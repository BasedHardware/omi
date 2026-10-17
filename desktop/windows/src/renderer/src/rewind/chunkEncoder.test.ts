// The encoder's orchestration, driven by a fake codec.
//
// What a fake can prove is everything that is not the codec: that frames go in
// in capture order, that exactly the first one is a key frame, that the decoder
// description is not dropped, and — the part that matters most — that no
// failure path can return a chunk holding only some of the frames the caller is
// about to delete the JPEGs for. The real H.264 round trip is covered by the
// Electron e2e, which is where a real encoder exists.
import { describe, expect, it, vi } from 'vitest'
import { decodeChunk } from '../../../main/rewind/chunks/chunkFormat'
import {
  CHUNK_BITRATE,
  ChunkEncodeError,
  encodeFramesToChunk,
  pickChunkCodec,
  type EncoderDeps,
  type SourceFrame
} from './chunkEncoder'

type EncodeCall = { keyFrame: boolean; timestamp: number }

function fakeDeps(
  options: {
    supported?: (codec: string) => boolean
    /** Emit the decoder description on the chunk at this index. */
    describeAt?: number | null
    /** Stop emitting output after this many frames, without erroring. */
    emitOnly?: number
    /** Raise on the encoder's error callback at this input index. */
    errorAt?: number
    calls?: EncodeCall[]
  } = {}
): EncoderDeps {
  const supported = options.supported ?? ((c: string) => c === 'avc1.42001f')
  const describeAt = options.describeAt === undefined ? 0 : options.describeAt
  const calls = options.calls ?? []

  class FakeVideoEncoder {
    static async isConfigSupported(config: { codec: string }) {
      return { supported: supported(config.codec), config }
    }
    private emitted = 0
    private onError: (e: Error) => void
    private onOutput: (chunk: unknown, meta?: unknown) => void
    constructor(init: { output: (c: unknown, m?: unknown) => void; error: (e: Error) => void }) {
      this.onOutput = init.output
      this.onError = init.error
    }
    configure(): void {
      /* the fake needs no configuration */
    }
    encode(frame: { timestamp: number }, opts?: { keyFrame?: boolean }): void {
      const index = calls.length
      calls.push({ keyFrame: Boolean(opts?.keyFrame), timestamp: frame.timestamp })
      if (options.errorAt === index) {
        this.onError(new Error('fake encoder failed'))
        return
      }
      if (options.emitOnly !== undefined && this.emitted >= options.emitOnly) return
      const payload = new Uint8Array([index + 1, 0xaa])
      this.onOutput(
        {
          type: opts?.keyFrame ? 'key' : 'delta',
          byteLength: payload.byteLength,
          copyTo: (dest: Uint8Array) => dest.set(payload)
        },
        this.emitted === describeAt
          ? { decoderConfig: { description: new Uint8Array([1, 100, 0, 31]) } }
          : undefined
      )
      this.emitted++
    }
    async flush(): Promise<void> {
      /* the fake emits synchronously, so there is nothing to drain */
    }
    close(): void {
      /* nothing to release */
    }
  }

  class FakeVideoFrame {
    timestamp: number
    duration: number
    constructor(_source: unknown, init: { timestamp: number; duration: number }) {
      this.timestamp = init.timestamp
      this.duration = init.duration
    }
    close(): void {
      /* nothing to release */
    }
  }

  return {
    VideoEncoder: FakeVideoEncoder as unknown as typeof globalThis.VideoEncoder,
    VideoFrame: FakeVideoFrame as unknown as typeof globalThis.VideoFrame,
    createImageBitmap: (async () => ({ close: () => {} })) as unknown as typeof createImageBitmap,
    createCanvas: () =>
      ({
        getContext: () => ({ drawImage: vi.fn() })
      }) as unknown as OffscreenCanvas
  }
}

function sources(count: number, startMs = 1_781_329_148_845): SourceFrame[] {
  return Array.from({ length: count }, (_, i) => ({
    captureTsMs: startMs + i * 1000,
    jpeg: new Uint8Array([0xff, 0xd8, i])
  }))
}

describe('picking a codec', () => {
  it('prefers H.264, which measured smallest on this app’s own output', () => {
    // 60-frame 1280x720 run: 136 KB H.264 against 201 KB VP9.
    return expect(pickChunkCodec(1280, 720, fakeDeps())).resolves.toBe('avc1.42001f')
  })

  it('falls back in order', async () => {
    const deps = fakeDeps({ supported: (c) => c === 'vp09.00.10.08' })
    await expect(pickChunkCodec(1280, 720, deps)).resolves.toBe('vp09.00.10.08')
  })

  it('returns null when the machine can encode none of them', async () => {
    // A real outcome, not an error: such a machine simply keeps its JPEGs.
    const deps = fakeDeps({ supported: () => false })
    await expect(pickChunkCodec(1280, 720, deps)).resolves.toBeNull()
  })

  it('treats a codec string that throws as unsupported', async () => {
    const deps = fakeDeps()
    deps.VideoEncoder = {
      isConfigSupported: async (c: { codec: string }) => {
        if (c.codec !== 'vp8') throw new TypeError('unrecognised codec')
        return { supported: true, config: c }
      }
    } as unknown as typeof globalThis.VideoEncoder
    await expect(pickChunkCodec(1280, 720, deps)).resolves.toBe('vp8')
  })
})

