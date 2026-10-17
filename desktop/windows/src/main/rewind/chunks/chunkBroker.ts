/**
 * Getting an encode done, from a process that cannot encode.
 *
 * The compactor runs in main, where there is no `VideoEncoder`. The renderer
 * has one. This is the request/response channel between them, and it is the
 * only reason compaction is asynchronous at all.
 *
 * Reads do not come through here. A chunk-backed frame is decoded by the
 * renderer that wants to display it, which asks main for the chunk's bytes and
 * runs its own decoder — because the cursor that makes scrubbing linear has to
 * live next to the thing doing the scrubbing to be worth anything. Encoding has
 * no such locality: it happens once, in the background, for a file nobody is
 * waiting on.
 */

import type { WebContents } from 'electron'

/** A single chunk is one encode; a slow machine still finishes well inside this. */
export const ENCODE_TIMEOUT_MS = 120_000

export type EncodeRequest = {
  requestId: string
  width: number
  height: number
  frames: { captureTsMs: number; jpeg: Uint8Array }[]
}

export type EncodeResponse =
  | { requestId: string; ok: true; bytes: Uint8Array }
  | { requestId: string; ok: false; error: string }

type Pending = {
  resolve: (bytes: Uint8Array) => void
  reject: (error: Error) => void
  timer: ReturnType<typeof setTimeout>
}

/**
 * Tracks in-flight encodes.
 *
 * Kept as a class with injected time and id sources so the whole protocol —
 * timeouts, a response for a request that already gave up, a renderer that goes
 * away mid-encode — is testable without Electron.
 */
export class ChunkEncodeBroker {
  private readonly pending = new Map<string, Pending>()
  private sequence = 0

  constructor(
    private readonly send: (request: EncodeRequest) => void,
    private readonly timeoutMs = ENCODE_TIMEOUT_MS
  ) {}

  get inFlight(): number {
    return this.pending.size
  }

  encode(input: Omit<EncodeRequest, 'requestId'>): Promise<Uint8Array> {
    const requestId = `chunk-${++this.sequence}`
    return new Promise<Uint8Array>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(requestId)
        reject(new Error(`chunk encode timed out after ${this.timeoutMs}ms`))
      }, this.timeoutMs)
      // Node keeps the process alive for a pending timer; a background
      // compaction must never be the reason the app will not quit.
      if (typeof timer.unref === 'function') timer.unref()
      this.pending.set(requestId, { resolve, reject, timer })
      try {
        this.send({ requestId, ...input })
      } catch (e) {
        this.settleWithError(requestId, e as Error)
      }
    })
  }

  /** Deliver a renderer's answer. Unknown ids are ignored, not thrown on. */
  settle(response: EncodeResponse): void {
    const entry = this.pending.get(response.requestId)
    // A response can arrive after its request timed out, or twice. Neither is
    // an error worth raising into an IPC handler; the request is simply over.
    if (!entry) return
    clearTimeout(entry.timer)
    this.pending.delete(response.requestId)
    if (response.ok) entry.resolve(response.bytes)
    else entry.reject(new Error(response.error))
  }

  private settleWithError(requestId: string, error: Error): void {
    const entry = this.pending.get(requestId)
    if (!entry) return
    clearTimeout(entry.timer)
    this.pending.delete(requestId)
    entry.reject(error)
  }

  /**
   * Fail everything in flight.
   *
   * Called when the renderer that was doing the encoding goes away. Without it
   * a compaction pass would sit on a promise nobody can resolve until the
   * timeout, holding its plan and its loaded JPEGs in memory the whole time.
   */
  abortAll(reason: string): void {
    const ids = [...this.pending.keys()]
    for (const id of ids) this.settleWithError(id, new Error(reason))
  }
}

/**
 * The renderer that should do the encoding.
 *
 * Any live, non-destroyed window will do — the work needs a codec, not a
 * particular page. Returns null when the app has no window open, in which case
 * compaction simply does not run this pass.
 */
export function pickEncodeTarget(candidates: WebContents[]): WebContents | null {
  for (const contents of candidates) {
    if (!contents.isDestroyed() && !contents.isCrashed()) return contents
  }
  return null
}
