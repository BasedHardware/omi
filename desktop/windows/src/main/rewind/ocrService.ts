import { helperProcess } from '../ocr/helperProcess'
import { unindexedRewindFrames } from '../ipc/db'
import { persistFrameOcr } from './ocrPersist'
import { rewindRoot } from './paths'
import { readRewindFrame } from './frameFile'

const BACKFILL_INTERVAL_MS = 4000
const BATCH = 5

let timer: NodeJS.Timeout | null = null
let running = false
// Whether an un-OCR'd frame MAY exist. The capture hot path OCRs almost every
// frame inline (marking it indexed=1); a frame only reaches this backlog sweep
// when the hot path skipped or failed it (see captureService.refreshCurrentScreen,
// which calls signalRewindOcrPending in exactly those cases). While this is false
// there is demonstrably nothing to do, so the 4s tick skips the DB read entirely —
// the mirror of embeddingService's queue-empty tick gate. Starts true so a
// pre-existing backlog from a previous session is drained on launch.
let pending = true

/** Wake the backlog sweep: an un-OCR'd frame may now exist. Cheap + idempotent;
 *  safe to call from the capture hot path. */
export function signalRewindOcrPending(): void {
  pending = true
}

async function backfill(): Promise<void> {
  if (running || !pending) return
  running = true
  // Clear optimistically BEFORE the query: a frame captured mid-sweep re-arms
  // `pending` via signalRewindOcrPending, so work is never lost by clearing early.
  pending = false
  try {
    const frames = unindexedRewindFrames(BATCH)
    // A full page means more may remain — keep sweeping on the next tick. A short
    // page drained the backlog, so stay gated until capture signals again.
    if (frames.length === BATCH) pending = true
    for (const f of frames) {
      if (f.id == null) continue
      // The app context stored on the frame at capture time; it is embedded with
      // the OCR text (see ocrPersist.FrameContext), so this sweep and the capture
      // hot path produce byte-identical content for the same screen.
      const context = { app: f.app, windowTitle: f.windowTitle }
      let jpeg: Buffer
      try {
        jpeg = await readRewindFrame(rewindRoot(), f.imagePath)
      } catch {
        persistFrameOcr(f.id, '', context) // image gone; mark indexed so we stop retrying
        continue
      }
      const result = await helperProcess.ocr(jpeg)
      // Persists the text + per-line boxes AND queues it for semantic indexing —
      // see ocrPersist.ts for why those two are deliberately fused.
      persistFrameOcr(
        f.id,
        result.ok ? result.fullText : '',
        context,
        result.ok ? result.lines : null
      )
    }
  } finally {
    running = false
  }
}

export function startRewindOcr(): void {
  // Drain any backlog left by a previous session on (re)start.
  pending = true
  if (timer) clearInterval(timer)
  timer = setInterval(() => void backfill(), BACKFILL_INTERVAL_MS)
}

/** Test seam: run one sweep synchronously and drive/inspect the pending latch. */
export const __rewindOcrTestHooks = {
  backfill,
  setPending: (v: boolean): void => {
    pending = v
  },
  getPending: (): boolean => pending
}
