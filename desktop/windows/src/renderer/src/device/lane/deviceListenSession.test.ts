import { describe, it, expect } from 'vitest'
import {
  DeviceListenSession,
  type DeviceLaneState,
  type DeviceLaneTransport
} from './deviceListenSession'
import { MAX_RECONNECT_ATTEMPTS } from '../../capture/liveRescue'
import type { BackendSegment } from '../../../../shared/types'
import { ManualClock, tick } from '../testing/fakes'

const segment = (id: string, text: string): BackendSegment =>
  ({ id, text, speaker: 'SPEAKER_0', start: 0, end: 1 }) as unknown as BackendSegment

interface Harness {
  session: DeviceListenSession
  clock: ManualClock
  transport: {
    busy: boolean
    startError: Error | null
    started: Array<{ sessionId: string; clientConversationId: string }>
    stopped: string[]
    fed: Array<{ sessionId: string; bytes: number }>
    subscriptions: number
    unsubscribes: number
  }
  handlers: {
    connect: (sessionId?: string) => void
    segments: (segs: BackendSegment[], sessionId?: string) => void
    close: (code: number, reason: string, sessionId?: string) => void
  }
  states: DeviceLaneState[]
  rescued: BackendSegment[][]
  lastSessionId: () => string
}

const harness = (): Harness => {
  const clock = new ManualClock()
  const states: DeviceLaneState[] = []
  const rescued: BackendSegment[][] = []
  const transport = {
    busy: false,
    startError: null as Error | null,
    started: [] as Array<{ sessionId: string; clientConversationId: string }>,
    stopped: [] as string[],
    fed: [] as Array<{ sessionId: string; bytes: number }>,
    subscriptions: 0,
    unsubscribes: 0
  }
  let sessionCounter = 0
  let live: Parameters<DeviceLaneTransport['subscribe']>[0] | null = null
  let lastId = ''

  const laneTransport: DeviceLaneTransport = {
    isConversationLaneBusy: async () => transport.busy,
    startSession: async (args) => {
      transport.started.push(args)
      if (transport.startError !== null) throw transport.startError
    },
    feed: (sessionId, pcm) => transport.fed.push({ sessionId, bytes: pcm.byteLength }),
    stopSession: (sessionId) => transport.stopped.push(sessionId),
    subscribe: (h) => {
      transport.subscriptions += 1
      live = h
      return () => {
        transport.unsubscribes += 1
      }
    },
    sleep: (ms, signal) => clock.sleep(ms, signal),
    newSessionId: () => {
      lastId = `device-listen-${++sessionCounter}`
      return lastId
    },
    newConversationId: () => 'conv-fixed'
  }

  const session = new DeviceListenSession(laneTransport, {
    onStateChange: (state) => states.push(state),
    onRescue: (segments) => rescued.push(segments)
  })

  return {
    session,
    clock,
    transport,
    states,
    rescued,
    lastSessionId: () => lastId,
    handlers: {
      connect: (sessionId) => live?.onConnected(sessionId ?? lastId),
      segments: (segs, sessionId) => live?.onSegments(sessionId ?? lastId, segs),
      close: (code, reason, sessionId) => live?.onClosed(sessionId ?? lastId, code, reason)
    }
  }
}

