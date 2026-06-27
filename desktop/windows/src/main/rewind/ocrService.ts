import { readFile } from 'fs/promises'
import { powerMonitor } from 'electron'
import { helperProcess } from '../ocr/helperProcess'
import { unindexedRewindFrames, setRewindFrameOcr } from '../ipc/db'

const BACKFILL_INTERVAL_MS = 4000
const BATCH = 10 // match macOS batchSize = 10
const FRAME_THROTTLE_MS = 100 // match macOS Task.sleep(nanoseconds: 100_000_000)

let timer: NodeJS.Timeout | null = null
let running = false

async function backfill(): Promise<void> {
  if (running) return
  // Skip on battery — mirrors macOS PowerMonitor.cachedBatteryState() gate in
  // RewindIndexer.backfillUnindexedScreenshots(). OCR is CPU-heavy; only run on AC.
  if (powerMonitor.isOnBatteryPower()) return
  running = true
  try {
    const frames = unindexedRewindFrames(BATCH)
    for (const f of frames) {
      // Check battery mid-batch to abort immediately if unplugged, matching macOS exactly
      if (powerMonitor.isOnBatteryPower()) break
      if (f.id == null) continue
      let jpeg: Buffer
      try {
        jpeg = await readFile(f.imagePath) // async — never blocks the event loop
      } catch {
        setRewindFrameOcr(f.id, '') // image gone; mark indexed so we stop retrying
        continue
      }
      const result = await helperProcess.ocr(jpeg)
      setRewindFrameOcr(f.id, result.ok ? result.fullText : '')
      // Throttle between frames to avoid hogging CPU — mirrors macOS 100ms sleep.
      await new Promise<void>((r) => setTimeout(r, FRAME_THROTTLE_MS))
    }
  } finally {
    running = false
  }
}

export function startRewindOcr(): void {
  if (timer) clearInterval(timer)
  timer = setInterval(() => void backfill(), BACKFILL_INTERVAL_MS)
}
