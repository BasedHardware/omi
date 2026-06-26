import { desktopCapturer, screen, webContents, powerMonitor } from 'electron'
import { writeFileSync, mkdirSync } from 'fs'
import { join } from 'path'
import { settings } from '../settings'
import { dhash, hammingDistance, DHASH_SAME_SCREEN_THRESHOLD } from './dhash'
import { ocrService } from './ocr'
import { insertFrame, setFrameOcr, pruneOlderThan, rewindRoot, stats } from './store'

// The Rewind capture loop, mirroring ProactiveAssistantsPlugin/RewindModels defaults:
// 3 s cadence, dHash dedup (<= 5 bits = same screen), JPEG q80.
// Capped at 2560 px because Windows.Media.Ocr rejects very large bitmaps.

const MAX_CAPTURE_DIMENSION = 2560
const JPEG_QUALITY = 80

let timer: NodeJS.Timeout | null = null
let lastHash: bigint | null = null
let capturing = false
let lastPrune = 0
let stopped = false

function day(ts: number): string {
  const d = new Date(ts)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

function broadcastStatus(): void {
  const s = stats()
  const payload = { ...s, ocrPending: ocrService.pending, capturing }
  for (const wc of webContents.getAllWebContents()) {
    if (!wc.isDestroyed()) wc.send('rewind:status', payload)
  }
}

async function captureOnce(): Promise<void> {
  if (powerMonitor.getSystemIdleState(60) === 'locked') return
  const display = screen.getPrimaryDisplay()
  const { width, height } = display.size
  const scale = Math.min(1, MAX_CAPTURE_DIMENSION / Math.max(width, height))
  const sources = await desktopCapturer.getSources({
    types: ['screen'],
    thumbnailSize: { width: Math.round(width * scale), height: Math.round(height * scale) }
  })
  const source = sources.find((s) => s.display_id === String(display.id)) ?? sources[0]
  if (!source || source.thumbnail.isEmpty()) return

  const img = source.thumbnail
  const hash = dhash(img)
  if (lastHash !== null && hammingDistance(hash, lastHash) <= DHASH_SAME_SCREEN_THRESHOLD) return
  lastHash = hash

  const ts = Date.now()
  const dayStr = day(ts)
  const dir = join(rewindRoot(), dayStr)
  mkdirSync(dir, { recursive: true })
  const time = new Date(ts)
  const fileName = `${String(time.getHours()).padStart(2, '0')}${String(time.getMinutes()).padStart(2, '0')}${String(
    time.getSeconds()
  ).padStart(2, '0')}_${String(ts % 1000).padStart(3, '0')}.jpg`
  const filePath = join(dir, fileName)
  const jpeg = img.toJPEG(JPEG_QUALITY)
  writeFileSync(filePath, jpeg)
  const id = insertFrame(ts, dayStr, filePath, jpeg.byteLength)

  void ocrService.recognize(filePath).then((text) => {
    if (text) setFrameOcr(id, text)
    broadcastStatus()
  })

  if (ts - lastPrune > 6 * 3600 * 1000) {
    lastPrune = ts
    pruneOlderThan(settings.get().retentionDays)
  }
  broadcastStatus()
}

function loop(): void {
  if (timer) clearTimeout(timer)
  if (stopped) return
  const s = settings.get()
  if (!s.rewindEnabled) {
    capturing = false
    broadcastStatus()
    return
  }
  capturing = true
  timer = setTimeout(async () => {
    if (stopped) return
    try {
      await captureOnce()
    } catch (e) {
      console.error('rewind: capture failed', e)
    }
    loop()
  }, Math.max(1000, s.rewindIntervalMs))
}

export function startRewindEngine(): void {
  settings.on('changed', (next, prev) => {
    if (next.rewindEnabled !== prev.rewindEnabled || next.rewindIntervalMs !== prev.rewindIntervalMs) loop()
  })
  loop()
}

export function isCapturing(): boolean {
  return capturing
}

// Stop the capture loop on app quit so no screenshots, JPEG encodes, or DB writes
// fire during shutdown. Idempotent.
export function stopRewindEngine(): void {
  stopped = true
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
  capturing = false
}

export function getRewindStatus(): ReturnType<typeof stats> & { ocrPending: number; capturing: boolean } {
  return { ...stats(), ocrPending: ocrService.pending, capturing }
}
