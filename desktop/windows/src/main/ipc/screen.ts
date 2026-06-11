import { ipcMain, desktopCapturer } from 'electron'
import { readFile } from 'fs/promises'
import { helperProcess } from '../ocr/helperProcess'
import { getPrimarySourceId } from '../rewind/sourceId'
import { getCurrentScreen, screenCacheFresh } from '../rewind/currentScreen'
import { latestRewindFrame } from './db'

// Overall cap for a single read. The fast path (latest Rewind frame) is near-
// instant; this is the backstop for the desktopCapturer fallback so a wedged
// capture can never hang the chat send.
const READ_TIMEOUT_MS = 4500

// Last-resort: capture the primary screen via desktopCapturer and OCR it. Slow
// (getSources can take seconds) and would include Omi's own window, so it's only
// used when Rewind has no frame yet (capture just enabled / disabled).
async function desktopCapturerOcr(): Promise<string> {
  try {
    const primaryId = await getPrimarySourceId().catch(() => null)
    const sources = await desktopCapturer.getSources({
      types: ['screen'],
      thumbnailSize: { width: 1920, height: 1080 }
    })
    const source = (primaryId ? sources.find((s) => s.id === primaryId) : undefined) ?? sources[0]
    if (!source || source.thumbnail.isEmpty()) return ''
    const res = await helperProcess.ocr(source.thumbnail.toJPEG(80))
    return res.ok ? res.fullText : ''
  } catch {
    return ''
  }
}

// Read "what's on screen right now" as OCR text. The FAST path is the hot in-memory
// cache (currentScreen), kept ~1s fresh in the background by the capture pipeline —
// an instant read, which is what makes the chat feel like it's looking live. The
// cold-start fallbacks below only run before the cache has been seeded (capture just
// enabled / app just started): the latest stored frame's OCR, then a one-off
// desktopCapturer grab as a last resort.
async function readScreenText(): Promise<string> {
  const cached = getCurrentScreen()
  if (cached.text && cached.text.trim() && screenCacheFresh(Date.now())) {
    console.log(
      `[screen:readNow] cache hit ${Math.round((Date.now() - cached.ts) / 1000)}s old, ${cached.text.length} chars`
    )
    return cached.text
  }
  // Seeded this session but stale (capture paused on idle/lock/excluded-app) — don't
  // pass off old text as the screen "right now"; send nothing this message.
  if (cached.ts !== 0) {
    console.log(
      `[screen:readNow] stale cache ${Math.round((Date.now() - cached.ts) / 1000)}s old; skipping (capture paused)`
    )
    return ''
  }

  // Cold cache — never seeded this session — seed from the most-recent stored frame's OCR if present.
  const frame = latestRewindFrame()
  if (frame?.ocrText && frame.ocrText.trim()) {
    console.log(`[screen:readNow] cold cache; latest frame OCR ${frame.ocrText.length} chars`)
    return frame.ocrText
  }
  // The stored frame exists but isn't OCR'd yet — OCR it once to bootstrap.
  if (frame) {
    try {
      const jpeg = await readFile(frame.imagePath)
      const res = await helperProcess.ocr(jpeg)
      if (res.ok) return res.fullText
    } catch {
      /* fall through to desktopCapturer */
    }
  }
  // No usable Rewind frame at all (capture off / just started) — last resort.
  const text = await desktopCapturerOcr()
  console.log(`[screen:readNow] cold cache; desktopCapturer fallback ${text.length} chars`)
  return text
}

export function registerScreenHandlers(): void {
  ipcMain.handle('screen:readNow', async () =>
    Promise.race([
      readScreenText(),
      new Promise<string>((resolve) => setTimeout(() => resolve(''), READ_TIMEOUT_MS))
    ])
  )
}
