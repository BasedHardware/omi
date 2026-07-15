import { readFileSync } from 'fs'
import { helperProcess } from '../ocr/helperProcess'
import { unindexedRewindFrames } from '../ipc/db'
import { persistFrameOcr } from './ocrPersist'

const BACKFILL_INTERVAL_MS = 4000
const BATCH = 5

let timer: NodeJS.Timeout | null = null
let running = false

async function backfill(): Promise<void> {
  if (running) return
  running = true
  try {
    const frames = unindexedRewindFrames(BATCH)
    for (const f of frames) {
      if (f.id == null) continue
      // The app context stored on the frame at capture time; it is embedded with
      // the OCR text (see ocrPersist.FrameContext), so this sweep and the capture
      // hot path produce byte-identical content for the same screen.
      const context = { app: f.app, windowTitle: f.windowTitle }
      let jpeg: Buffer
      try {
        jpeg = readFileSync(f.imagePath)
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
  if (timer) clearInterval(timer)
  timer = setInterval(() => void backfill(), BACKFILL_INTERVAL_MS)
}
