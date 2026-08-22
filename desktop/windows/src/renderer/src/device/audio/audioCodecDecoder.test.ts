import { describe, it, expect } from 'vitest'
import { Lc3SilenceDecoder, MuLawDecoder, PcmDecoder } from './audioCodecDecoder'
import { createAudioDecoder, hasFullCodecSupport, isCodecSupported } from './audioDecoderFactory'
import { OpusFrameDecoder } from './opusFrameDecoder'
import { AacFrameDecoder } from './aacFrameDecoder'

const noSinks = { onPcm: () => undefined, onError: () => undefined }

describe('PcmDecoder', () => {
  it('passes 16-bit little-endian samples through signed', () => {
    const decoder = new PcmDecoder('pcm16')
    const pcm = decoder.decode(Uint8Array.from([0x00, 0x01, 0xff, 0xff, 0x00, 0x80]))!
    expect(Array.from(pcm)).toEqual([256, -1, -32768])
  })

  it('recenters unsigned 8-bit samples around zero', () => {
    const decoder = new PcmDecoder('pcm8')
    const pcm = decoder.decode(Uint8Array.from([128, 129, 127, 255, 0]))!
    expect(Array.from(pcm)).toEqual([0, 256, -256, 32512, -32768])
  })
})

describe('MuLawDecoder', () => {
  it('matches the canonical G.711 endpoints', () => {
    const decoder = new MuLawDecoder('mulaw8')
    const pcm = decoder.decode(Uint8Array.from([0x00, 0x80, 0xff, 0x7f]))!
    expect(Array.from(pcm)).toEqual([-32124, 32124, 0, 0])
  })
})

describe('Lc3SilenceDecoder', () => {
  it('emits 160 zero samples per frame so timing stays correct', () => {
    const decoder = new Lc3SilenceDecoder()
    const pcm = decoder.decode(new Uint8Array(30))!
    expect(pcm.length).toBe(160)
    expect(pcm.every((s) => s === 0)).toBe(true)
    expect(decoder.decode(new Uint8Array(0))).toBeNull()
    expect(decoder.hasFullSupport).toBe(false)
  })
})

describe('audio decoder factory', () => {
  it('supports every codec but unknown, and flags LC3 as partial', () => {
    expect(isCodecSupported('opus')).toBe(true)
    expect(isCodecSupported('lc3FS1030')).toBe(true)
    expect(isCodecSupported('unknown')).toBe(false)
    expect(hasFullCodecSupport('lc3FS1030')).toBe(false)
    expect(hasFullCodecSupport('opusFS320')).toBe(true)
  })

  it('builds the right decoder per codec and nothing for unknown', () => {
    expect(createAudioDecoder('pcm8', noSinks)).toBeInstanceOf(PcmDecoder)
    expect(createAudioDecoder('mulaw16', noSinks)).toBeInstanceOf(MuLawDecoder)
    expect(createAudioDecoder('lc3FS1030', noSinks)).toBeInstanceOf(Lc3SilenceDecoder)
    expect(createAudioDecoder('unknown', noSinks)).toBeNull()

    const opus = createAudioDecoder('opus', noSinks)
    expect(opus).toBeInstanceOf(OpusFrameDecoder)
    opus?.close()

    const aac = createAudioDecoder('aac', noSinks)
    expect(aac).toBeInstanceOf(AacFrameDecoder)
    aac?.close()
  })
})

describe('OpusFrameDecoder', () => {
  it('decodes real Opus frames to 16 kHz mono PCM', async () => {
    const decoder = new OpusFrameDecoder('opusFS320')
    await decoder.ready
    // A TOC-only packet is a valid DTX frame: config 23 is a 20 ms CELT
    // frame, which is 320 samples at 16 kHz.
    const pcm = decoder.decode(Uint8Array.from([0xb8]))
    expect(pcm).not.toBeNull()
    expect(pcm!.length).toBe(320)
    decoder.close()
  })

  it('returns null before the WASM decoder is ready and after close', async () => {
    const decoder = new OpusFrameDecoder('opus')
    expect(decoder.decode(Uint8Array.from([0xb8]))).toBeNull()
    await decoder.ready
    expect(decoder.decode(Uint8Array.from([0xb8]))).not.toBeNull()
    decoder.close()
    expect(decoder.decode(Uint8Array.from([0xb8]))).toBeNull()
  })

  it('is synchronous and fully supported', () => {
    const decoder = new OpusFrameDecoder('opus')
    expect(decoder.isAsync).toBe(false)
    expect(decoder.hasFullSupport).toBe(true)
    decoder.close()
  })
})

