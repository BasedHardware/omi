import {
  app,
  shell,
  BrowserWindow,
  ipcMain,
  session,
  nativeImage,
  desktopCapturer,
  Notification
} from 'electron'
import { join } from 'path'
import { appendFileSync } from 'fs'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import iconPath from '../../resources/icon.png?asset'
import { listCaptureSources } from './ipc/capture'
import { registerOmiListenHandlers } from './ipc/omiListen'
import { registerFileIndexHandlers } from './ipc/fileIndex'
import { registerMemoryImportHandlers } from './ipc/memoryImport'
import { registerMemoryExportHandlers } from './ipc/memoryExport'
import { registerKgHandlers } from './ipc/kg'
import { registerIntegrationsHandlers } from './ipc/integrations'
import { registerLocalGraphHandlers } from './ipc/localGraph'
import { registerUsageHandlers } from './ipc/usage'
import { registerMemoryCleanupHandlers } from './ipc/memoryCleanup'
import { startForegroundMonitor } from './usage/foregroundMonitor'
import { getOverlayWindow, toggleOverlay } from './overlay/window'
import {
  registerOverlayShortcut,
  unregisterOverlayShortcut,
  OVERLAY_ACCELERATOR
} from './overlay/shortcut'
import { registerOverlayHandlers } from './overlay/ipc'
import { seedUserAssistOnce } from './usage/userAssistSeed'
import { registerRewindHandlers } from './ipc/rewind'
import { registerScreenHandlers } from './ipc/screen'
import { registerInsightHandlers } from './ipc/insight'
import { createInsightToastWindow } from './insight/toastWindow'
import { registerAutomationHandlers } from './ipc/automation'
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
import { initSentry } from './sentry'
import { isQuitting, markQuitting, quitApp } from './lifecycle'
import { createTray, updateTrayState, destroyTray } from './tray'
import { initAutoUpdater } from './updater'
import { registerRecordShortcut, setRecordAccelerator, getRecordShortcut } from './shortcuts'
import { getAppSettings, setAppSettings } from './appSettings'

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

// Default the perf log to the user data dir so marks double as lightweight prod
// telemetry. The bench runner overrides OMI_PERF_LOG to point at .bench/.
// app.getPath('userData') is valid before app.whenReady().
if (!process.env.OMI_PERF_LOG) {
  process.env.OMI_PERF_LOG = join(app.getPath('userData'), 'perf.jsonl')
}
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
  logFatal('render-process-gone', `reason=${details.reason} exitCode=${details.exitCode}`)
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
  logFatal('child-process-gone', `type=${details.type} reason=${details.reason}`)
)

// Opt-in sandbox isolation. By default Electron derives userData from the
// product name ("omi-windows"), which is the real user's data + signed-in
// Firebase session. Set OMI_SANDBOX to pin a throwaway userData dir instead,
// so a sandbox build can't share (and clobber) the production omi.db /
// local_kg schema. Must run before any DB open (db.ts resolves userData lazily
// on first IPC). NOTE: default = production data, so normal runs load memories.
// In bench mode (OMI_BENCH=1) we NEVER pin, so the runner's isolated
// --user-data-dir is honored (pinning here would override it and collide caches).
//
// The VALUE names the profile, so concurrent worktrees each get their OWN
// userData dir and never contend for the shared Chromium GPU/disk/quota caches
// (that contention crashes the WebGL brain map — the only GPU-backed surface —
// while the plain-DOM UI survives). Use a distinct OMI_SANDBOX=<name> per
// worktree to run several at once. OMI_SANDBOX=1 keeps the original shared
// "…-sandbox-chat-kg" profile for backward compatibility (no re-login).
//
// This is intentionally OPT-IN, NOT auto-derived from the worktree folder: the
// user's real data + Firebase session + onboarding floor live in the DEFAULT
// profile, and Chromium can't safely share one profile across two live
// instances anyway. So the MAIN worktree must stay on the default (real data),
// and only the SECONDARY worktree(s) you run alongside it should set
// OMI_SANDBOX=<name> to isolate. (An earlier auto-derive moved this worktree off
// the default profile and blanked the brain map's onboarding floor — never do
// that.)
// Desktop-automation bridge (real Windows UI actions). ON by default; set
// OMI_AUTOMATION='0' as a kill-switch to disable it. Gates both the IPC
// registration and the foreground-target tracker; the renderer reads the same
// flag (window.omi.automationEnabled) to skip its action-planner pre-step.
const AUTOMATION_ENABLED = process.env.OMI_AUTOMATION !== '0'

