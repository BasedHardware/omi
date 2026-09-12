/**
 * Turning a run of JPEGs into one inter-frame-compressed chunk.
 *
 * This runs in the renderer because that is where WebCodecs lives: Electron's
 * main process is Node, and Node has no `VideoEncoder`. Main owns every file
 * read and write (as it already does for JPEGs), hands the bytes over, and gets
 * chunk bytes back — so adding compaction does not give the renderer filesystem
 * access it did not have.
 *
 * The codec objects are injected rather than reached for globally. Everything
 * interesting here is orchestration — frame order, where the key frame goes,
 * what happens when the encoder errors halfway — and none of it needs a real
 * H.264 encoder to be worth testing. The real codec is exercised end to end by
 * the Electron e2e (`scripts/run-rewind-chunk-e2e.mjs`).
 */

import {
  encodeChunk,
  type ChunkContents,
  type ChunkFrame
} from '../../../main/rewind/chunks/chunkFormat'

/**
 * Codec preference order.
 *
 * H.264 first because it was measurably the smallest on this app's own capture
 * output: on a 60-frame 1280x720 run, 136 KB against VP9's 201 KB. VP9 is the
 * fallback rather than the default despite scoring higher on PSNR, because the
 * fidelity both reach is far past what a screen recall thumbnail needs and the
 * point of the feature is the bytes.
 */
export const CHUNK_CODEC_PREFERENCE = ['avc1.42001f', 'vp09.00.10.08', 'vp8'] as const

/**
 * Encoder target rate.
 *
 * A rate controller spends its budget whether or not the content needs it, so
 * this number is a ceiling on a pathological chunk rather than the size of a
 * normal one: the same 60-frame run measured 136 KB at 400 kbps and 136 KB at
 * 150 kbps, because near-identical consecutive screens do not have 400 kbps of
 * information in them. It is set high enough that a genuinely busy minute
 * (video playback, fast scrolling) is not smeared.
 */
export const CHUNK_BITRATE = 400_000

/** Chunks are addressed by frame index; the nominal rate only sets timestamps. */
const NOMINAL_FPS = 1
const FRAME_DURATION_US = 1_000_000 / NOMINAL_FPS

export type SourceFrame = {
  captureTsMs: number
  /** The frame's stored JPEG bytes. */
  jpeg: Uint8Array
}

export type EncodeChunkOptions = {
  width: number
  height: number
  frames: SourceFrame[]
  /** Overrides for tests; production passes nothing and uses the globals. */
  deps?: Partial<EncoderDeps>
}

export type EncoderDeps = {
  VideoEncoder: typeof globalThis.VideoEncoder
  VideoFrame: typeof globalThis.VideoFrame
  createImageBitmap: typeof globalThis.createImageBitmap
  createCanvas: (width: number, height: number) => OffscreenCanvas
}

function defaultDeps(): EncoderDeps {
  return {
    VideoEncoder: globalThis.VideoEncoder,
    VideoFrame: globalThis.VideoFrame,
    // Bound, not referenced. `createImageBitmap` is a method on the global
    // object and throws "Illegal invocation" when called with `this` undefined,
    // which is exactly what happens once it is pulled out into a plain
    // property. Constructors above are unaffected because `new` supplies its
    // own receiver.
    createImageBitmap: globalThis.createImageBitmap?.bind(globalThis),
    createCanvas: (width, height) => new OffscreenCanvas(width, height)
  }
}

export class ChunkEncodeError extends Error {}

/**
 * Copy a WebCodecs buffer source into bytes we own.
 *
 * `decoderConfig.description` is an `AllowSharedBufferSource`: an ArrayBuffer, a
 * SharedArrayBuffer, or a view onto either. It is copied rather than referenced
 * because the encoder may reuse the underlying storage once the callback
 * returns, and the description has to outlive the encode to reach the file.
 */
function copyBufferSource(source: AllowSharedBufferSource): Uint8Array<ArrayBuffer> {
  const view = ArrayBuffer.isView(source)
    ? new Uint8Array(source.buffer as ArrayBufferLike, source.byteOffset, source.byteLength)
    : new Uint8Array(source as ArrayBufferLike)
  // Allocate our own storage and copy in, so the result is backed by a plain
  // ArrayBuffer regardless of which of the three shapes arrived.
  const copy = new Uint8Array(new ArrayBuffer(view.byteLength))
  copy.set(view)
  return copy
}

/**
 * The first codec in the preference order this machine can actually encode.
 *
 * Returns null when none is available, which is a real outcome — a machine with
 * no usable video encoder simply never compacts, and keeps its JPEGs.
 */
