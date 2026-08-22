import { describe, it, expect } from 'vitest'
import { BleAudioService } from './bleAudioService'
import type { DeviceConnection, StreamSubscriber } from '../connections/deviceConnection'
import type { BleAudioCodec } from '../protocol/deviceTypes'
import type { BtDevice } from '../protocol/btDevice'
import { makeBtDevice } from '../protocol/btDevice'
import type { DeviceType } from '../protocol/deviceTypes'

const tick = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0))

/** Minimal connection stub exposing just the audio surface the service uses. */
class StubConnection {
  device: BtDevice
  audioSubscribers: Array<StreamSubscriber<Uint8Array>> = []
  codecReads = 0
  cancels = 0

  constructor(
    type: DeviceType,
    private readonly codec: BleAudioCodec,
    private readonly codecGate?: Promise<void>
  ) {
    this.device = makeBtDevice({ id: 'stub', name: null, type })
  }

  async getAudioCodec(): Promise<BleAudioCodec> {
    this.codecReads += 1
    if (this.codecGate !== undefined) await this.codecGate
    return this.codec
  }

  getAudioStream(subscriber: StreamSubscriber<Uint8Array>): { cancel: () => void } {
    this.audioSubscribers.push(subscriber)
    return {
      cancel: () => {
        this.cancels += 1
      }
    }
  }

  emit(frame: Uint8Array): void {
    for (const subscriber of this.audioSubscribers) subscriber.onValue(frame)
  }

  finish(error: Error | null): void {
    for (const subscriber of this.audioSubscribers) subscriber.onFinish(error)
  }

  asConnection(): DeviceConnection {
    return this as unknown as DeviceConnection
  }
}

/** [u16 index LE, u8 frameId, ...content] */
const packet = (index: number, frameId: number, content: number[]): Uint8Array =>
  Uint8Array.from([index & 0xff, (index >> 8) & 0xff, frameId, ...content])

