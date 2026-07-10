import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { CaptureCommand, CaptureEvent, ListenMessage } from '../../../shared/types'

// omiListenClient now owns the transcript flow in the CALLING window but drives
// capture REMOTELY: it opens the listen session, sends audio-start to the capture
// window, maps listen messages to callbacks, maps a routed audio-source-error to
// a fatal error, and tears down (audio-stop + listenStop) on stop.

vi.mock('./firebase', () => ({
  auth: { currentUser: { getIdToken: vi.fn(async () => 'test-token') } }
}))
vi.mock('./preferences', () => ({ getPreferences: () => ({ language: 'en' }) }))

import { startOmiListen } from './omiListenClient'

type Bridge = {
  listenStart: ReturnType<typeof vi.fn>
  listenStop: ReturnType<typeof vi.fn>
  captureCommand: ReturnType<typeof vi.fn>
  commands: CaptureCommand[]
  msgHandlers: Array<(m: ListenMessage) => void>
  evHandlers: Array<(e: CaptureEvent) => void>
}

let bridge: Bridge

function emitMsg(m: ListenMessage): void {
  for (const fn of [...bridge.msgHandlers]) fn(m)
}
function emitEvent(e: CaptureEvent): void {
  for (const fn of [...bridge.evHandlers]) fn(e)
}

function callbacks() {
  return {
    onConnected: vi.fn(),
    onSegments: vi.fn(),
    onEvent: vi.fn(),
    onError: vi.fn(),
    onClosed: vi.fn()
  }
}

beforeEach(() => {
  bridge = {
    listenStart: vi.fn(async () => {}),
    listenStop: vi.fn(async () => {}),
    captureCommand: vi.fn((c: CaptureCommand) => bridge.commands.push(c)),
    commands: [],
    msgHandlers: [],
    evHandlers: []
  }
  ;(globalThis as Record<string, unknown>).window = {
    omi: {
      listenStart: bridge.listenStart,
      listenStop: bridge.listenStop,
      listenFeed: vi.fn(),
      captureCommand: bridge.captureCommand,
      onListenMessage: (fn: (m: ListenMessage) => void) => {
        bridge.msgHandlers.push(fn)
        return () => (bridge.msgHandlers = bridge.msgHandlers.filter((x) => x !== fn))
      },
      onCaptureEvent: (fn: (e: CaptureEvent) => void) => {
        bridge.evHandlers.push(fn)
        return () => (bridge.evHandlers = bridge.evHandlers.filter((x) => x !== fn))
      }
    }
  }
})

function startedSessionId(): string {
  const args = bridge.listenStart.mock.calls[0][0] as { sessionId: string }
  return args.sessionId
}

describe('startOmiListen', () => {
  it('opens the session and asks the capture window to stream the source (VAD-gated)', async () => {
    await startOmiListen('mic', callbacks())
    expect(bridge.listenStart).toHaveBeenCalledTimes(1)
    const startArgs = bridge.listenStart.mock.calls[0][0]
    expect(startArgs).toMatchObject({
      source: 'mic',
      mode: 'conversation',
      token: 'test-token',
      language: 'en'
    })
    const audioStart = bridge.commands.find((c) => c.type === 'audio-start')
    expect(audioStart).toMatchObject({
      type: 'audio-start',
      source: 'mic',
      sessionId: startArgs.sessionId
    })
  })

  it('maps listen messages to callbacks', async () => {
    const cb = callbacks()
    await startOmiListen('mic', cb)
    const sessionId = startedSessionId()
    emitMsg({ sessionId, kind: 'connected' })
    emitMsg({
      sessionId,
      kind: 'segments',
      segments: [{ text: 'hi', is_user: true, start: 0, end: 1 }]
    })
    expect(cb.onConnected).toHaveBeenCalled()
    expect(cb.onSegments).toHaveBeenCalledWith([{ text: 'hi', is_user: true, start: 0, end: 1 }])
  })

  it('a close AFTER connect calls onClosed; a close BEFORE connect is a fatal error', async () => {
    const cb = callbacks()
    await startOmiListen('mic', cb)
    const sessionId = startedSessionId()
    emitMsg({ sessionId, kind: 'connected' })
    emitMsg({ sessionId, kind: 'closed', code: 1000, reason: 'bye' })
    expect(cb.onClosed).toHaveBeenCalledWith(1000, 'bye')

    const cb2 = callbacks()
    await startOmiListen('system', cb2)
    const sid2 = (bridge.listenStart.mock.calls[1][0] as { sessionId: string }).sessionId
    emitMsg({ sessionId: sid2, kind: 'closed', code: 1006, reason: '' })
    expect(cb2.onError).toHaveBeenCalledWith(expect.any(Error), true)
    expect(cb2.onClosed).not.toHaveBeenCalled()
  })

  it('maps a routed audio-source-error to a fatal error', async () => {
    const cb = callbacks()
    await startOmiListen('mic', cb)
    const sessionId = startedSessionId()
    emitEvent({
      type: 'audio-source-error',
      sessionId,
      name: 'NotAllowedError',
      message: 'blocked'
    })
    expect(cb.onError).toHaveBeenCalledWith(expect.any(Error), true)
    expect((cb.onError.mock.calls[0][0] as Error).message).toBe('blocked')
  })

  it('ignores messages/events for a different session', async () => {
    const cb = callbacks()
    await startOmiListen('mic', cb)
    emitMsg({ sessionId: 'other', kind: 'connected' })
    emitEvent({ type: 'audio-source-error', sessionId: 'other', name: 'X', message: 'y' })
    expect(cb.onConnected).not.toHaveBeenCalled()
    expect(cb.onError).not.toHaveBeenCalled()
  })

  it('re-issues audio-start when the capture window restarts (frozen-transcript regression)', async () => {
    await startOmiListen('mic', callbacks())
    const sessionId = startedSessionId()
    const startsBefore = bridge.commands.filter((c) => c.type === 'audio-start').length
    emitEvent({ type: 'capture-window-restarted' })
    const starts = bridge.commands.filter((c) => c.type === 'audio-start')
    expect(starts.length).toBe(startsBefore + 1)
    expect(starts[starts.length - 1]).toMatchObject({ type: 'audio-start', sessionId, source: 'mic' })
  })

  it('does NOT re-issue audio-start after stop()', async () => {
    const session = await startOmiListen('mic', callbacks())
    session.stop()
    const startsBefore = bridge.commands.filter((c) => c.type === 'audio-start').length
    emitEvent({ type: 'capture-window-restarted' })
    expect(bridge.commands.filter((c) => c.type === 'audio-start').length).toBe(startsBefore)
  })

  it('stop() tears down: audio-stop, listenStop, and no further callbacks', async () => {
    const cb = callbacks()
    const handle = await startOmiListen('mic', cb)
    const sessionId = startedSessionId()
    handle.stop()
    expect(bridge.commands.some((c) => c.type === 'audio-stop' && c.sessionId === sessionId)).toBe(
      true
    )
    expect(bridge.listenStop).toHaveBeenCalledWith(sessionId)
    // Unsubscribed — a late message must not reach the callbacks.
    emitMsg({ sessionId, kind: 'segments', segments: [] })
    expect(cb.onSegments).not.toHaveBeenCalled()
  })
})
