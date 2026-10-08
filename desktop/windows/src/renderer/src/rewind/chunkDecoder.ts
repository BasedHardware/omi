/**
 * Reading one frame back out of a chunk.
 *
 * A chunk is inter-frame compressed, so frame *n* cannot be reached without
 * decoding everything before it. The consequence is the whole reason this file
 * has a cursor in it rather than a `decodeFrame(path, n)` function: opening a
 * fresh decoder per request makes a scrub quadratic, and macOS measured that
 * cost directly — 728 ms to walk an 18-frame chunk reopening each time, 59 ms
 * keeping the reader alive (`RewindVideoFrameCursor.swift`).
 *
 * The decision of when the live decoder can be reused is not here; it is a pure
 * state machine in `main/rewind/chunks/cursorPolicy.ts`, tested on its own. This
 * file is the part that needs a codec: it executes the plan that module returns.
 */

import { decodeChunk, type ChunkContents } from '../../../main/rewind/chunks/chunkFormat'
import {
  afterExhausted,
  afterRead,
  newCursor,
  planRead,
  type CursorState
} from '../../../main/rewind/chunks/cursorPolicy'

export type DecoderDeps = {
  VideoDecoder: typeof globalThis.VideoDecoder
  EncodedVideoChunk: typeof globalThis.EncodedVideoChunk
  createCanvas: (width: number, height: number) => OffscreenCanvas
}

function defaultDeps(): DecoderDeps {
  return {
    VideoDecoder: globalThis.VideoDecoder,
    EncodedVideoChunk: globalThis.EncodedVideoChunk,
    createCanvas: (width, height) => new OffscreenCanvas(width, height)
  }
}

export class ChunkDecodeError extends Error {}

/**
 * A live decode session over one chunk, parked before the next frame it will
 * produce.
 *
 * WebCodecs decoding is push/pull across a callback rather than a pull-only
 * tape, so this drains chunks into a queue and reads from it, where macOS calls
 * `copyNextSampleBuffer()`. The externally visible behaviour is the same: a
 * one-way tape that can serve any offset at or after where it is parked.
 */
class ChunkTape {
  private readonly decoded: VideoFrame[] = []
  private readonly decoder: VideoDecoder
  private failure: Error | null = null
  private fed = 0
  /**
   * Set once the stream has been flushed.
   *
   * `flush()` ends the decoder's current run: WebCodecs requires the next
   * `decode()` after it to be a key frame, so flushing between reads would
   * break the tape on the very next step ("A key frame is required after
   * configure() or flush()"). It is therefore only ever done at the end of the
   * chunk, when everything has been fed and there is nothing left to decode.
   */
  private flushed = false
  /** Resolved by the output callback, so a read can await progress. */
  private awaitingOutput: (() => void) | null = null

  private constructor(
    readonly chunkPath: string,
    private readonly contents: ChunkContents,
    private readonly deps: DecoderDeps
  ) {
    this.decoder = new deps.VideoDecoder({
      output: (frame) => {
        this.decoded.push(frame)
        this.awaitingOutput?.()
      },
      error: (e: Error) => {
        this.failure = e
        this.awaitingOutput?.()
      }
    })
    this.decoder.configure({
      codec: contents.codec,
      codedWidth: contents.width,
      codedHeight: contents.height,
      ...(contents.description.byteLength > 0 ? { description: contents.description } : {})
    })
  }

  static open(chunkPath: string, contents: ChunkContents, deps: DecoderDeps): ChunkTape {
    return new ChunkTape(chunkPath, contents, deps)
  }

  get frameCount(): number {
    return this.contents.frames.length
  }

