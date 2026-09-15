/**
 * Tracks which captured audio actually reached the transcription socket, and
 * turns the parts that did not into write-ahead-log chunks. Port of the
 * `_chunk` algorithm in Flutter `services/wals/local_wal_sync.dart`.
 *
 * Two rules from the source carry the design:
 *  - Frames are judged only once they are older than a delay, because a frame
 *    fed a moment ago may still be on its way to a socket that is connecting.
 *  - A stretch of audio is only worth storing when enough of it was missed;
 *    a couple of dropped chunks around a reconnect are not a lost recording.
 *
 * The Flutter version counts BLE frames because that is its capture unit. The
 * desktop feeds PCM chunks of varying length, so the same thresholds are
 * expressed in milliseconds of audio, which is what the rules mean.
 *
 * One deliberate difference: the source applies its loss threshold to whatever
 * happens to be judgeable when its 75 second timer fires, so the same outage
 * stored or discarded depending on the polling cadence. Here a window is only
 * emitted once a full chunk of audio is judgeable (or on drain), which makes
 * the outcome identical whether the caller polls every second or every minute.
 */

import {
  WAL_CHUNK_SECONDS,
  WAL_LOSS_THRESHOLD_SECONDS,
  WAL_NEW_FRAME_SYNC_DELAY_SECONDS
} from '../../shared/wal'

/** What happened to one fed chunk of audio. */
export type FrameDisposition =
  /** Handed to an open socket. */
  | 'sent'
  /** Held for a socket that is still connecting; resolves later. */
  | 'buffered'
  /** Never reached the backend. */
  | 'missed'

export interface CaptureFrame {
  bytes: Uint8Array
  /** Capture time, epoch milliseconds. */
  capturedAtMs: number
  /** Audio duration this chunk represents. */
  durationMs: number
  disposition: FrameDisposition
}

export interface WalChunk {
  frames: CaptureFrame[]
  /** Capture start, unix SECONDS: the timestamp the upload filename carries. */
  timerStart: number
  /** Total audio duration in seconds (rounded down, at least 1). */
  seconds: number
  totalFrames: number
  /** Leading run of frames the socket already took. */
  syncedFrameOffset: number
  /** True when every frame reached the backend, so nothing needs uploading. */
  fullySynced: boolean
  byteLength: number
}

export interface FrameLedgerOptions {
  now: () => number
  /** Store every chunk, even fully-synced ones (the unlimited-storage pref). */
  storeEverything?: boolean
  /** Bounds memory when the socket is down for a long time. */
  maxBufferedMs?: number
}

const DEFAULT_MAX_BUFFERED_MS = 5 * 60_000

export class WalFrameLedger {
  private frames: CaptureFrame[] = []
  private readonly options: Required<FrameLedgerOptions>

  constructor(options: FrameLedgerOptions) {
    this.options = {
      now: options.now,
      storeEverything: options.storeEverything ?? false,
      maxBufferedMs: options.maxBufferedMs ?? DEFAULT_MAX_BUFFERED_MS
    }
  }

  get bufferedFrameCount(): number {
    return this.frames.length
  }

  get bufferedMs(): number {
    return this.frames.reduce((sum, f) => sum + f.durationMs, 0)
  }

  /** Records one fed chunk of audio and how it was handled. */
  push(frame: CaptureFrame): void {
    this.frames.push(frame)
  }

  /**
   * Resolves frames that were buffered pre-connect. The socket flushes them on
   * open, so they did reach the backend; a cap-evicted or abandoned buffer did
   * not. Applies to the oldest buffered frames first, matching the order the
   * socket flushes them in.
   */
  resolveBuffered(disposition: 'sent' | 'missed', count?: number): number {
    let remaining = count ?? Number.POSITIVE_INFINITY
    let resolved = 0
    for (const frame of this.frames) {
      if (remaining <= 0) break
      if (frame.disposition !== 'buffered') continue
      frame.disposition = disposition
      remaining -= 1
      resolved += 1
    }
    return resolved
  }

