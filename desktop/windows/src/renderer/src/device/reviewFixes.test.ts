/**
 * Regression tests for the review findings on the wearable stack. Each case
 * names the failure it prevents rather than the code it touches.
 */

import { describe, it, expect } from 'vitest'
import { DeviceOperationBroker, UncorrelatedOperationGate } from './session/deviceOperationBroker'
import { DeviceSessionCoordinator } from './session/deviceSessionCoordinator'
import { DeviceListenSession, type DeviceLaneTransport } from './lane/deviceListenSession'
import { BleAudioProcessor } from './audio/bleAudioProcessor'
import { BleAudioService } from './audio/bleAudioService'
import { AacFrameDecoder } from './audio/aacFrameDecoder'
import { OpusFrameDecoder } from './audio/opusFrameDecoder'
import { extractOpusRecursive, encodeVarint } from './connections/limitlessProtocol'
import { makeBtDevice } from './protocol/btDevice'
import { ManualClock, tick } from './testing/fakes'
import type { DeviceConnection } from './connections/deviceConnection'
import type { BackendSegment } from '../../../shared/types'

describe('broker: a start that rejects must not strand its caller', () => {
  it('settles as failed even when nothing ever completes the operation', async () => {
    const broker = new DeviceOperationBroker(new ManualClock())
    const startError = new Error('write rejected')
    // No timeout, and no succeed/fail call: before the fix this promise hung
    // forever, blocking the connect sequence behind it.
    await expect(
      broker.perform<void>({ key: 'k', start: () => Promise.reject(startError) })
    ).rejects.toBe(startError)
    // The key is released, so the caller can retry.
    expect(broker.hasPending('k')).toBe(false)
  })

  it('reports a start failure rather than a misleading timeout', async () => {
    const clock = new ManualClock()
    const broker = new DeviceOperationBroker(clock)
    const promise = broker.perform<void>({
      key: 'k',
      timeoutMs: 5_000,
      start: () => Promise.reject(new Error('gatt busy'))
    })
    await expect(promise).rejects.toThrow('gatt busy')
  })

  it('a throwing terminal hook still resumes the caller, and does not escape', async () => {
    const broker = new DeviceOperationBroker(new ManualClock())
    const escaped: unknown[] = []
    const onRejection = (reason: unknown): void => {
      escaped.push(reason)
    }
    process.on('unhandledRejection', onRejection)
    try {
      const promise = broker.perform<number>({
        key: 'k',
        onTerminal: () => {
          throw new Error('hook exploded')
        },
        start: () => undefined
      })
      broker.succeed('k', 5)
      await expect(promise).resolves.toBe(5)
      // Let any stray rejection surface before asserting there was none.
      await new Promise((resolve) => setTimeout(resolve, 0))
      expect(escaped).toEqual([])
    } finally {
      process.off('unhandledRejection', onRejection)
    }
  })
})

describe('coordinator: a retry token belongs to one device', () => {
  it('refuses to open a different device with a valid token', async () => {
    const deviceA = makeBtDevice({ id: 'a', name: 'A', type: 'omi' })
    const deviceB = makeBtDevice({ id: 'b', name: 'B', type: 'omi' })
    const requests: Array<{ device: typeof deviceA; generation: number; attempt: number }> = []
    const coordinator = new DeviceSessionCoordinator(
      {
        connectionFactory: () => null,
        onReconnectRequested: (r) => requests.push(r)
      },
      { pairedDevice: deviceA, clock: new ManualClock() }
    )
    coordinator.startReconnecting()
    await tick()
    expect(requests.length).toBe(1)
    await expect(coordinator.connect(deviceB, requests[0])).rejects.toMatchObject({
      kind: 'superseded'
    })
  })
})

describe('lane: overlapping starts must not open two sockets', () => {
  const laneHarness = (): { lane: DeviceListenSession; starts: number } => {
    const state = { starts: 0 }
    const transport: DeviceLaneTransport = {
      // Resolves on a later microtask, which is the window two concurrent
      // starts used to slip through.
      isConversationLaneBusy: async () => {
        await Promise.resolve()
        return false
      },
      startSession: async () => {
        state.starts += 1
      },
      feed: () => undefined,
      stopSession: () => undefined,
      subscribe: () => () => undefined,
      sleep: async () => 'aborted',
      newSessionId: () => `s${state.starts}`,
      newConversationId: () => 'c'
    }
    const lane = new DeviceListenSession(transport)
    return {
      lane,
      get starts() {
        return state.starts
      }
    } as { lane: DeviceListenSession; starts: number }
  }

  it('the second concurrent start is refused', async () => {
    const h = laneHarness()
    const [first, second] = await Promise.all([h.lane.start(), h.lane.start()])
    expect([first, second].filter(Boolean).length).toBe(1)
    expect(h.starts).toBe(1)
  })

  it('a conversation boundary drops retained segments so they are not re-rescued', async () => {
    const rescued: BackendSegment[][] = []
    let live: Parameters<DeviceLaneTransport['subscribe']>[0] | null = null
    const transport: DeviceLaneTransport = {
      isConversationLaneBusy: async () => false,
      startSession: async () => undefined,
      feed: () => undefined,
      stopSession: () => undefined,
      subscribe: (h) => {
        live = h
        return () => undefined
      },
      sleep: async () => 'elapsed',
      newSessionId: () => 'session-1',
      newConversationId: () => 'conv-1'
    }
    const lane = new DeviceListenSession(transport, { onRescue: (s) => rescued.push(s) })
    await lane.start()
    live!.onConnected('session-1')
    live!.onSegments('session-1', [{ id: 'a', text: 'first call' } as unknown as BackendSegment])
    expect(lane.retainedSegments().length).toBe(1)

    // The backend finalized that conversation; those segments are already saved.
    live!.onEvent('session-1', { type: 'memory_creating' } as never)
    expect(lane.retainedSegments().length).toBe(0)

    live!.onClosed('session-1', 1008, 'trial_expired')
    expect(rescued.length).toBe(0)
  })
})