  /**
   * Decode up to and including `offset`, returning that frame.
   *
   * Feeds only as far as it must. Frames before the target are decoded (they
   * have to be — they are the reference pictures) and released immediately,
   * so walking a chunk holds one frame at a time rather than all of them.
   */
  async advanceTo(offset: number): Promise<VideoFrame> {
    if (offset >= this.contents.frames.length) {
      throw new ChunkDecodeError(
        `frame ${offset} is past the end of ${this.chunkPath} (${this.contents.frames.length} frames)`
      )
    }
    while (this.fed <= offset) this.feedNext()

    // A decoder may hold frames back before emitting them, so reaching offset
    // can need more input than offset itself. Feed further chunks while any
    // remain, and only flush once there is nothing left to feed — after which
    // the tape is closed to new input, but by then everything is decoded.
    while (this.decoded.length <= offset && !this.failure) {
      if (await this.waitForOutput()) continue
      if (this.fed < this.contents.frames.length) {
        this.feedNext()
        continue
      }
      if (this.flushed) break
      await this.decoder.flush()
      this.flushed = true
    }
    if (this.failure) throw this.failure

    if (this.decoded.length <= offset) {
      throw new ChunkDecodeError(
        `decoder produced ${this.decoded.length} frames, wanted ${offset + 1}`
      )
    }
    // Release everything before the target; they were only needed as references.
    for (let i = 0; i < offset; i++) {
      const stale = this.decoded[i]
      if (stale) {
        stale.close()
        delete this.decoded[i]
      }
    }
    return this.decoded[offset]
  }

  /** Push the next encoded frame into the decoder. */
  private feedNext(): void {
    const frame = this.contents.frames[this.fed]
    this.decoder.decode(
      new this.deps.EncodedVideoChunk({
        type: frame.isKeyFrame ? 'key' : 'delta',
        // Synthesised from the index for the same reason the encoder does it:
        // it is monotonic by construction. The real capture time travels in the
        // container record, not in the codec's timeline.
        timestamp: this.fed * 1_000_000,
        data: frame.data
      })
    )
    this.fed++
  }

  /**
   * Wait briefly for the decoder to emit something.
   *
   * Returns true if it did. False means it is waiting for more input (or is
   * done), which the caller answers by feeding more or, as a last resort,
   * flushing. The timeout is what keeps a decoder that will never emit again
   * from hanging a read forever.
   */
  private waitForOutput(timeoutMs = 2000): Promise<boolean> {
    return new Promise<boolean>((resolve) => {
      let settled = false
      const done = (value: boolean): void => {
        if (settled) return
        settled = true
        this.awaitingOutput = null
        clearTimeout(timer)
        resolve(value)
      }
      const timer = setTimeout(() => done(false), timeoutMs)
      this.awaitingOutput = () => done(true)
    })
  }

  close(): void {
    for (const frame of this.decoded) frame?.close()
    this.decoded.length = 0
    this.awaitingOutput?.()
    try {
      this.decoder.close()
    } catch {
      // Already closed by an error callback.
    }
  }
}

/**
 * Serves frame reads from chunks, keeping one decoder alive between requests.
 *
 * Holds exactly one tape. A scrub through a chunk therefore costs one open plus
 * one decode step per frame; anything that jumps backwards or to another chunk
 * pays a reopen, which is what it would have paid anyway.
 */
export class ChunkFrameReader {
  private state: CursorState = newCursor()
  private tape: ChunkTape | null = null

  constructor(private readonly deps: DecoderDeps = defaultDeps()) {}

  /**
   * Decode one frame to JPEG bytes.
   *
   * `loadChunk` is injected so the reader never touches the filesystem: main
   * owns file access and hands the bytes over, exactly as it does for JPEGs.
   */
  async readFrame(
    chunkPath: string,
    frameOffset: number,
    loadChunk: (path: string) => Promise<Uint8Array>,
    quality = 0.82
  ): Promise<Blob> {
    const action = planRead(this.state, chunkPath, frameOffset)

    if (action.kind === 'reopen') {
      this.retire()
      const bytes = await loadChunk(chunkPath)
      const contents = decodeChunk(bytes)
      this.tape = ChunkTape.open(chunkPath, contents, this.deps)
    }
    const tape = this.tape
    if (!tape) throw new ChunkDecodeError('no chunk open')

    let frame: VideoFrame
    try {
      frame = await tape.advanceTo(frameOffset)
    } catch (e) {
      // A chunk registered in the database is always complete, so running off
      // the end means the row disagrees with the file rather than "not yet".
      this.state = afterExhausted(this.state)
      this.retire()
      throw e
    }

    const canvas = this.deps.createCanvas(frame.displayWidth, frame.displayHeight)
    const context = canvas.getContext('2d')
    if (!context) throw new ChunkDecodeError('no 2d context for chunk decoding')
    context.drawImage(frame, 0, 0)
    const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality })

    this.state = afterRead(this.state, action, frameOffset)
    return blob
  }

  /** Drop the live decoder. Safe at any time; the next read reopens. */
  retire(): void {
    this.tape?.close()
    this.tape = null
    this.state = newCursor()
  }
}
