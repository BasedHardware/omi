import { app, shell, BrowserWindow, ipcMain, session, nativeImage, desktopCapturer } from 'electron'
import { join } from 'path'
import { appendFileSync } from 'fs'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import { supportsMica } from './windowsVersion'
import { APP_BG_HEX, WCO_SYMBOL_HEX } from '../shared/chrome'
import iconPath from '../../resources/icon.png?asset'
import { listCaptureSources } from './ipc/capture'
import {
  registerOmiListenHandlers,
  startTestListenSession,
  stopTestListenSession
} from './ipc/omiListen'
import { registerCaptureBridge } from './ipc/captureBridge'
import { registerSoak } from './soak'
import { createCaptureWindow, getCaptureWindow, getCaptureWc } from './captureWindow'
import { registerFileIndexHandlers } from './ipc/fileIndex'
import { registerMemoryImportHandlers } from './ipc/memoryImport'
import { registerMemoryExportHandlers } from './ipc/memoryExport'
import { registerKgHandlers } from './ipc/kg'
import { registerAuthHandlers } from './ipc/auth'
import { registerIntegrationsHandlers } from './ipc/integrations'
import { registerLocalGraphHandlers } from './ipc/localGraph'
import { registerUsageHandlers } from './ipc/usage'
import { registerMemoryCleanupHandlers } from './ipc/memoryCleanup'
import { startForegroundMonitor } from './usage/foregroundMonitor'
import {
  registerBarIpc,
  destroyBar,
  handleSummonPress,
  setSummonGestureAccelerator,
  setBarEnabled,
  setPeekWatchSuspended,
  getBarWindow,
  isBarInteractive,
  isBarVisible,
  showBar,
  hideBar
} from './bar/window'
import {
  registerOverlayShortcut,
  unregisterOverlayShortcut,
  suspendOverlayShortcut,
  resumeOverlayShortcut,
  OVERLAY_ACCELERATOR
} from './overlay/shortcut'
import { registerOverlayHandlers } from './overlay/ipc'
import { seedUserAssistOnce } from './usage/userAssistSeed'
import { registerRewindHandlers } from './ipc/rewind'
import { registerScreenHandlers } from './ipc/screen'
import { registerInsightHandlers } from './ipc/insight'
import {
  createInsightToastWindow,
  showWhatsNewToast,
  getCurrentWhatsNew
} from './insight/toastWindow'
import { maybeGetWhatsNew, releaseNotesUrl } from './whatsNew'
import { registerMeetingHandlers } from './ipc/meeting'
import { startMeetingMonitor, stopMeetingMonitor, meetingDebug } from './meeting/meetingMonitor'
import { registerAutomationHandlers } from './ipc/automation'
import { registerCodingAgentHandlers } from './ipc/codingAgent'
import { automationBridge } from './automation/bridge'
import {
  startAutomationTargetTracker,
  stopAutomationTargetTracker
} from './automation/foregroundTarget'
import { registerScreenSynthHandlers } from './ipc/screenSynth'
import { startRendererServer, rendererBaseUrl } from './rendererServer'
import { startRewindCapture } from './rewind/captureService'
import { startRewindOcr } from './rewind/ocrService'
import { startRewindRetention } from './rewind/retentionRunner'
import { prewarmPrimarySourceId } from './rewind/sourceId'
import { perfMark, flushPerfMarks } from '../shared/perf'
// Dev-only benchmarking / sandbox machinery. Every call below is behind
// `import.meta.env.DEV`, so this module is tree-shaken out of packaged main.
import * as devBench from './dev/bench'
import { initSentry } from './sentry'
import { isQuitting, quitApp } from './lifecycle'
import { createTray, updateTrayState, destroyTray, isTrayCreated } from './tray'
import { initAutoUpdater, getPendingUpdate } from './updater'
import {
  registerRecordShortcut,
  setRecordAccelerator,
  getRecordShortcut,
  suspendRecordShortcut,
  resumeRecordShortcut
} from './shortcuts'
import { getAppSettings, setAppSettings } from './appSettings'
import { showBestEffortNotification } from './notify'

// THE main window — single module-level owner. Everything that outlives the
// whenReady scope (tray menu, updater, shortcuts, second-instance handoff,
// activate) reads through this variable so a re-created window can never leave
// a consumer bound to a destroyed instance.
let mainWindow: BrowserWindow | null = null

function withMainWindow(fn: (win: BrowserWindow) => void): void {
  if (mainWindow && !mainWindow.isDestroyed()) fn(mainWindow)
}

/** Surface the main window: un-minimize, show, focus. */
function surfaceMainWindow(): void {
  withMainWindow((win) => {
    if (win.isMinimized()) win.restore()
    win.show()
    win.focus()
  })
}

// Tray-only start: when launched at login with --hidden, create the window but
// don't show it (the user opens it from the tray). See setLoginItemSettings.
const startHidden = process.argv.includes('--hidden')