export async function pickChunkCodec(
  width: number,
  height: number,
  deps: EncoderDeps = defaultDeps()
): Promise<string | null> {
  for (const codec of CHUNK_CODEC_PREFERENCE) {
    try {
      const support = await deps.VideoEncoder.isConfigSupported({
        codec,
        width,
        height,
        bitrate: CHUNK_BITRATE,
        framerate: NOMINAL_FPS
      })
      if (support.supported) return codec
    } catch {
      // An unrecognised codec string throws rather than reporting unsupported.
      // Either way it is not usable; try the next one.
    }
  }
  return null
}

/**
 * Encode a planned run into chunk bytes.
 *
 * Throws rather than returning a short chunk: the caller is about to delete the
 * JPEGs these frames came from, and a chunk holding a prefix of them would take
 * the rest with it. Every failure path here leaves the source files untouched.
 */
export async function encodeFramesToChunk(options: EncodeChunkOptions): Promise<Uint8Array> {
  const deps = { ...defaultDeps(), ...options.deps }
  const { width, height, frames } = options
  if (frames.length === 0) throw new ChunkEncodeError('nothing to encode')

  const codec = await pickChunkCodec(width, height, deps)
  if (!codec) throw new ChunkEncodeError('no supported video encoder on this machine')

  const encoded: ChunkFrame[] = []
  let description = new Uint8Array()
  let encoderError: Error | null = null

  const encoder = new deps.VideoEncoder({
    output: (chunk, metadata) => {
      // The decoder description (avcC for H.264) arrives on metadata, usually
      // only with the first chunk. Losing it makes the file undecodable, so it
      // is captured from whichever chunk carries it.
      const config = metadata?.decoderConfig
      if (config?.description) description = copyBufferSource(config.description)
      const data = new Uint8Array(chunk.byteLength)
      chunk.copyTo(data)
      encoded.push({
        // Position in `encoded` is the frame's offset, and the encoder emits in
        // order, so the source frame at this index is the one this belongs to.
        captureTsMs: frames[encoded.length]?.captureTsMs ?? 0,
        isKeyFrame: chunk.type === 'key',
        data
      })
    },
    error: (e: Error) => {
      encoderError = e
    }
  })

  encoder.configure({
    codec,
    width,
    height,
    bitrate: CHUNK_BITRATE,
    framerate: NOMINAL_FPS,
    latencyMode: 'quality'
  })

  const canvas = deps.createCanvas(width, height)
  const context = canvas.getContext('2d')
  if (!context) throw new ChunkEncodeError('no 2d context for chunk encoding')

  try {
    for (let i = 0; i < frames.length; i++) {
      if (encoderError) throw encoderError
      const bitmap = await deps.createImageBitmap(
        new Blob([frames[i].jpeg as BlobPart], { type: 'image/jpeg' })
      )
      try {
        // Every frame is drawn to the chunk's fixed geometry. The planner only
        // groups frames that already share it, so this is a blit and not a
        // rescale — but doing it through the canvas means a row whose stored
        // width disagrees with its JPEG cannot produce a mis-sized VideoFrame.
        context.drawImage(bitmap, 0, 0, width, height)
      } finally {
        bitmap.close()
      }
      // Presentation timestamps are derived from the frame INDEX, not from the
      // capture clock. macOS derives them from a live capture rate and documents
      // what that cost: a mid-chunk rate change made a later frame's timestamp
      // fall below an already-appended one, which the writer rejects as
      // non-monotonic, dropping frames and sometimes the whole chunk
      // (VideoChunkEncoder.swift). An index is monotonic by construction, and
      // the real capture time is carried per record in the container instead.
      const frame = new deps.VideoFrame(canvas, {
        timestamp: i * FRAME_DURATION_US,
        duration: FRAME_DURATION_US
      })
      try {
        encoder.encode(frame, { keyFrame: i === 0 })
      } finally {
        frame.close()
      }
    }

    await encoder.flush()
    if (encoderError) throw encoderError
  } finally {
    try {
      encoder.close()
    } catch {
      // A closed-on-error encoder throws again on close; the original error is
      // the one worth reporting.
    }
  }

  if (encoded.length !== frames.length) {
    throw new ChunkEncodeError(
      `encoder returned ${encoded.length} frames for ${frames.length} inputs`
    )
  }

  const contents: ChunkContents = { codec, description, width, height, frames: encoded }
  return encodeChunk(contents)
}
