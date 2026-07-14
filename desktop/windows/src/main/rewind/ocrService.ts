import { readFileSync } from 'fs'
import { helperProcess } from '../ocr/helperProcess'
import { unindexedRewindFrames, setRewindFrameOcr } from '../ipc/db'

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
        setRewindFrameOcr(f.id, '') // image gone; mark indexed so we stop retrying
        continue
      }
      const result = await helperProcess.ocr(jpeg)
      // Persist per-line boxes (Track 4) with the flattened text for the overlay.
      setRewindFrameOcr(
        f.id,
        result.ok ? result.fullText : '',
        result.ok ? JSON.stringify(result.lines) : null
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