// In dev, default the perf log to userData so marks capture to disk (the bench
// runner overrides OMI_PERF_LOG). Packaged builds write nothing unless the env
// var is explicitly set — no silent prod telemetry file. Runs before app:start.
if (import.meta.env.DEV) devBench.applyDevPerfLogDefault()
// Dev GPU stability: render in software + keep WebGL on SwiftShader + never let a
// GPU crash permanently blocklist WebGL, so the orb / brain map / blur / effects
// stay reliable on flaky dev GPUs (hybrid laptop, asleep display, headless soak).
// Must run before app ready. Packaged builds keep full hardware acceleration.
if (import.meta.env.DEV) devBench.applyDevGpuStability()
perfMark('app:start')

// --- Global crash observability --------------------------------------------
// The main process previously had no top-level error handling: an unhandled
// exception or rejection could terminate (or silently wedge) the app with
// nothing recorded, and renderer/GPU/utility crashes went unnoticed. Record
// fatal events to a crash log under userData so field failures are diagnosable,
// and keep the app usable on a renderer crash by reloading rather than leaving
// a blank window. Handlers are best-effort and must never throw themselves.
function logFatal(kind: string, detail: unknown): void {
  const body = detail instanceof Error ? (detail.stack ?? detail.message) : String(detail)
  try {
    // Resolve the path at call time, not module load: the sandbox block below
    // re-pins userData, and a path captured at import would send sandbox-mode
    // crash logs to the production profile.
    appendFileSync(
      join(app.getPath('userData'), 'crash.log'),
      `${new Date().toISOString()} [${kind}] ${body}\n`
    )
  } catch {
    /* best-effort; never throw from a crash handler */
  }
  console.error(`[fatal] ${kind}:`, detail)
}
process.on('uncaughtException', (err) => logFatal('uncaughtException', err))
process.on('unhandledRejection', (reason) => logFatal('unhandledRejection', reason))
// Reload a crashed renderer instead of leaving a white window — but cap rapid
// retries: a persistent startup failure would otherwise loop crash → reload →
// crash forever, flashing the window and flooding crash.log. The budget is
// tracked PER WebContents (WeakMap, so destroyed windows drop out): a
// crash-looping toast/overlay must not exhaust the main window's retries.
const RENDERER_RELOAD_WINDOW_MS = 60_000
const RENDERER_RELOAD_MAX = 3
const rendererReloadTimes = new WeakMap<Electron.WebContents, number[]>()
app.on('render-process-gone', (_e, wc, details) => {
  // Include the URL so a crash is attributable to a specific window (main /bar /
  // capture /insight-toast) instead of an anonymous "renderer crashed".
  const url = ((): string => {
    try {
      return wc.getURL()
    } catch {
      return '?'
    }
  })()
  logFatal(
    'render-process-gone',
    `url=${url} reason=${details.reason} exitCode=${details.exitCode}`
  )
  // Skip clean exits (intentional teardown) and destroyed windows.
  if (details.reason === 'clean-exit' || wc.isDestroyed()) return
  const now = Date.now()
  const recent = (rendererReloadTimes.get(wc) ?? []).filter(
    (t) => now - t < RENDERER_RELOAD_WINDOW_MS
  )
  if (recent.length >= RENDERER_RELOAD_MAX) {
    rendererReloadTimes.set(wc, recent)
    logFatal(
      'render-process-gone',
      `reload suppressed — renderer (webContents ${wc.id}) crashed ${RENDERER_RELOAD_MAX}+ times in ${RENDERER_RELOAD_WINDOW_MS / 1000}s; leaving window for manual reload`
    )
    return
  }
  recent.push(now)
  rendererReloadTimes.set(wc, recent)
  try {
    wc.reload()
  } catch {
    /* window may be mid-teardown */
  }
})
app.on('child-process-gone', (_e, details) =>
  // Include the utility's name/service (e.g. "Audio Service", "Video Capture")
  // so a Utility crash points at the actual subsystem rather than just "Utility".
  logFatal(
    'child-process-gone',
    `type=${details.type}` +
      (details.name ? ` name=${details.name}` : '') +
      (details.serviceName ? ` service=${details.serviceName}` : '') +
      ` reason=${details.reason} exitCode=${details.exitCode}`
  )
)

// Desktop-automation bridge (real Windows UI actions). ON by default; set
// OMI_AUTOMATION='0' as a kill-switch to disable it. Gates both the IPC
// registration and the foreground-target tracker; the renderer reads the same
// flag (window.omi.automationEnabled) to skip its action-planner pre-step.
const AUTOMATION_ENABLED = process.env.OMI_AUTOMATION !== '0'

// OMI_SANDBOX pins a throwaway userData dir for parallel dev worktrees so they
// don't clobber the real profile (dev-only; see dev/bench). Runs before the
// single-instance lock and any DB open.
if (import.meta.env.DEV) devBench.applySandboxUserDataOverride()

