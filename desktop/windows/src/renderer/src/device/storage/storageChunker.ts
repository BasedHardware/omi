/**
 * Groups drained frames into the chunks that become write-ahead-log files.
 *
 * Device storage hands back a long run of frames with occasional capture times.
 * Uploading that as one file would be a single huge upload and a single point
 * of failure, so it is cut into bounded chunks, each stamped with the capture
 * time that applies to its first frame.
 *
 * Ported from the chunking in Flutter `ring_storage_sync.dart` and
 * `storage_sync.dart`, which both use a 180 second chunk for stored audio (the
 * live path uses 60; stored audio is uploaded in bigger pieces because it is
 * not racing a socket).
 */

/** Seconds of stored audio per uploaded file. */
export const STORED_CHUNK_SECONDS = 180

export interface DrainedFrame {
  bytes: Uint8Array
  /** Capture time for this frame, epoch seconds. */
  epochSeconds: number
}

export interface DrainedChunk {
  frames: Uint8Array[]
  /** Capture start, epoch seconds: the timestamp the upload filename carries. */
  startEpochSeconds: number
  seconds: number
  byteLength: number
}

export interface ChunkerOptions {
  framesPerSecond: number
  chunkSeconds?: number
}

/**
 * Accumulates frames and emits bounded chunks. A gap in capture time also ends
 * a chunk: two runs recorded an hour apart are two recordings, and merging them
 * would produce one file whose timestamp is wrong for most of its audio.
 */
export class StorageChunker {
  private frames: DrainedFrame[] = []
  private readonly framesPerSecond: number
  private readonly chunkSeconds: number

  constructor(options: ChunkerOptions) {
    this.framesPerSecond = Math.max(1, options.framesPerSecond)
    this.chunkSeconds = options.chunkSeconds ?? STORED_CHUNK_SECONDS
  }

  get pendingFrameCount(): number {
    return this.frames.length
  }

  /** Adds frames and returns any chunks that are now complete. */
  push(frames: DrainedFrame[]): DrainedChunk[] {
    const complete: DrainedChunk[] = []
    for (const frame of frames) {
      const previous = this.frames[this.frames.length - 1]
      if (previous !== undefined && this.startsNewRecording(previous, frame)) {
        const chunk = this.take()
        if (chunk !== null) complete.push(chunk)
      }
      this.frames.push(frame)
      if (this.frames.length >= this.chunkSeconds * this.framesPerSecond) {
        const chunk = this.take()
        if (chunk !== null) complete.push(chunk)
      }
    }
    return complete
  }

  /** Emits whatever is left, however short. */
  flush(): DrainedChunk[] {
    const chunk = this.take()
    return chunk === null ? [] : [chunk]
  }

  reset(): void {
    this.frames = []
  }

  /**
   * A capture time that jumps forward by more than the audio between the two
   * frames means the device stopped and started again.
   */
  private startsNewRecording(previous: DrainedFrame, next: DrainedFrame): boolean {
    const drift = next.epochSeconds - previous.epochSeconds
    if (drift < 0) return true
    return drift > this.chunkSeconds
  }

  private take(): DrainedChunk | null {
    if (this.frames.length === 0) return null
    const frames = this.frames
    this.frames = []
    return {
      frames: frames.map((f) => f.bytes),
      startEpochSeconds: frames[0].epochSeconds,
      seconds: Math.max(1, Math.round(frames.length / this.framesPerSecond)),
      byteLength: frames.reduce((sum, f) => sum + f.bytes.byteLength, 0)
    }
  }
}

/**
 * Assigns a capture time to each frame in a payload. A payload carries one
 * record time plus optional embedded markers; frames between markers are spread
 * across the elapsed second so a chunk's duration reflects real time.
 */
export function stampFrames(
  frames: Uint8Array[],
  recordEpochSeconds: number,
  markers: Array<{ frameIndex: number; epochSeconds: number }>,
  framesPerSecond: number
): DrainedFrame[] {
  const perSecond = Math.max(1, framesPerSecond)
  const stamped: DrainedFrame[] = []
  let currentEpoch = recordEpochSeconds
  let sinceEpoch = 0
  let nextMarker = 0

  for (let i = 0; i < frames.length; i += 1) {
    while (nextMarker < markers.length && markers[nextMarker].frameIndex === i) {
      currentEpoch = markers[nextMarker].epochSeconds
      sinceEpoch = 0
      nextMarker += 1
    }
    stamped.push({
      bytes: frames[i],
      epochSeconds: currentEpoch + Math.floor(sinceEpoch / perSecond)
    })
    sinceEpoch += 1
  }
  return stamped
}