describe('encoding a run', () => {
  it('produces a chunk that parses back to the same frames', async () => {
    const frames = sources(12)
    const bytes = await encodeFramesToChunk({
      width: 1280,
      height: 720,
      frames,
      deps: fakeDeps()
    })
    const decoded = decodeChunk(bytes)
    expect(decoded.codec).toBe('avc1.42001f')
    expect(decoded.width).toBe(1280)
    expect(decoded.height).toBe(720)
    expect(decoded.frames).toHaveLength(12)
    expect(decoded.frames.map((f) => f.captureTsMs)).toEqual(frames.map((f) => f.captureTsMs))
  })

  it('makes exactly the first frame a key frame', async () => {
    const calls: EncodeCall[] = []
    await encodeFramesToChunk({
      width: 640,
      height: 480,
      frames: sources(8),
      deps: fakeDeps({ calls })
    })
    expect(calls.map((c) => c.keyFrame)).toEqual([
      true,
      false,
      false,
      false,
      false,
      false,
      false,
      false
    ])
  })

  it('derives presentation timestamps from the index, not the capture clock', async () => {
    // macOS derived them from a live capture rate and a mid-chunk rate change
    // made a later frame's timestamp fall below an earlier one, which the writer
    // rejects as non-monotonic. Here the source timestamps deliberately jump
    // around and the encoded timeline stays strictly increasing.
    const calls: EncodeCall[] = []
    const jumpy: SourceFrame[] = [
      { captureTsMs: 5_000, jpeg: new Uint8Array([1]) },
      { captureTsMs: 1_000, jpeg: new Uint8Array([2]) },
      { captureTsMs: 90_000, jpeg: new Uint8Array([3]) }
    ]
    await encodeFramesToChunk({ width: 640, height: 480, frames: jumpy, deps: fakeDeps({ calls }) })
    const stamps = calls.map((c) => c.timestamp)
    expect(stamps).toEqual([0, 1_000_000, 2_000_000])
    // ...and the real capture times survive in the container instead.
    const bytes = await encodeFramesToChunk({
      width: 640,
      height: 480,
      frames: jumpy,
      deps: fakeDeps()
    })
    expect(decodeChunk(bytes).frames.map((f) => f.captureTsMs)).toEqual([5_000, 1_000, 90_000])
  })

  it('keeps the decoder description wherever the encoder attaches it', async () => {
    // Losing it makes the whole file undecodable, and it does not always ride
    // on the first chunk.
    const bytes = await encodeFramesToChunk({
      width: 640,
      height: 480,
      frames: sources(5),
      deps: fakeDeps({ describeAt: 3 })
    })
    expect([...decodeChunk(bytes).description]).toEqual([1, 100, 0, 31])
  })

  it('encodes for a codec that carries no description', async () => {
    const bytes = await encodeFramesToChunk({
      width: 640,
      height: 480,
      frames: sources(5),
      deps: fakeDeps({ describeAt: null })
    })
    expect(decodeChunk(bytes).description).toHaveLength(0)
  })
})

describe('what it refuses to hand back', () => {
  it('throws when the encoder returns fewer frames than it was given', async () => {
    // THE property of this file. The caller deletes the source JPEGs on
    // success, so a chunk holding 5 of 10 frames would take the other 5 with it.
    await expect(
      encodeFramesToChunk({
        width: 640,
        height: 480,
        frames: sources(10),
        deps: fakeDeps({ emitOnly: 5 })
      })
    ).rejects.toThrow(/returned 5 frames for 10 inputs/)
  })

  it('propagates an encoder error instead of returning a partial chunk', async () => {
    await expect(
      encodeFramesToChunk({
        width: 640,
        height: 480,
        frames: sources(10),
        deps: fakeDeps({ errorAt: 4 })
      })
    ).rejects.toThrow(/fake encoder failed/)
  })

  it('stops feeding frames once the encoder has errored', async () => {
    const calls: EncodeCall[] = []
    await encodeFramesToChunk({
      width: 640,
      height: 480,
      frames: sources(10),
      deps: fakeDeps({ errorAt: 2, calls })
    }).catch(() => undefined)
    // It notices before the next encode rather than pushing all ten in.
    expect(calls.length).toBeLessThan(10)
  })

  it('refuses when no codec is available', async () => {
    await expect(
      encodeFramesToChunk({
        width: 640,
        height: 480,
        frames: sources(9),
        deps: fakeDeps({ supported: () => false })
      })
    ).rejects.toThrow(ChunkEncodeError)
  })

  it('refuses an empty run', async () => {
    await expect(
      encodeFramesToChunk({ width: 640, height: 480, frames: [], deps: fakeDeps() })
    ).rejects.toThrow(/nothing to encode/)
  })
})

describe('configuration', () => {
  it('targets a bitrate high enough that a busy minute is not smeared', () => {
    // Set as a ceiling, not a size: the same run measured 136 KB at both 400
    // and 150 kbps, because near-identical screens have no more information in
    // them to spend the budget on.
    expect(CHUNK_BITRATE).toBe(400_000)
  })
})
