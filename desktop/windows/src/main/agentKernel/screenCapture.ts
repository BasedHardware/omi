// Windows screen-capture backend for the `capture_screen` product tool.
//
// PORTS macOS' ScreenCaptureManager.captureScreen() (desktop/macos/
// FloatingControlBar/ScreenCaptureManager.swift): grab the display the user is
// looking at, write it to an image file, and return the file PATH — never the
// bytes. pi's built-in `Read` tool loads the image from that path, exactly as on
// Mac (see ChatToolExecutor.executeCaptureScreen → returns fileURL.path). Keeping
// the return contract a path is what lets Windows reuse pi's Read tool unchanged.
//
// Faithful choices, verified against the Swift:
//   • Display selection: Mac captures the display *under the mouse cursor*
//     (displayIDUnderMouse, falling back to the main display). We match that via
//     Electron's screen module, falling back to the primary source, then the first.
//   • Full-resolution: Mac captures at native Retina resolution. We size the
//     desktopCapturer thumbnail to the target display's pixel size (DIP × scale).
//   • Format: the Windows manifest advertises "the saved JPEG image", so we write
//     JPEG (nativeImage has no WebP encoder; Mac's WebP is a Mac-only detail, and
//     pi's Read tool loads JPEG all the same).
//
// A one-shot model-invoked capture is NOT the pathological polling the Rewind
// pipeline avoids (rewind/captureService.ts acquires frames in the renderer
// because *polling* desktopCapturer froze the system). A single occasional grab
// on a real tool call is the same shape as ipc/screen.ts's desktopCapturerOcr
// fallback, which this mirrors.

import { app, desktopCapturer, screen, type DesktopCapturerSource } from 'electron'
import { mkdirSync, readdirSync, statSync, unlinkSync, writeFileSync } from 'fs'
import { join } from 'path'
import { getPrimarySourceId } from '../rewind/sourceId'

const SCREENSHOT_DIR_NAME = 'chat-screenshots'
const FILE_PREFIX = 'screenshot-'
const FILE_EXT = '.jpg'
const JPEG_QUALITY = 80

// Mac leaves its screenshots in ~/Documents/Omi/Screenshots forever. We deviate
// lightly: prune our own siblings older than this so an occasional full-screen
// grab of potentially sensitive content does not accumulate unbounded on disk.
// The just-written file always survives (it is newer than the cutoff).
const PRUNE_AGE_MS = 60 * 60 * 1000

// Fallback capture size when the target display's pixel size can't be resolved —
// matches the desktopCapturerOcr fallback in ipc/screen.ts.
const DEFAULT_PIXEL_SIZE = { width: 1920, height: 1080 }

interface TargetDisplay {
  id: string
  pixelSize: { width: number; height: number }
}

/** The display under the mouse cursor, mirroring Mac's displayIDUnderMouse(). */
function cursorDisplay(): TargetDisplay | null {
  try {
    const point = screen.getCursorScreenPoint()
    const display = screen.getDisplayNearestPoint(point)
    if (!display) return null
    const scale = display.scaleFactor > 0 ? display.scaleFactor : 1
    return {
      id: String(display.id),
      pixelSize: {
        width: Math.max(1, Math.round(display.size.width * scale)),
        height: Math.max(1, Math.round(display.size.height * scale))
      }
    }
  } catch {
    return null
  }
}

/** Pick the source for the target display, else the primary source, else the first. */
async function pickSource(
  sources: DesktopCapturerSource[],
  target: TargetDisplay | null
): Promise<DesktopCapturerSource | null> {
  if (sources.length === 0) return null
  if (target) {
    const byDisplay = sources.find((s) => s.display_id === target.id)
    if (byDisplay) return byDisplay
  }
  const primaryId = await getPrimarySourceId().catch(() => null)
  const byPrimary = primaryId ? sources.find((s) => s.id === primaryId) : undefined
  return byPrimary ?? sources[0]
}

function screenshotsDir(): string {
  const dir = join(app.getPath('userData'), SCREENSHOT_DIR_NAME)
  mkdirSync(dir, { recursive: true })
  return dir
}

/** Best-effort delete of our own stale screenshots. Never throws. */
function pruneOldScreenshots(dir: string, nowMs: number): void {
  let entries: string[]
  try {
    entries = readdirSync(dir)
  } catch {
    return
  }
  for (const name of entries) {
    if (!name.startsWith(FILE_PREFIX) || !name.endsWith(FILE_EXT)) continue
    const full = join(dir, name)
    try {
      if (nowMs - statSync(full).mtimeMs > PRUNE_AGE_MS) unlinkSync(full)
    } catch {
      /* a sibling vanished or is locked — ignore. */
    }
  }
}

/**
 * Capture the screen under the cursor to a JPEG file and return its absolute path.
 * Throws on failure (the relay turns a throw into an `Error: …` tool result, so the
 * model sees the same "Error: Failed to capture screen" shape macOS returns).
 */
export async function captureScreenToFile(): Promise<string> {
  const target = cursorDisplay()
  const thumbnailSize = target?.pixelSize ?? DEFAULT_PIXEL_SIZE
  const sources = await desktopCapturer.getSources({ types: ['screen'], thumbnailSize })
  const source = await pickSource(sources, target)
  if (!source || source.thumbnail.isEmpty()) {
    throw new Error('Failed to capture screen')
  }
  const jpeg = source.thumbnail.toJPEG(JPEG_QUALITY)
  if (jpeg.length === 0) {
    throw new Error('Failed to capture screen')
  }

  const dir = screenshotsDir()
  const nowMs = Date.now()
  pruneOldScreenshots(dir, nowMs)
  const path = join(dir, `${FILE_PREFIX}${nowMs}${FILE_EXT}`)
  writeFileSync(path, jpeg)
  return path
}