const sandbox = process.env.OMI_SANDBOX
if (sandbox && process.env.OMI_BENCH !== '1') {
  const suffix = sandbox === '1' ? 'chat-kg' : sandbox.replace(/[^a-zA-Z0-9._-]/g, '-')
  app.setPath('userData', join(app.getPath('appData'), `omi-windows-sandbox-${suffix}`))
}

// Single-instance lock: only ONE Omi runs per userData profile. A second launch
// hands off to the first (see the 'second-instance' handler) and exits. Acquired
// AFTER the sandbox repin above so distinct OMI_SANDBOX profiles (and the E2E
// harness's --user-data-dir) each get their own lock instead of contending.
const gotSingleInstanceLock = app.requestSingleInstanceLock()
if (!gotSingleInstanceLock) app.quit()

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
  updateLocalConversationTitle
} from './ipc/db'

// The first time the user closes the window to the tray, tell them Omi is still
// running (otherwise "it disappeared but didn't quit" is confusing). Shown once,
// persisted in app-settings.json.
function maybeShowCloseToTrayNotice(): void {
  if (getAppSettings().closeToTrayNoticeShown) return
  setAppSettings({ closeToTrayNoticeShown: true })
  if (!Notification.isSupported()) return
  try {
    new Notification({
      title: 'Omi is still running',
      body: 'Omi keeps listening in the tray. Right-click the tray icon to pause or quit.'
    }).show()
  } catch (e) {
    console.warn('[tray] close-to-tray notice failed:', e)
  }
}