  /**
   * Emits chunks for audio old enough to judge. Frames newer than the delay
   * stay behind for the next pass; a buffered frame is treated as still in
   * flight and is never judged.
   */
  chunk(): WalChunk[] {
    if (this.frames.length === 0) return []
    const pivotMs = this.options.now() - WAL_NEW_FRAME_SYNC_DELAY_SECONDS * 1000

    let judged = 0
    while (judged < this.frames.length) {
      const frame = this.frames[judged]
      if (frame.capturedAtMs + frame.durationMs > pivotMs) break
      if (frame.disposition === 'buffered') break
      judged += 1
    }
    // Long outages must not grow the buffer without bound; past the cap the
    // oldest audio is judged even though it is still inside the delay.
    if (judged === 0 && this.bufferedMs > this.options.maxBufferedMs) {
      judged = this.frames.findIndex((f) => f.disposition === 'buffered')
      if (judged < 0) judged = this.frames.length
    }
    if (judged === 0) return []

    const budgetMs = WAL_CHUNK_SECONDS * 1000
    const groups = splitByDuration(this.frames.slice(0, judged), budgetMs)
    const chunks: WalChunk[] = []
    let consumed = 0
    for (const group of groups) {
      const groupMs = group.reduce((sum, f) => sum + f.durationMs, 0)
      // A partial window stays behind: judging it now would measure the loss
      // threshold against a slice instead of a window, so a long outage sliced
      // finely enough would be discarded a little at a time.
      if (groupMs < budgetMs) break
      consumed += group.length
      const chunk = buildChunk(group)
      if (chunk === null) continue
      if (this.shouldStore(group)) chunks.push(chunk)
    }
    if (consumed > 0) this.frames.splice(0, consumed)
    return chunks
  }

  private shouldStore(group: CaptureFrame[]): boolean {
    if (this.options.storeEverything) return true
    const missedMs = group
      .filter((f) => f.disposition === 'missed')
      .reduce((sum, f) => sum + f.durationMs, 0)
    return missedMs >= WAL_LOSS_THRESHOLD_SECONDS * 1000
  }

  /**
   * Emits whatever is left regardless of the delay or the window size (session
   * end, shutdown). Any missed audio counts here: at the end of a session there
   * is no later pass that could gather more of it.
   */
  drain(): WalChunk[] {
    if (this.frames.length === 0) return []
    const remaining = this.frames.splice(0, this.frames.length)
    const chunks: WalChunk[] = []
    for (const group of splitByDuration(remaining, WAL_CHUNK_SECONDS * 1000)) {
      const chunk = buildChunk(group)
      if (chunk === null) continue
      const missedMs = group
        .filter((f) => f.disposition === 'missed')
        .reduce((sum, f) => sum + f.durationMs, 0)
      if (this.options.storeEverything || missedMs > 0) chunks.push(chunk)
    }
    return chunks
  }

  reset(): void {
    this.frames = []
  }
}

/** Splits a run of frames into groups no longer than the chunk budget, so one
 *  long outage becomes several files rather than one unbounded upload. */
function splitByDuration(frames: CaptureFrame[], budgetMs: number): CaptureFrame[][] {
  const groups: CaptureFrame[][] = []
  let current: CaptureFrame[] = []
  let currentMs = 0
  for (const frame of frames) {
    if (current.length > 0 && currentMs + frame.durationMs > budgetMs) {
      groups.push(current)
      current = []
      currentMs = 0
    }
    current.push(frame)
    currentMs += frame.durationMs
  }
  if (current.length > 0) groups.push(current)
  return groups
}

function buildChunk(frames: CaptureFrame[]): WalChunk | null {
  if (frames.length === 0) return null
  let syncedFrameOffset = 0
  for (const frame of frames) {
    if (frame.disposition === 'sent') syncedFrameOffset += 1
    else break
  }
  const totalMs = frames.reduce((sum, f) => sum + f.durationMs, 0)
  const byteLength = frames.reduce((sum, f) => sum + f.bytes.byteLength, 0)
  return {
    frames,
    timerStart: Math.floor(frames[0].capturedAtMs / 1000),
    seconds: Math.max(1, Math.floor(totalMs / 1000)),
    totalFrames: frames.length,
    syncedFrameOffset,
    fullySynced: frames.every((f) => f.disposition === 'sent'),
    byteLength
  }
}