describe('audio: a decoder that can never produce samples is not healthy', () => {
  it('an async decoder without real support drives the degradation ladder', () => {
    const degraded: boolean[] = []
    // AAC with no WebCodecs: decode() returns null forever and no sink fires.
    const processor = new BleAudioProcessor({
      codec: 'aac',
      delegate: {
        onPcm: () => undefined,
        onDegradedChange: (isDegraded) => degraded.push(isDegraded)
      }
    })
    expect(processor.hasFullSupport).toBe(false)
    const frame = new Uint8Array(20)
    frame[0] = 0xff
    frame[1] = 0xf1
    for (let i = 0; i < 10; i += 1) processor.processFrame(frame)
    expect(degraded).toEqual([true])
  })
})

describe('audio service: a failed start releases the session slot', () => {
  const failingConnection = (): DeviceConnection =>
    ({
      device: makeBtDevice({ id: 'x', name: null, type: 'omi' }),
      getAudioCodec: async () => {
        throw new Error('codec read failed')
      },
      getAudioStream: () => ({ cancel: () => undefined })
    }) as unknown as DeviceConnection

  it('a later start is not refused as already running', async () => {
    const service = new BleAudioService()
    expect(await service.startProcessing(failingConnection(), { onPcm: () => undefined })).toBe(
      false
    )
    expect(service.isProcessing).toBe(false)

    const working = {
      device: makeBtDevice({ id: 'x', name: null, type: 'omi' }),
      getAudioCodec: async () => 'pcm8' as const,
      getAudioStream: () => ({ cancel: () => undefined })
    } as unknown as DeviceConnection
    expect(await service.startProcessing(working, { onPcm: () => undefined })).toBe(true)
    service.stopProcessing()
  })
})

describe('limitless: unknown fixed-width fields must be stepped over', () => {
  it('keeps extracting Opus frames after a fixed64 field', () => {
    const frame = Uint8Array.from([0xb8, ...new Array(11).fill(3)])
    // field 1, wire type 1 (fixed64) followed by the audio bytes field.
    const data = Uint8Array.from([
      (1 << 3) | 1,
      ...new Array(8).fill(0),
      (2 << 3) | 2,
      ...encodeVarint(frame.length),
      ...frame
    ])
    const frames = extractOpusRecursive(data)
    expect(frames.length).toBe(1)
    expect(frames[0]).toEqual(frame)
  })
})

describe('decoders: teardown must not lose or throw', () => {
  it('closing an Opus decoder before the WASM is ready is safe', async () => {
    const decoder = new OpusFrameDecoder('opus')
    decoder.close()
    // The initialization continuation still runs; it must free rather than
    // resurrect the decoder, and must not throw.
    await expect(decoder.ready).resolves.toBeUndefined()
    expect(decoder.decode(Uint8Array.from([0xb8]))).toBeNull()
  })

  it('an AAC decoder flushes queued output before closing', () => {
    const calls: string[] = []
    let closed = false
    class FakeDecoder {
      state = 'configured'
      configure(): void {
        this.state = 'configured'
      }
      decode(): void {
        calls.push('decode')
      }
      flush(): Promise<void> {
        calls.push('flush')
        return Promise.resolve()
      }
      close(): void {
        calls.push('close')
        closed = true
        this.state = 'closed'
      }
    }
    class FakeChunk {
      constructor(readonly init: unknown) {}
    }
    const decoder = new AacFrameDecoder(
      { onPcm: () => undefined, onError: () => undefined },
      { AudioDecoder: FakeDecoder as never, EncodedAudioChunk: FakeChunk as never }
    )
    decoder.close()
    expect(calls[0]).toBe('flush')
    void closed
  })
})

describe('gate: identity poisoning survives a reset boundary correctly', () => {
  it('reset clears poisoning so a fresh session starts clean', () => {
    const gate = new UncorrelatedOperationGate()
    const handle = gate.register('k')!
    gate.terminal(handle, 'timedOut')
    expect(gate.canStart('k')).toBe(false)
    gate.reset()
    expect(gate.canStart('k')).toBe(true)
    expect(gate.hasLiveAttempt('k')).toBe(false)
  })
})