function createWindow(): BrowserWindow {
  // Create the browser window. 1280x820 gives the two-column Record layout
  // (transcript + screen sidebar) room without overflow; min-size prevents the
  // sidebar from clipping below a usable threshold.
  const mainWindow = new BrowserWindow({
    title: 'omi',
    width: 1280,
    height: 820,
    minWidth: 1024,
    minHeight: 640,
    show: false,
    autoHideMenuBar: true,
    frame: true,
    transparent: false,
    backgroundColor: '#121212',
    icon,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      webSecurity: false, // Disabled to work around Omi API CORS preflight issues
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

  // Allow Firebase + Google OAuth popups to open as real Electron windows so
  // signInWithPopup() can postMessage back to the opener. Everything else
  // routes to the system browser.
  mainWindow.webContents.setWindowOpenHandler((details) => {
    const url = details.url
    const isOAuth =
      url.startsWith('https://accounts.google.com/') ||
      url.startsWith('https://based-hardware.firebaseapp.com/') ||
      url.includes('/__/auth/') ||
      url.includes('firebaseapp.com/__/auth')
    if (isOAuth) {
      return {
        action: 'allow',
        overrideBrowserWindowOptions: {
          width: 480,
          height: 720,
          autoHideMenuBar: true,
          webPreferences: { nodeIntegration: false, contextIsolation: true }
        }
      }
    }
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
  // Set app user model id for windows
  electronApp.setAppUserModelId('com.omiwindows.app')

  // Default open or close DevTools by F12 in development
  // and ignore CommandOrControl + R in production.
  // see https://github.com/alex8088/electron-toolkit/tree/master/packages/utils
  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  // Omi's API doesn't advertise http://localhost:5173 as a CORS-allowed origin.
  // In Electron we control the network stack, so strip the Origin header on
  // outgoing requests and inject permissive CORS response headers. Scoped to
  // the specific upstreams — everything else flows normally.
  const apiUrls = ['https://api.omi.me/*', 'https://desktop-backend-hhibjajaja-uc.a.run.app/*']
  session.defaultSession.webRequest.onBeforeSendHeaders({ urls: apiUrls }, (details, cb) => {
    const headers = { ...details.requestHeaders }
    delete headers.Origin
    delete headers.origin
    cb({ requestHeaders: headers })
  })
  session.defaultSession.webRequest.onHeadersReceived({ urls: apiUrls }, (details, cb) => {
    cb({
      responseHeaders: {
        ...details.responseHeaders,
        'access-control-allow-origin': ['*'],
        'access-control-allow-headers': ['*'],
        'access-control-allow-methods': ['GET, POST, PUT, PATCH, DELETE, OPTIONS']
      }
    })
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
  // Trivial round-trip used to measure raw IPC overhead in bench mode.
  ipcMain.handle('bench:echo', async (_e, x: number) => x)
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
  registerOmiListenHandlers()
  registerFileIndexHandlers()
  registerLocalGraphHandlers()
  registerMemoryImportHandlers()
  registerMemoryExportHandlers()
  registerKgHandlers()
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
      !!mainWindow && !mainWindow.isDestroyed() && mainWindow.isVisible() && !mainWindow.isMinimized(),
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
      trayCreated: true,
      // The harness must target the MAIN window — getAllWindows() also returns
      // the insight toast / overlay, which have different close semantics.
      mainWindowId: mainWindow.id
    }
  }

  // Defer non-essential background services until the window is ready to show, so
  // their synchronous setup (foreground-monitor koffi/user32 init ~60ms, rewind
  // capture/OCR/retention loops, screen-source prewarm) runs AFTER first paint
  // instead of delaying the window from appearing. None are needed before the UI
  // is up; their IPC handlers are already registered above.
  win.once('ready-to-show', () => {
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
  })

  // Overlay: wire IPC + global shortcut. The overlay window is created lazily on
  // first summon (so it inherits the already signed-in Firebase session).
  registerOverlayHandlers(surfaceMainWindow)
  const shortcutOk = registerOverlayShortcut(OVERLAY_ACCELERATOR, toggleOverlay)
  if (!shortcutOk) {
    console.warn(
      '[overlay] summon shortcut unavailable; overlay can still be opened via a future rebind UI'
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
    openAtLogin: app.isPackaged ? app.getLoginItemSettings().openAtLogin : false
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

  // Bench mode: after the renderer has loaded, run the fixed DB + IPC workload,
  // flush marks, and quit. Guarded entirely behind OMI_BENCH so prod is unaffected.
  if (process.env.OMI_BENCH === '1') {
    // Resolve when the renderer reports its first painted frame, so we can be
    // sure the renderer:first-paint mark is recorded before we quit (the
    // workload may otherwise finish first once seeding is fast).
    const firstPaint = new Promise<void>((resolve) => {
      ipcMain.once('perf:firstPaint', () => resolve())
    })
    // Resolve when the AUTHENTICATED shell reports it has mounted+painted
    // (renderer:app-ready). Only fires when signed in + onboarded; on the
    // Login/unauthenticated path it never arrives, so callers must keep a
    // fallback. The perf:mark handler above already records the mark on disk.
    const appReady = new Promise<void>((resolve) => {
      const onMark = (_e: unknown, name: string): void => {
        if (String(name) === 'renderer:app-ready') {
          ipcMain.off('perf:mark', onMark)
          resolve()
        }
      }
      ipcMain.on('perf:mark', onMark)
    })
    win.webContents.once('did-finish-load', async () => {
      // Animation bench: just wait for the renderer probe's jank summary, record
      // it, and quit. We deliberately DON'T run the DB/IPC workload here — its
      // main-thread + IPC traffic would land during the recording window and
      // pollute the frame-timing measurement.
      if (process.env.OMI_ANIM_BENCH === '1') {
        await new Promise<void>((resolve) => {
          ipcMain.once('perf:animResult', (_e, stats) => {
            perfMark('anim:startup', stats as Record<string, unknown>)
            resolve()
          })
          setTimeout(resolve, 15000)
        })
        flushPerfMarks()
        app.quit()
        return
      }
      try {
        // Wait for the authed shell to be ready BEFORE running the workload, so
        // the bench measures the real authed-startup path. Fall back to
        // first-paint (unauthenticated Login run) and a hard 30s cap so the
        // bench always completes. The workload runs synchronously in main and
        // would otherwise block main from processing these IPCs, back-dating the
        // marks by the workload's duration (a measurement artifact).
        // app-ready is preferred. On an authed run the spinner first-paints
        // almost immediately while auth+onboarding+mount take a few more
        // seconds, so the first-paint fallback gets an 8s grace to let app-ready
        // win; only a genuinely unauthenticated run falls through to it.
        await Promise.race([
          appReady,
          firstPaint.then(() => new Promise((r) => setTimeout(r, 8000))),
          new Promise((r) => setTimeout(r, 30000))
        ])
        // The DB/IPC workload (src/main/bench/workload.ts) was removed for the
        // public release (commit dd1904d). Bench mode now only records the
        // startup-timing marks captured above, then flushes and quits.
      } catch (e) {
        console.error('[bench] workload failed:', e)
      } finally {
        flushPerfMarks()
        app.quit()
      }
    })
  }

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

// On a normal shutdown: mark quitting (so any late close handlers don't cancel),
// tear down the tray + always-alive overlay window, flush perf marks, release the
// overlay shortcut, and dispose the automation helper + foreground-window hook.
app.on('will-quit', () => {
  markQuitting()
  destroyTray()
  const overlay = getOverlayWindow()
  if (overlay && !overlay.isDestroyed()) overlay.destroy()
  unregisterOverlayShortcut()
  flushPerfMarks()
  automationBridge.dispose()
  stopAutomationTargetTracker()
})

// In this file you can include the rest of your app's specific main process
// code. You can also put them in separate files and require them here.