describe('DeviceListenSession', () => {
  it('refuses to open while the microphone lane holds the conversation socket', async () => {
    const h = harness()
    h.transport.busy = true
    expect(await h.session.start()).toBe(false)
    expect(h.session.currentState).toBe('blocked')
    expect(h.transport.started.length).toBe(0)
  })

  it('opens a conversation session and streams PCM without a capture command', async () => {
    const h = harness()
    expect(await h.session.start()).toBe(true)
    expect(h.transport.started.length).toBe(1)
    expect(h.transport.started[0].clientConversationId).toBe('conv-fixed')

    h.handlers.connect()
    expect(h.session.currentState).toBe('streaming')

    h.session.feed(Int16Array.from([1, 2, 3, 4]))
    expect(h.transport.fed).toEqual([{ sessionId: h.lastSessionId(), bytes: 8 }])
  })

  it('drops audio fed before the lane opens or after it stops', async () => {
    const h = harness()
    h.session.feed(Int16Array.from([1, 2]))
    expect(h.transport.fed.length).toBe(0)

    await h.session.start()
    h.handlers.connect()
    h.session.stop()
    h.session.feed(Int16Array.from([1, 2]))
    expect(h.transport.fed.length).toBe(0)
  })

  it('reconnects on a retryable drop and resumes the same conversation', async () => {
    const h = harness()
    await h.session.start()
    h.handlers.connect()
    const firstSession = h.lastSessionId()

    h.handlers.close(1006, 'connection lost')
    expect(h.session.currentState).toBe('reconnecting')
    expect(h.transport.stopped).toEqual([firstSession])

    // Backoff runs on the injected clock; the first attempt waits ~2 s.
    h.clock.advance(5_000)
    await tick()
    expect(h.transport.started.length).toBe(2)
    expect(h.transport.started[1].sessionId).not.toBe(firstSession)
    // Same conversation id, so the backend continues the same conversation.
    expect(h.transport.started[1].clientConversationId).toBe('conv-fixed')

    h.handlers.connect()
    expect(h.session.currentState).toBe('streaming')
  })

  it('gives up on a quota close immediately and rescues retained segments', async () => {
    const h = harness()
    await h.session.start()
    h.handlers.connect()
    h.handlers.segments([segment('a', 'hello'), segment('b', 'world')])

    h.handlers.close(1008, 'trial_expired')
    expect(h.transport.started.length).toBe(1)
    expect(h.session.currentState).toBe('stopped')
    expect(h.rescued.length).toBe(1)
    expect(h.rescued[0].map((s) => s.text)).toEqual(['hello', 'world'])
  })

  it('rescues after the reconnect budget is exhausted', async () => {
    const h = harness()
    await h.session.start()
    h.handlers.connect()
    h.handlers.segments([segment('a', 'kept')])

    for (let i = 0; i < MAX_RECONNECT_ATTEMPTS; i += 1) {
      h.handlers.close(1006, 'connection lost')
      h.clock.advance(60_000)
      await tick()
      // Each retry opens a new session that never connects.
    }
    expect(h.transport.started.length).toBe(MAX_RECONNECT_ATTEMPTS + 1)

    h.handlers.close(1006, 'connection lost')
    expect(h.session.currentState).toBe('stopped')
    expect(h.rescued[0].map((s) => s.text)).toEqual(['kept'])
  })

  it('a successful reconnect resets the retry budget', async () => {
    const h = harness()
    await h.session.start()
    h.handlers.connect()
    // More drops than the budget allows: each one reconnects successfully, so
    // a lane that never reset its counter would give up partway through.
    for (let i = 0; i < MAX_RECONNECT_ATTEMPTS + 2; i += 1) {
      h.handlers.close(1006, 'connection lost')
      expect(h.session.currentState).toBe('reconnecting')
      h.clock.advance(60_000)
      await tick()
      h.handlers.connect()
      expect(h.session.currentState).toBe('streaming')
    }
    expect(h.transport.started.length).toBe(MAX_RECONNECT_ATTEMPTS + 3)
    expect(h.rescued.length).toBe(0)
  })

  it('refines repeated segment ids in place rather than duplicating them', async () => {
    const h = harness()
    await h.session.start()
    h.handlers.connect()
    h.handlers.segments([segment('a', 'hel')])
    h.handlers.segments([segment('a', 'hello there')])
    expect(h.session.retainedSegments().map((s) => s.text)).toEqual(['hello there'])
  })

  it('stop tears the socket down once and stops reconnecting', async () => {
    const h = harness()
    await h.session.start()
    h.handlers.connect()
    const sessionId = h.lastSessionId()

    h.session.stop()
    expect(h.transport.stopped).toEqual([sessionId])
    expect(h.transport.unsubscribes).toBe(1)

    h.session.stop()
    expect(h.transport.stopped.length).toBe(1)

    h.clock.advance(120_000)
    await tick()
    expect(h.transport.started.length).toBe(1)
  })

  it('a failed start is treated as a drop and retried', async () => {
    const h = harness()
    h.transport.startError = new Error('socket refused')
    expect(await h.session.start()).toBe(false)
    expect(h.session.currentState).toBe('reconnecting')

    h.transport.startError = null
    h.clock.advance(60_000)
    await tick()
    expect(h.transport.started.length).toBe(2)
  })

  it('ignores messages addressed to a superseded session', async () => {
    const h = harness()
    await h.session.start()
    h.handlers.connect()
    h.handlers.segments([segment('a', 'live')], 'device-listen-stale')
    expect(h.session.retainedSegments().length).toBe(0)
    h.handlers.close(1006, 'connection lost', 'device-listen-stale')
    expect(h.session.currentState).toBe('streaming')
  })
})