describe('AacFrameDecoder', () => {
  interface FakeChunk {
    type: string
    timestamp: number
    data: Uint8Array
  }

  const fakeWebCodecs = (): {
    globals: Record<string, unknown>
    chunks: FakeChunk[]
    emit: (samples: number[], format?: string) => void
    fail: (message: string) => void
    closed: () => boolean
  } => {
    const chunks: FakeChunk[] = []
    let output: ((data: unknown) => void) | null = null
    let error: ((e: Error) => void) | null = null
    let closed = false
    class FakeAudioDecoder {
      state = 'unconfigured'
      constructor(init: { output: (d: unknown) => void; error: (e: Error) => void }) {
        output = init.output
        error = init.error
      }
      configure(): void {
        this.state = 'configured'
      }
      decode(chunk: unknown): void {
        chunks.push(chunk as FakeChunk)
      }
      close(): void {
        this.state = 'closed'
        closed = true
      }
    }
    class FakeChunkCtor {
      type: string
      timestamp: number
      data: Uint8Array
      constructor(init: { type: string; timestamp: number; data: Uint8Array }) {
        this.type = init.type
        this.timestamp = init.timestamp
        this.data = init.data
      }
    }
    return {
      globals: { AudioDecoder: FakeAudioDecoder, EncodedAudioChunk: FakeChunkCtor },
      chunks,
      emit: (samples, format = 'f32-planar') => {
        output?.({
          numberOfFrames: samples.length,
          numberOfChannels: 1,
          format,
          copyTo: (destination: ArrayBufferView) => {
            const view = destination as Float32Array | Int16Array
            for (let i = 0; i < samples.length; i += 1) view[i] = samples[i]
          },
          close: () => undefined
        })
      },
      fail: (message) => error?.(new Error(message)),
      closed: () => closed
    }
  }

  it('forwards ADTS frames as key chunks with advancing timestamps', () => {
    const codecs = fakeWebCodecs()
    const pcm: Int16Array[] = []
    const decoder = new AacFrameDecoder(
      { onPcm: (p) => pcm.push(p), onError: () => undefined },
      codecs.globals
    )
    expect(decoder.hasFullSupport).toBe(true)
    expect(decoder.isAsync).toBe(true)

    const frame = new Uint8Array(20)
    frame[0] = 0xff
    frame[1] = 0xf1
    expect(decoder.decode(frame)).toBeNull()
    expect(decoder.decode(frame)).toBeNull()
    expect(codecs.chunks.length).toBe(2)
    expect(codecs.chunks[0].type).toBe('key')
    expect(codecs.chunks[1].timestamp).toBeGreaterThan(codecs.chunks[0].timestamp)

    // PCM arrives through the sink, converted from planar float.
    codecs.emit([0, 0.5, -1])
    expect(pcm.length).toBe(1)
    expect(Array.from(pcm[0])).toEqual([0, 16384, -32767])
    decoder.close()
    expect(codecs.closed()).toBe(true)
  })

  it('takes s16 output without a float conversion', () => {
    const codecs = fakeWebCodecs()
    const pcm: Int16Array[] = []
    const decoder = new AacFrameDecoder(
      { onPcm: (p) => pcm.push(p), onError: () => undefined },
      codecs.globals
    )
    codecs.emit([5, -5, 100], 's16')
    expect(Array.from(pcm[0])).toEqual([5, -5, 100])
    decoder.close()
  })

  it('reports short frames and decoder errors through the sink', () => {
    const codecs = fakeWebCodecs()
    const errors: string[] = []
    const decoder = new AacFrameDecoder(
      { onPcm: () => undefined, onError: (e) => errors.push(e.message) },
      codecs.globals
    )
    decoder.decode(new Uint8Array(3))
    expect(codecs.chunks.length).toBe(0)
    expect(errors[0]).toContain('shorter than an ADTS header')
    codecs.fail('bitstream corrupt')
    expect(errors[1]).toBe('bitstream corrupt')
    decoder.close()
  })

  it('reports missing WebCodecs as partial support instead of throwing', () => {
    const decoder = new AacFrameDecoder(noSinks, {})
    expect(decoder.hasFullSupport).toBe(false)
    expect(decoder.decode(new Uint8Array(20))).toBeNull()
    decoder.close()
  })
})
