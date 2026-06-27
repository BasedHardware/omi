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
      setRewindFrameOcr(f.id, result.ok ? result.fullText : '')
    }
  } finally {
    running = false
  }
}

export function startRewindOcr(): void {
  if (timer) clearInterval(timer)
  // A DB error inside backfill (e.g. SQLITE_BUSY from unindexedRewindFrames /
  // setRewindFrameOcr) would otherwise reject this fire-and-forget call and
  // recur as an unhandled rejection every interval.
  timer = setInterval(() => {
    backfill().catch((e) => console.warn('[rewind-ocr] backfill failed:', e))
  }, BACKFILL_INTERVAL_MS)
}