// Single-instance lock: only ONE Omi runs per userData profile. A second launch
// hands off to the first (see the 'second-instance' handler) and exits. Acquired
// AFTER the sandbox repin above so distinct OMI_SANDBOX profiles (and the E2E
// harness's --user-data-dir) each get their own lock instead of contending.
const gotSingleInstanceLock = app.requestSingleInstanceLock()
if (!gotSingleInstanceLock) app.quit()

// Wipe stale Chromium GPU/shader caches for THIS profile before the GPU process
// opens them — a force-killed dev build corrupts them and the corruption poisons
// the next launch's WebGL. Gated on the single-instance lock so a throwaway
// second launch can't delete the RUNNING instance's live caches; still before
// whenReady/first-window, so it lands ahead of GPU-process init.
if (import.meta.env.DEV && gotSingleInstanceLock) devBench.clearStaleGpuCaches()

// Crash/error reporting. After the lock check so the throwaway second-launch
// process doesn't pay SDK setup; no-op unless a DSN is configured, and only
// enabled for packaged builds (see sentry.ts).
if (gotSingleInstanceLock) initSentry()

const icon = nativeImage.createFromPath(iconPath)
import {
  remapConversationId,
  insertLocalConversation,
  getLocalConversation,
  listLocalConversations,
  deleteLocalConversation,
  updateLocalConversationTitle,
  updateLocalConversationSync,
  claimConversationForPosting
} from './ipc/db'

// The first time the user closes the window to the tray, tell them Omi is still
// running (otherwise "it disappeared but didn't quit" is confusing). Shown once,
// persisted in app-settings.json.
function maybeShowCloseToTrayNotice(): void {
  if (getAppSettings().closeToTrayNoticeShown) return
  setAppSettings({ closeToTrayNoticeShown: true })
  showBestEffortNotification(
    'Omi is still running',
    'Omi keeps listening in the tray. Right-click the tray icon to pause or quit.'
  )
}

function createWindow(): BrowserWindow {
  // Create the browser window. 1280x820 gives the two-column Record layout
  // (transcript + screen sidebar) room without overflow; the 500px floor keeps
  // a narrow snapped window usable (the sidebar collapses).
  //
  // Windows-11 chrome: the native title bar is hidden and replaced by the
  // Window Controls Overlay (native caption buttons → Snap Layouts hover
  // works); the renderer draws its own 36px drag strip. On 22H2+ the window
  // gets the Mica system backdrop (the renderer goes translucent via
  // data-mica); older builds fall back to the flat token canvas.
  const mica = supportsMica()
  const mainWindow = new BrowserWindow({
    title: 'omi',
    width: 1280,
    height: 820,
    minWidth: 500,
    minHeight: 600,
    show: false,
    autoHideMenuBar: true,
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      // The overlay paints only the caption-button cluster; it must match the
      // app's top strip (the transparent TitleBar drag region, so the color
      // directly behind the buttons is the page background — #0f0f0f, restored
      // as the Mica tint base in useMicaChrome, or the flat non-Mica canvas).
      //
      // #0f0f0f is deliberate, not a leftover. The caption seam looked wrong ONLY
      // because the Mica tint was dead code (the page rendered fully transparent,
      // so the strip was raw 100%-bleed Mica — much lighter than the opaque
      // caption). Restoring the tint (useMicaChrome) makes the strip 82%-opaque
      // #0f0f0f, and the caption blends into it. Verified on a real composited
      // desktop (setTitleBarOverlay sweep + CopyFromScreen sampling): Windows
      // FLATTENS the overlay alpha (rgba(15,15,15,0.82) rendered as opaque
      // ~#0e0e0e, no desktop bleed) so a translucent overlay is impossible, and
      // solids #1a1a1a / #252525 both rendered as a VISIBLY LIGHTER box around
      // the buttons — #0f0f0f was the only seamless tone. (Trade-off: the strip
      // is translucent and the overlay is opaque, so on a very light wallpaper
      // the 18% bleed lifts the strip slightly above #0f0f0f — a subtle, not a
      // box-shaped, mismatch. See PR notes.)
      // Static is fine: the app has no theme/backdrop switching (no nativeTheme/
      // themeSource usage), so the overlay never needs a runtime setTitleBarOverlay.
      // Both values derive from shared/chrome (single source of truth with the
      // renderer's Mica tint + the CSS --bg-primary / --text-tertiary tokens).
      color: APP_BG_HEX,
      symbolColor: WCO_SYMBOL_HEX,
      height: 36
    },
    transparent: false,
    ...(mica ? { backgroundMaterial: 'mica' as const } : { backgroundColor: '#0f0f0f' }),
    icon,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      // Tell the preload whether Mica is active (renderer sets data-mica).
      additionalArguments: [`--omi-mica=${mica ? '1' : '0'}`],
      // webSecurity stays ON. The Omi API CORS gap is handled by the header
      // injection + OPTIONS-preflight forcing in the webRequest hooks below, so
      // we no longer weaken the renderer's web security to work around it.
      // Keep renderer timers running at full rate when the window is minimized/
      // hidden, so Rewind's background screen capture keeps sampling instead of
      // being throttled to ~once/minute by Chromium's background policy.
      backgroundThrottling: false
    }
  })

  // NOTE: the main window is intentionally NOT content-protected. We used to call
  // setContentProtection(true) here (Windows WDA_EXCLUDEFROMCAPTURE) so Rewind/chat
  // screenshots read only what's BEHIND Omi — but Omi's own window should appear in
  // the Rewind timeline like any other app. The frame dedup hash still skips
  // unchanged frames, and the foreground-window metadata records when Omi is
  // frontmost. (The floating overlay keeps its own protection in overlay/window.ts.)
  mainWindow.on('ready-to-show', () => {
    // Tray-only login start (--hidden): keep the window hidden until the user
    // opens it from the tray.
    if (!startHidden) mainWindow.show()
  })

  // Close = hide to tray (Windows stays resident in the tray), unless the app is
  // really quitting. The overlay and background services keep running so Omi
  // keeps listening. Real teardown happens on quit (see will-quit).
  mainWindow.on('close', (e) => {
    if (!isQuitting()) {
      e.preventDefault()
      mainWindow.hide()
      maybeShowCloseToTrayNotice()
    }
  })

  // Ctrl+Q quits for real while the window is focused (tray Quit and the
  // app:quit IPC are the other real-quit paths).
  mainWindow.webContents.on('before-input-event', (_e, input) => {
    if (input.type === 'keyDown' && input.control && input.key.toLowerCase() === 'q') quitApp()
  })
  perfMark('window:created')

  // Everything window.open()ed routes to the system browser — there is no
  // embedded OAuth popup anymore (Google blocks webview OAuth; sign-in runs the
  // backend PKCE flow in the system browser via src/main/ipc/auth.ts).
  mainWindow.webContents.setWindowOpenHandler((details) => {
    const url = details.url
    // Hand only web/mail links to the OS. A prompt-injected chat reply could emit
    // a file://, UNC, or custom-protocol URL; passing those to shell.openExternal
    // enables NTLM-hash leak / protocol-handler abuse. Defense-in-depth alongside
    // the renderer's Markdown scheme allow-list.
    try {
      const scheme = new URL(url).protocol
      if (scheme === 'http:' || scheme === 'https:' || scheme === 'mailto:') {
        shell.openExternal(url)
      } else {
        console.warn('[main] blocked external open of non-web URL scheme:', scheme)
      }
    } catch {
      console.warn('[main] blocked external open of unparseable URL')
    }
    return { action: 'deny' }
  })

  // HMR for renderer base on electron-vite cli.
  // Load the remote URL for development, or the loopback renderer server in
  // production — a file:// origin would break Firebase sign-in (see
  // rendererServer.ts). loadFile stays as a last resort so a server failure
  // still produces a window (signed-out features only).
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else if (rendererBaseUrl()) {
    mainWindow.loadURL(`${rendererBaseUrl()}/index.html`)
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
  return mainWindow
}

