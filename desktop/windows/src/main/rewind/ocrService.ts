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
      let jpeg: Buffer
      try {
        jpeg = readFileSync(f.imagePath)
      } catch {
        persistFrameOcr(f.id, '') // image gone; mark indexed so we stop retrying
        continue
      }
      const result = await helperProcess.ocr(jpeg)
      // Persists the text + per-line boxes AND queues it for semantic indexing —
      // see ocrPersist.ts for why those two are deliberately fused.
      persistFrameOcr(f.id, result.ok ? result.fullText : '', result.ok ? result.lines : null)
    }
  } finally {
    running = false
  }
}

export function startRewindOcr(): void {
  if (timer) clearInterval(timer)
  timer = setInterval(() => void backfill(), BACKFILL_INTERVAL_MS)
}
