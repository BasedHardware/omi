import { powerMonitor, nativeImage } from 'electron'
import { writeFileSync } from 'fs'
import { basename } from 'path'
import { getForegroundExePath, getForegroundWindowTitle } from '../usage/nativeForeground'
import { averageHash } from './frameHash'
import { shouldCaptureFrame } from './captureDecision'
import { rewindFramePath } from './paths'
import { helperProcess } from '../ocr/helperProcess'
import { insertRewindFrame, setRewindFrameOcr } from '../ipc/db'
import { setCurrentScreen } from './currentScreen'
import { getPersistedRewindSettings, persistRewindSettings } from './rewindSettings'
import { BUILT_IN_EXCLUDED_APPS } from '../../shared/rewindExclusions'
import type { RewindSettings } from '../../shared/types'

const HASH_W = 16
const HASH_H = 9
const IDLE_THRESHOLD_SECONDS = 60

let locked = false
let lastHash: string | null = null
let powerListenersBound = false
// In-memory mirror of the persisted settings. startRewindCapture() loads the
// saved value (defaulting to capture-on) at startup; updateRewindSettings()
// keeps this and the on-disk copy in sync. Defaults to capture-on for any
// pre-startup getRewindSettings() read.
let settings: RewindSettings = {
  captureEnabled: true,
  intervalMs: 1000,
  retentionDays: 14,
  excludedApps: []
}

function bindPowerListeners(): void {
  if (powerListenersBound) return
  powerMonitor.on('lock-screen', () => (locked = true))
  powerMonitor.on('unlock-screen', () => (locked = false))
  powerListenersBound = true
}

export type IngestResult = { captured: boolean; reason?: string }

// Single-flight guard so the background "current screen" OCR never stacks: the
// helper processes one frame at a time, and a captured frame arrives ~every second.
// If an OCR is already running we skip this frame — the cache stays ~1-2s fresh,
// which is plenty for the chat's instant read.
let screenOcrInFlight = false

/**
 * Keep the chat's hot "current screen" cache fresh: OCR a just-captured frame in
 * the background and store the text in {@link setCurrentScreen}, so the chat reads
 * it with zero latency. Also persists the OCR onto the frame so the slower
 * backfiller doesn't re-OCR it. Best-effort and NEVER awaited by the capture path.
 */
async function refreshCurrentScreen(frameId: number, jpeg: Buffer): Promise<void> {
  if (screenOcrInFlight) return
  screenOcrInFlight = true
  try {
    const res = await helperProcess.ocr(jpeg)
    if (res.ok) {
      setCurrentScreen(res.fullText)
      setRewindFrameOcr(frameId, res.fullText)
    }
  } catch {
    /* best-effort: keep the last good cached value */
  } finally {
    screenOcrInFlight = false
  }
}

/**
 * Ingest one screen frame (JPEG bytes) sampled by the renderer's capture host
 * (a getUserMedia desktop stream → canvas, the app's proven efficient path).
 * Capture *acquisition* deliberately lives in the renderer so it never touches
 * Electron's heavyweight `desktopCapturer` full-resolution thumbnail path,
 * which froze the whole system when polled. The main process keeps the cheap
 * parts: foreground-window metadata, idle/lock/dup gating, and storage.
 */
export async function ingestRewindFrame(jpeg: Buffer): Promise<IngestResult> {
  if (!settings.captureEnabled) return { captured: false, reason: 'disabled' }

  // NOTE: we don't skip capture while an Omi window is focused. The main window is
  // no longer content-protected, so Omi appears in the Rewind timeline like any
  // other app; the timeline keeps filling (and the chat's screen cache stays fresh)
  // even while Omi is focused. The dedup hash below still skips unchanged frames.

  let win = { app: '', title: '', processName: '' }
  try {
    const info = await helperProcess.windowInfo()
    // Prefer the friendly app name ("Google Chrome") over the exe ("chrome");
    // keep the raw process name in its own field.
    win = { app: info.app || info.processName, title: info.title, processName: info.processName }
  } catch {
    /* helper unavailable; fall back below */
  }
  // The C# helper isn't always running (OCR is shelved), so windowInfo() often
  // yields nothing → every frame would read "Unknown app". Fall back to the
  // always-available koffi/user32 foreground reader (same source app-usage uses)
  // and derive a name from the foreground exe.
  if (!win.app) {
    const exe = getForegroundExePath()
    if (exe) {
      const proc = basename(exe).replace(/\.exe$/i, '')
      win = {
        app: proc ? proc.charAt(0).toUpperCase() + proc.slice(1) : '',
        title: win.title,
        processName: win.processName || proc
      }
    }
  }
  // The helper rarely runs (OCR shelved), so the title is usually empty — but the
  // window title is what catches login/private-browsing screens in a normal
  // browser. Read it directly from user32 (GetWindowTextW) as a fallback.
  if (!win.title) win.title = getForegroundWindowTitle() ?? ''

  const image = nativeImage.createFromBuffer(jpeg)
  if (image.isEmpty()) return { captured: false, reason: 'decode-failed' }

  const small = image.resize({ width: HASH_W, height: HASH_H })
  const hash = averageHash(small.toBitmap(), HASH_W * HASH_H)

  const decision = shouldCaptureFrame({
    locked,
    idleSeconds: powerMonitor.getSystemIdleTime(),
    idleThresholdSeconds: IDLE_THRESHOLD_SECONDS,
    busy: false,
    appName: win.app,
    processName: win.processName,
    windowTitle: win.title,
    excludedApps: [...BUILT_IN_EXCLUDED_APPS, ...settings.excludedApps],
    hash,
    lastHash
  })
  if (!decision.capture) return { captured: false, reason: decision.reason }

  try {
    const ts = Date.now()
    const path = rewindFramePath(ts)
    writeFileSync(path, jpeg)
    const { width, height } = image.getSize()
    const id = insertRewindFrame({
      ts,
      app: win.app,
      windowTitle: win.title,
      processName: win.processName,
      ocrText: '',
      imagePath: path,
      width,
      height,
      indexed: 0
    })
    lastHash = hash
    // Update the chat's hot "current screen" cache from this fresh frame, in the
    // background (single-flight). Not awaited: capture cadence must not wait on OCR.
    void refreshCurrentScreen(id, jpeg)
    return { captured: true }
  } catch (e) {
    console.error('[rewind] capture failed:', (e as Error).message)
    return { captured: false, reason: 'write-failed' }
  }
}

/**
 * Load the user's persisted settings (capture-on by default for a fresh
 * install) + bind power listeners. The renderer drives cadence.
 */
export function startRewindCapture(): void {
  bindPowerListeners()
  settings = getPersistedRewindSettings()
}

/** Update the live settings and persist them so the choice survives restarts. */
export function updateRewindSettings(next: RewindSettings): void {
  settings = persistRewindSettings(next)
}

export function getRewindSettings(): RewindSettings {
  return settings
}
