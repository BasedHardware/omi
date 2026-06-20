import { powerMonitor, nativeImage } from 'electron'
import { writeFileSync } from 'fs'
import { basename } from 'path'
import { getForegroundExePath, getForegroundWindowTitle } from '../usage/nativeForeground'
import { averageHash } from './frameHash'
import { shouldCaptureFrame } from './captureDecision'
import { rewindFramePath } from './paths'
import { helperProcess } from '../ocr/helperProcess'
import { insertRewindFrame, setRewindFrameOcr } from '../ipc/db'
import { setCurrentScreen, reaffirmCurrentScreen } from './currentScreen'
import { createLatestRunner } from './latestRunner'
import { getPersistedRewindSettings, persistRewindSettings } from './rewindSettings'
import { BUILT_IN_EXCLUDED_APPS } from '../../shared/rewindExclusions'
import { DEFAULT_CAPTURE_MAX_EDGE } from '../../shared/rewindResolution'
import type { RewindSettings } from '../../shared/types'

const HASH_W = 16
const HASH_H = 9
const IDLE_THRESHOLD_SECONDS = 60

let locked = false
let lastHash: string | null = null
let powerListenersBound = false
// Last logged frame dimensions, so the resolution-change log fires only on change.
let lastLoggedWidth = 0
let lastLoggedHeight = 0
// In-memory mirror of the persisted settings. startRewindCapture() loads the
// saved value (defaulting to capture-on) at startup; updateRewindSettings()
// keeps this and the on-disk copy in sync. Defaults to capture-on for any
// pre-startup getRewindSettings() read.
let settings: RewindSettings = {
  captureEnabled: true,
  intervalMs: 1000,
  retentionDays: 14,
  excludedApps: [],
  captureMaxEdge: DEFAULT_CAPTURE_MAX_EDGE
}

function bindPowerListeners(): void {
  if (powerListenersBound) return
  powerMonitor.on('lock-screen', () => (locked = true))
  powerMonitor.on('unlock-screen', () => (locked = false))
  powerListenersBound = true
}

export type IngestResult = { captured: boolean; reason?: string }

/**
 * Keep the chat's hot "current screen" cache fresh: OCR a just-captured frame in
 * the background and store the text in {@link setCurrentScreen}, so the chat reads
 * it with zero latency. Also persists the OCR onto the frame so the slower
 * backfiller doesn't re-OCR it. Best-effort and NEVER awaited by the capture path.
 *
 * Single-flight with trailing-edge coalescing to the LATEST frame: the helper
 * OCRs one frame at a time (~0.2-2.5s) while captured frames arrive every ~1s, so
 * when the screen changes faster than OCR completes we must keep the NEWEST frame
 * and process it next — not drop it. A plain "skip if busy" guard dropped the new
 * frame, and since `lastHash` had already advanced, every later (identical) frame
 * was a duplicate → OCR never re-ran → the cache stayed stranded on the OLD
 * screen's text (the "reads an old screen / looks frozen" bug).
 */
const submitScreenOcr = createLatestRunner<{ frameId: number; jpeg: Buffer }>(
  async ({ frameId, jpeg }) => {
    const res = await helperProcess.ocr(jpeg)
    if (res.ok) {
      setCurrentScreen(res.fullText)
      setRewindFrameOcr(frameId, res.fullText)
      console.log(`[rewind:screen] cache <- ${res.fullText.length} chars (frame ${frameId})`)
    } else {
      console.warn(`[rewind:screen] OCR failed (frame ${frameId}): ${res.code} ${res.message ?? ''}`)
    }
  }
)

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

  // Read foreground-window metadata (for exclusion + sensitive-title gating and
  // for storage) from the always-instant, in-process user32 readers — NOT the C#
  // helper. The helper is single-threaded and now constantly busy OCRing the live
  // screen, so a windowInfo() call there queues behind the in-flight OCR
  // (~0.5-2.5s, measured) and stalls EVERY capture, stretching the cadence and
  // delaying how fast a screen change reaches the chat. user32 is ~ms and never
  // contends. (Slight cosmetic cost: the timeline shows the capitalized exe name
  // "Chrome" rather than the helper's friendly "Google Chrome"; exclusion
  // matching is unaffected since it's case-insensitive substring on app + proc.)
  let win = { app: '', title: '', processName: '' }
  const exe = getForegroundExePath()
  if (exe) {
    const proc = basename(exe).replace(/\.exe$/i, '')
    win = {
      app: proc ? proc.charAt(0).toUpperCase() + proc.slice(1) : '',
      title: '',
      processName: proc
    }
  }
  // The window title is what catches login/private-browsing screens in a normal
  // browser, so always read it (GetWindowTextW).
  win.title = getForegroundWindowTitle() ?? ''

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
  if (!decision.capture) {
    // A duplicate frame means the screen is unchanged since the last captured +
    // OCR'd frame, so the hot "current screen" cache text is still accurate right
    // now — re-affirm its freshness (no re-OCR) so a static screen doesn't age the
    // cache out (CACHE_FRESH_MS) and leave the chat unable to read it. Other skip
    // reasons (idle/lock/excluded/sensitive) intentionally let the cache go stale.
    if (decision.reason === 'duplicate') reaffirmCurrentScreen()
    return { captured: false, reason: decision.reason }
  }

  try {
    const ts = Date.now()
    const path = rewindFramePath(ts)
    writeFileSync(path, jpeg)
    const { width, height } = image.getSize()
    // Log frame dimensions only when they change — lets the resolution Setting be
    // verified (the longest edge should track captureMaxEdge) without per-frame spam.
    if (width !== lastLoggedWidth || height !== lastLoggedHeight) {
      lastLoggedWidth = width
      lastLoggedHeight = height
      console.log(`[rewind] frame size ${width}x${height} (captureMaxEdge=${settings.captureMaxEdge})`)
    }
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
    // background. Coalesces to the latest frame; never awaited (capture cadence
    // must not wait on OCR).
    submitScreenOcr({ frameId: id, jpeg })
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