describe('BleAudioService', () => {
  it('decodes an Omi session end to end and reports the codec', async () => {
    const connection = new StubConnection('omi', 'pcm8')
    const service = new BleAudioService()
    const pcm: Int16Array[] = []
    const codecs: BleAudioCodec[] = []
    const raw: Uint8Array[] = []

    expect(
      await service.startProcessing(connection.asConnection(), {
        onPcm: (p) => pcm.push(p),
        onRawFrame: (f) => raw.push(f),
        onCodec: (c) => codecs.push(c)
      })
    ).toBe(true)
    expect(service.isProcessing).toBe(true)
    expect(service.currentCodec).toBe('pcm8')
    expect(codecs).toEqual(['pcm8'])

    connection.emit(packet(1, 0, new Array(80).fill(200)))
    expect(pcm.length).toBe(1)
    expect(pcm[0].length).toBe(80)
    // The raw encoded frame reaches the WAL handler before any decoding.
    expect(raw.length).toBe(1)
    expect(raw[0].length).toBe(83)
    expect(service.audioLevel).toBeGreaterThan(0)

    const stats = service.stopProcessing()
    expect(stats?.framesProcessed).toBe(1)
    expect(connection.cancels).toBe(1)
    expect(service.isProcessing).toBe(false)
  })

  it('refuses a second start while one session is running', async () => {
    const connection = new StubConnection('omi', 'pcm8')
    const service = new BleAudioService()
    await service.startProcessing(connection.asConnection(), { onPcm: () => undefined })
    expect(
      await service.startProcessing(connection.asConnection(), { onPcm: () => undefined })
    ).toBe(false)
    expect(connection.codecReads).toBe(1)
  })

  it('aborts a start that was stopped during the codec read, reporting nothing', async () => {
    let release!: () => void
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    const connection = new StubConnection('omi', 'pcm8', gate)
    const service = new BleAudioService()
    const codecs: BleAudioCodec[] = []
    const starting = service.startProcessing(connection.asConnection(), {
      onPcm: () => undefined,
      onCodec: (c) => codecs.push(c)
    })
    service.stopProcessing()
    release()
    expect(await starting).toBe(false)
    expect(connection.audioSubscribers.length).toBe(0)
    expect(service.isProcessing).toBe(false)
    // A start abandoned mid-read must not publish state for the session it
    // never opened.
    expect(codecs).toEqual([])
    expect(service.currentCodec).toBeNull()
  })

  it('refuses an unsupported codec and tears the session back down', async () => {
    const connection = new StubConnection('omi', 'unknown')
    const service = new BleAudioService()
    expect(
      await service.startProcessing(connection.asConnection(), { onPcm: () => undefined })
    ).toBe(false)
    expect(service.isProcessing).toBe(false)
    expect(connection.audioSubscribers.length).toBe(0)
  })

  it('routes Bee and Limitless frames whole, and other families through reassembly', async () => {
    // Bee frames are already whole: an LC3-sized frame decodes on its own,
    // while the same bytes sent as an Omi packet would need a header.
    const bee = new StubConnection('bee', 'lc3FS1030')
    const beeService = new BleAudioService()
    const beePcm: Int16Array[] = []
    await beeService.startProcessing(bee.asConnection(), { onPcm: (p) => beePcm.push(p) })
    bee.emit(new Uint8Array(30))
    expect(beePcm.length).toBe(1)
    beeService.stopProcessing()

    const plaud = new StubConnection('plaud', 'lc3FS1030')
    const plaudService = new BleAudioService()
    const plaudPcm: Int16Array[] = []
    await plaudService.startProcessing(plaud.asConnection(), { onPcm: (p) => plaudPcm.push(p) })
    // Non-whole-frame families go through processAudioData, which slices.
    plaud.emit(new Uint8Array(60))
    expect(plaudPcm.length).toBe(2)
    plaudService.stopProcessing()
  })

  it('a stream that ends tears the session down and reports the error once', async () => {
    const connection = new StubConnection('omi', 'pcm8')
    const service = new BleAudioService()
    const ended: Array<Error | null> = []
    await service.startProcessing(connection.asConnection(), {
      onPcm: () => undefined,
      onEnded: (error) => ended.push(error)
    })
    connection.finish(new Error('link lost'))
    await tick()
    expect(ended.length).toBe(1)
    expect(ended[0]?.message).toBe('link lost')
    expect(service.isProcessing).toBe(false)
    expect(service.currentCodec).toBeNull()
  })

  it('surfaces the degraded flag from the processor and clears it on recovery', async () => {
    // Bee routes whole frames straight to the decoder, so an empty frame is a
    // decode failure rather than an empty slice list.
    const connection = new StubConnection('bee', 'lc3FS1030')
    const service = new BleAudioService()
    const degraded: boolean[] = []
    await service.startProcessing(connection.asConnection(), {
      onPcm: () => undefined,
      onDegradedChange: (isDegraded) => degraded.push(isDegraded)
    })
    for (let i = 0; i < 9; i += 1) connection.emit(new Uint8Array(0))
    expect(degraded).toEqual([])
    expect(service.isDecodeDegraded).toBe(false)

    connection.emit(new Uint8Array(0))
    expect(degraded).toEqual([true])
    expect(service.isDecodeDegraded).toBe(true)

    connection.emit(new Uint8Array(30))
    expect(degraded).toEqual([true, false])
    expect(service.isDecodeDegraded).toBe(false)
    service.stopProcessing()
  })

  it('smooths the audio level toward the signal RMS', async () => {
    const connection = new StubConnection('omi', 'pcm16')
    const service = new BleAudioService()
    const levels: number[] = []
    await service.startProcessing(connection.asConnection(), {
      onPcm: () => undefined,
      onLevel: (level) => levels.push(level)
    })
    // Full-scale samples: RMS is 1, and the smoothing lands each step 30% closer.
    const loud: number[] = []
    for (let i = 0; i < 40; i += 1) loud.push(0xff, 0x7f)
    connection.emit(packet(1, 0, loud))
    expect(levels.length).toBe(1)
    expect(levels[0]).toBeCloseTo(0.3, 2)
    connection.emit(packet(2, 0, loud))
    expect(levels[1]).toBeCloseTo(0.51, 2)
    service.stopProcessing()
  })
})