// This method will be called when Electron has finished
// initialization and is ready to create browser windows.
// Some APIs can only be used after this event occurs.
app.whenReady().then(async () => {
  // Lost the single-instance race: this process is already quitting — do no
  // window/service setup, just let it exit and hand off to the first instance.
  if (!gotSingleInstanceLock) return
  perfMark('main:ready')

  // Production only (dev uses the vite dev server): serve the packaged renderer
  // over localhost so Firebase auth sees an authorized origin. Must be up before
  // any window loads.
  if (!(is.dev && process.env['ELECTRON_RENDERER_URL'])) {
    try {
      await startRendererServer(join(__dirname, '../renderer'))
    } catch (e) {
      console.error(
        '[main] renderer server failed to start — falling back to file:// (sign-in will not work):',
        e
      )
    }
  }
  // Set the App User Model ID before any BrowserWindow or Notification is created,
  // so Windows attributes toasts + taskbar grouping to Omi (packaged toasts fail
  // silently otherwise). This MUST run first: it matches electron-builder.yml's
  // appId (com.omiwindows.app) exactly — the NSIS shortcut AUMID the installer
  // writes — which is what lets packaged toasts attribute correctly. Both
  // Notification sites (notify.ts, insight/notification.ts) are user-event-driven
  // and structurally cannot fire before createWindow below, so this always wins.
  electronApp.setAppUserModelId('com.omiwindows.app')

  // Default open or close DevTools by F12 in development
  // and ignore CommandOrControl + R in production.
  // see https://github.com/alex8088/electron-toolkit/tree/master/packages/utils
  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  // Omi's API doesn't advertise the renderer's localhost origin as CORS-allowed.
  // We used to work around this by disabling webSecurity on every window; that's
  // now OFF (webSecurity is ON — see the window webPreferences), so instead we
  // control the network stack: strip the Origin header on outgoing requests and
  // inject permissive CORS response headers. Scoped to the specific upstreams —
  // everything else flows normally.
  const apiUrls = [
    'https://api.omi.me/*',
    'https://desktop-backend-hhibjajaja-uc.a.run.app/*',
    // PostHog analytics ingestion. Added proactively for the webSecurity-on switch.
    // Static analysis suggests it may not actually need CORS help (a same-shape
    // JSON POST that PostHog answers with permissive CORS), but including it is
    // harmless and avoids a surprise block if PostHog tightens its headers.
    'https://us.i.posthog.com/*'
  ]
  session.defaultSession.webRequest.onBeforeSendHeaders({ urls: apiUrls }, (details, cb) => {
    const headers = { ...details.requestHeaders }
    delete headers.Origin
    delete headers.origin
    cb({ requestHeaders: headers })
  })
  session.defaultSession.webRequest.onHeadersReceived({ urls: apiUrls }, (details, cb) => {
    const responseHeaders = {
      ...details.responseHeaders,
      'access-control-allow-origin': ['*'],
      // `*` does NOT cover Authorization even for non-credentialed requests, so
      // list it (and content-type) explicitly alongside the wildcard.
      'access-control-allow-headers': ['authorization, content-type, *'],
      'access-control-allow-methods': ['GET, POST, PUT, PATCH, DELETE, OPTIONS']
    }
    // Preflight gotcha (surfaces only with webSecurity ON): a CORS preflight
    // OPTIONS must get a 2xx carrying the allow-* headers or the browser blocks
    // the real request. The Omi API may not answer OPTIONS with a success + these
    // headers, so force a 200 for preflights on the allowlisted hosts.
    if (details.method === 'OPTIONS') {
      cb({ responseHeaders, statusLine: 'HTTP/1.1 200 OK' })
      return
    }
    cb({ responseHeaders })
  })

  // System-audio (loopback) capture for the Screen recording mode (which mixes
  // mic + system audio). getDisplayMedia() in the renderer routes here; we hand back a screen
  // video source plus 'loopback' audio (Windows WASAPI loopback). The renderer
  // drops the unused video track and keeps only the system-audio track. This is
  // separate from the screen-record picker, which uses getUserMedia with an
  // explicit desktop source id and never hits this handler.
  //
  // NOTE: Electron ships no default getDisplayMedia picker — if this handler
  // isn't registered, getDisplayMedia() rejects with "Not supported". Changes
  // here only take effect after a FULL restart of the main process.
  session.defaultSession.setDisplayMediaRequestHandler(async (_request, callback) => {
    try {
      const sources = await desktopCapturer.getSources({ types: ['screen'] })
      if (sources.length === 0) throw new Error('no screen sources available')
      console.log('[main] display-media request → granting loopback audio')
      callback({ video: sources[0], audio: 'loopback' })
    } catch (e) {
      console.error('[main] display-media request failed:', e)
      callback({})
    }
  })
  console.log('[main] setDisplayMediaRequestHandler registered (system-audio loopback ready)')

  ipcMain.handle('capture:getSources', async () => listCaptureSources())
  // Renderer reports its first painted frame; recorded here so the startup mark
  // uses the main process's monotonic clock (consistent with the other phases).
  ipcMain.on('perf:firstPaint', () => perfMark('renderer:first-paint'))
  // Generic renderer-side startup mark (e.g. 'renderer:eval' once the bundle has
  // finished evaluating), recorded on the main clock to bisect startup phases.
  ipcMain.on('perf:mark', (_e, name: string) => perfMark(String(name)))
  // Dev-only bench IPC (bench:echo round-trip). Tree-shaken from packaged main.
  if (import.meta.env.DEV) devBench.registerBenchIpc()
  ipcMain.handle('db:remapConversationId', async (_e, fromId: string, toId: string) =>
    remapConversationId(fromId, toId)
  )
  ipcMain.handle('db:insertLocalConversation', async (_e, c) => insertLocalConversation(c))
  ipcMain.handle('db:getLocalConversation', async (_e, id: string) => getLocalConversation(id))
  ipcMain.handle('db:listLocalConversations', async () => listLocalConversations())
  ipcMain.handle('db:deleteLocalConversation', async (_e, id: string) =>
    deleteLocalConversation(id)
  )
  ipcMain.handle('db:updateLocalConversationTitle', async (_e, id: string, title: string) =>
    updateLocalConversationTitle(id, title)
  )
  ipcMain.handle('db:updateLocalConversationSync', async (_e, id, patch) =>
    updateLocalConversationSync(id, patch)
  )
  ipcMain.handle(
    'db:claimConversationForPosting',
    async (_e, id: string, resetAttempts?: boolean) =>
      claimConversationForPosting(id, resetAttempts)
  )
  registerOmiListenHandlers()
  // Capture bridge: routes commands from UI windows to the hidden capture window
  // and events back. Registered before the capture window is created so no early
  // command/event is missed. Reads the capture wc live so a respawn is picked up.
  registerCaptureBridge(getCaptureWc)
  // Soak telemetry (inert unless OMI_SOAK=1): samples process metrics + listen
  // byte counters to userData/soak.jsonl for the 8h idle-soak verification.
  registerSoak()
  registerFileIndexHandlers()
  registerLocalGraphHandlers()
  registerMemoryImportHandlers()
  registerMemoryExportHandlers()
  registerKgHandlers()
  // Google sign-in (system browser + loopback). On success, surface the main
  // window OVER the browser: Windows blocks background apps from stealing
  // foreground focus, so a plain show()/focus() only flashes the taskbar —
  // briefly forcing always-on-top makes the surface actually happen (same
  // trick as integrations/oauth.ts focusOmi).
  registerAuthHandlers(() => {
    withMainWindow((win) => {
      if (win.isMinimized()) win.restore()
      win.setAlwaysOnTop(true)
      win.show()
      win.focus()
      win.setAlwaysOnTop(false)
    })
    app.focus({ steal: true })
  })
  registerIntegrationsHandlers()
  registerUsageHandlers()
  registerMemoryCleanupHandlers()
  registerRewindHandlers()
  registerScreenHandlers()
  // Cross-window conversations refresh: any renderer that writes a local
  // conversation (main window OR overlay) notifies here; rebroadcast to every
  // window so each invalidates its own per-process conversations cache (e.g. an
  // overlay chat shows up in the main window's chat tab without a relaunch).
  ipcMain.on('conversations:notify-changed', () => {
    for (const w of BrowserWindow.getAllWindows()) {
      if (!w.isDestroyed()) w.webContents.send('conversations:changed')
    }
  })
  registerInsightHandlers()
  registerMeetingHandlers()
  // What's-new toast (Phase 8): the renderer pulls the pending payload on mount
  // (push-during-load race), and opens the release notes in the system browser.
  ipcMain.handle('whatsnew:getPending', async () => getCurrentWhatsNew())
  ipcMain.on('whatsnew:openNotes', () => void shell.openExternal(releaseNotesUrl()))
  perfMark('main:handlers-registered')
  // One-time cold-start seed: rank the first brain map by real historical app
  // usage from the Windows UserAssist registry. No-op when disabled/off-Windows/
  // already seeded. Runs before the renderer's first KG build.
  seedUserAssistOnce()
  perfMark('main:userassist-seeded')
  // Desktop automation: register the snapshot/plan/run IPC here (cheap — handler
  // registration only). The foreground-window tracker is a service start, so it's
  // deferred to ready-to-show below alongside the other background services.
  // On by default; OMI_AUTOMATION='0' disables the "take real UI actions" bridge.
  if (AUTOMATION_ENABLED) registerAutomationHandlers()
  // Screen-activity synthesis IPC (cheap handler registration; the renderer drives
  // cadence). Rewind handlers/services are already registered/deferred above + below.
  registerScreenSynthHandlers()
  // Coding-agent task IPC (cheap handler registration; adapter subprocesses spawn
  // only when a task actually runs).
  registerCodingAgentHandlers()

  // `win` is this launch's instance for one-shot wiring below (ready-to-show,
  // bench); long-lived consumers read the module-level `mainWindow` instead.
  const win = (mainWindow = createWindow())

  // System tray: the app's anchor while windows are hidden. Reflects listening
  // state (renderer reports via tray:state), toggles the window, and owns Quit.
  // Every dep reads through the module-level ref (never a captured instance) so
  // the tray keeps working if the window is ever re-created.
  createTray({
    showMainWindow: surfaceMainWindow,
    hideMainWindow: () => withMainWindow((win) => win.hide()),
    isMainWindowVisible: () =>
      !!mainWindow &&
      !mainWindow.isDestroyed() &&
      mainWindow.isVisible() &&
      !mainWindow.isMinimized(),
    toggleListening: () => withMainWindow((win) => win.webContents.send('tray:toggle-listening')),
    openSettings: () => {
      surfaceMainWindow()
      withMainWindow((win) => win.webContents.send('tray:open-settings'))
    },
    quit: quitApp
  })

  // Auto-update (packaged builds only; see updater.ts). Never crashes the app.
  initAutoUpdater(() => mainWindow)

  // E2E hook (only when OMI_E2E=1; never in prod): expose the main-process facts
  // the lifecycle harness asserts via electronApp.evaluate.
  if (process.env.OMI_E2E === '1') {
    ;(globalThis as unknown as { __omiE2E?: Record<string, unknown> }).__omiE2E = {
      trayCreated: () => isTrayCreated(),
      // The harness must target the MAIN window — getAllWindows() also returns
      // the insight toast / overlay, which have different close semantics.
      mainWindowId: mainWindow.id,
      // VAD-playback harness: start/stop a real capture session (mic -> pipeline
      // -> VAD gate -> counted-and-dropped bytes) with zero auth or network.
      startCaptureForTest: async ({ source }: { source: 'mic' | 'system' }) => {
        if (!startTestListenSession('e2e-vad-playback', source)) return false
        const wc = getCaptureWc()
        if (!wc || wc.isDestroyed()) return false
        wc.send('omi-capture:cmd', {
          cmd: { type: 'audio-start', sessionId: 'e2e-vad-playback', source },
          ownerId: wc.id
        })
        return true
      },
      stopCaptureForTest: () => {
        const wc = getCaptureWc()
        if (wc && !wc.isDestroyed()) {
          wc.send('omi-capture:cmd', {
            cmd: { type: 'audio-stop', sessionId: 'e2e-vad-playback' },
            ownerId: wc.id
          })
        }
        stopTestListenSession('e2e-vad-playback')
      },
      // Bar harness: drive reveal paths without the global hotkey / edge strip
      // (the harness asserts focus behavior + takes screenshots).
      barShow: (mode: 'peek' | 'expanded' | 'ptt', reveal?: 'summon' | 'ptt') => {
        setBarEnabled(true) // the hermetic harness has no onboarding to enable it
        showBar(mode, reveal ?? (mode === 'ptt' ? 'ptt' : 'summon'))
      },
      barEnable: () => setBarEnabled(true),
      // Screenshot capture on a live desktop: the cursor is outside the peek
      // footprint, so the retract watchdog would hide the bar mid-capture.
      barHoldPeekOpen: (hold: boolean) => setPeekWatchSuspended(!!hold),
      barHide: () => hideBar(),
      barSummonFire: () => handleSummonPress(),
      barState: () => {
        const win = getBarWindow()
        return {
          exists: !!win && !win.isDestroyed(),
          visible: isBarVisible(),
          focused: !!win && !win.isDestroyed() && win.isFocused(),
          focusable: !!win && !win.isDestroyed() && win.isFocusable(),
          // Real hit-testing state: must be false right after ANY present —
          // only the cursor entering the visible surface enables it.
          interactive: isBarInteractive(),
          id: win && !win.isDestroyed() ? win.id : null
        }
      },
      // Meeting detection: inject fake Tier1/Tier2 signals + read the machine
      // phase, so the toast + capture wiring is drivable without real Zoom.
      meeting: meetingDebug()
    }
  }

  // Defer non-essential background services until the window is ready to show, so
  // their synchronous setup (foreground-monitor koffi/user32 init ~60ms, rewind
  // capture/OCR/retention loops, screen-source prewarm) runs AFTER first paint
  // instead of delaying the window from appearing. None are needed before the UI
  // is up; their IPC handlers are already registered above.
  win.once('ready-to-show', () => {
    // The hidden always-alive capture window: owns all audio + Rewind capture,
    // independent of any UI window. Created after first paint (ready-to-show fires
    // for --hidden tray-only login starts too, so continuous recording still works
    // before the user opens the window) rather than alongside createWindow, so a
    // second full renderer eval doesn't contend with the main window's first paint.
    // Capture starts ~0.5-1s later as a result, which the 2s PTT pre-roll and the
    // 30s silence finalizer tolerate. Skipped under the dev perf bench, whose
    // startup measurement must not include a second renderer.
    if (!(import.meta.env.DEV && devBench.isBenchMode())) createCaptureWindow()
    // Foreground app-usage tracking. No-ops when disabled in Settings or off-Windows.
    startForegroundMonitor()
    // Track the last non-Omi foreground window so the automation planner snapshots
    // the app the user was actually using (Omi is foreground once they click chat).
    if (AUTOMATION_ENABLED) startAutomationTargetTracker()
    // Load the user's persisted Rewind settings — capture is ON by default for a
    // fresh install, and any change the user makes in Settings survives restarts.
    // OCR/retention loops are cheap no-ops until frames exist.
    startRewindCapture()
    startRewindOcr()
    startRewindRetention()
    // Warm the (slow) screen-source-id cache a few seconds later, off the critical
    // path, so enabling capture later is an instant cache hit.
    setTimeout(() => prewarmPrimarySourceId(), 4000)
    // Pre-create the (hidden) acrylic toast window so the first Omi insight shows instantly.
    createInsightToastWindow()
    // Post-update "what's new" (Phase 8): a few seconds after startup (once the
    // toast window has loaded), surface the changelog for the version we just
    // updated into. No-op on a fresh install or an unchanged version.
    setTimeout(() => {
      const whatsNew = maybeGetWhatsNew()
      if (whatsNew) showWhatsNewToast(whatsNew)
    }, 6000)
    // Meeting detection (Phase 5): event-driven Tier1/Tier2 monitor → toast +
    // auto-capture via the capture window. No-op off-Windows; 'off' mode keeps
    // the machine latched silent.
    startMeetingMonitor({ getCaptureWc })
  })

  // Bar (replaces the old floating overlay): wire IPC + the global summon
  // shortcut. The shortcut callback feeds the gesture machine (auto-repeat
  // fires group into ONE gesture: tap toggles the expanded bar, a physical
  // hold is push-to-talk — the "bar flaps while holding the hotkey" fix).
  registerOverlayHandlers(surfaceMainWindow)
  // The bar chat is a viewport over the main window's single chat engine
  // (INV-CHAT-1): bar IPC forwards send/state routing to the main window here,
  // since bar/window.ts has no reference to it.
  registerBarIpc((channel, ...args) => withMainWindow((w) => w.webContents.send(channel, ...args)))
  setSummonGestureAccelerator(OVERLAY_ACCELERATOR)
  const shortcutOk = registerOverlayShortcut(OVERLAY_ACCELERATOR, handleSummonPress)
  if (!shortcutOk) {
    console.warn(
      '[bar] summon shortcut unavailable; the bar can still be revealed from the top edge'
    )
  }

  // Mic record chord (default Ctrl+Space, rebindable + persisted). Fires
  // 'recorder:hotkey' at the renderer (receiver already exists) and surfaces the
  // window if it was hidden, so a global hotkey both starts capture AND brings Omi
  // to the front.
  const recordState = registerRecordShortcut(getAppSettings().recordHotkey, () => {
    surfaceMainWindow()
    withMainWindow((w) => w.webContents.send('recorder:hotkey', 'mic'))
  })
  if (!recordState.registered) {
    console.warn(`[shortcut] record chord "${recordState.accelerator}" is unavailable (in use?)`)
  }

  // Renderer → tray: reflect the reported listening state on the tray icon/menu.
  ipcMain.on('tray:state', (_e, state) => updateTrayState(state))

  // Launch-at-login (writes the HKCU Run key; --hidden → tray-only start).
  // Packaged builds only: in dev process.execPath is the bare electron.exe
  // WITHOUT the app path, so a dev-written Run entry would launch an empty
  // Electron shell at every login (found live during Phase 1 verification).
  ipcMain.handle('app:get-login-item', () => ({
    openAtLogin: app.isPackaged ? app.getLoginItemSettings().openAtLogin : false,
    supported: app.isPackaged
  }))
  ipcMain.handle('app:set-login-item', (_e, enabled: boolean) => {
    if (!app.isPackaged) {
      console.log('[login-item] skipped in dev (execPath is bare electron.exe)')
      return
    }
    app.setLoginItemSettings({ openAtLogin: !!enabled, path: process.execPath, args: ['--hidden'] })
  })

  // Record-chord get/rebind. Rebinds persist and never throw on a conflict — a
  // taken chord returns registered=false so the UI can prompt for another.
  ipcMain.handle('shortcuts:get-record', () => getRecordShortcut())
  // Query the staged update on demand (the update:ready event fires once,
  // usually while Settings isn't mounted — see updater.getPendingUpdate).
  ipcMain.handle('update:get-pending', () => getPendingUpdate())

  // Suspend/resume global chords while the settings UI captures raw keys for a
  // rebind — otherwise pressing the CURRENT chord fires it instead of being
  // captured. (The overlay's own recorder uses overlay:suspendShortcut.)
  ipcMain.on('shortcuts:suspend-capture', () => {
    suspendRecordShortcut()
    suspendOverlayShortcut()
  })
  ipcMain.on('shortcuts:resume-capture', () => {
    resumeRecordShortcut()
    resumeOverlayShortcut()
  })

  ipcMain.handle('shortcuts:set-record', (_e, accelerator: string) => {
    if (typeof accelerator !== 'string' || !accelerator.trim()) {
      return { ok: false, registered: getRecordShortcut().registered }
    }
    const next = setRecordAccelerator(accelerator.trim())
    if (next.registered) setAppSettings({ recordHotkey: next.accelerator })
    return { ok: next.registered, registered: next.registered }
  })

  // Renderer → quit for real (menu/button in the UI).
  ipcMain.on('app:quit', () => quitApp())

  // Dev perf bench: after the renderer loads, record the startup-timing marks and
  // quit. Entirely dev-only — tree-shaken from packaged main (see dev/bench).
  if (import.meta.env.DEV) devBench.runBenchDriver(win)

  app.on('activate', function () {
    // On macOS it's common to re-create a window in the app when the
    // dock icon is clicked and there are no other windows open.
    if (BrowserWindow.getAllWindows().length === 0) mainWindow = createWindow()
  })
})

// A second launch attempt handed off to us (see requestSingleInstanceLock):
// surface the existing window instead of starting a new instance.
app.on('second-instance', () => {
  surfaceMainWindow()
})

// On win32 the app lives in the tray, so it must NOT quit when the last window
// hides/closes — only an explicit Quit ends it (see lifecycle.quitApp). macOS
// keeps its historical behavior; other platforms quit when all windows close.
app.on('window-all-closed', () => {
  if (process.platform === 'win32' || process.platform === 'darwin') return
  app.quit()
})

// On a normal shutdown (the quitting flag is already set — lifecycle.ts's
// before-quit hook runs first): tear down the tray + always-alive overlay window,
// flush perf marks, release the overlay shortcut, and dispose the automation
// helper + foreground-window hook.
app.on('will-quit', () => {
  stopMeetingMonitor()
  destroyTray()
  destroyBar()
  const capture = getCaptureWindow()
  if (capture && !capture.isDestroyed()) capture.destroy()
  unregisterOverlayShortcut()
  flushPerfMarks()
  automationBridge.dispose()
  stopAutomationTargetTracker()
})

// In this file you can include the rest of your app's specific main process
// code. You can also put them in separate files and require them here.
