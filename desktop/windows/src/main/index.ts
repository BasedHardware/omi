import { app, shell, BrowserWindow, ipcMain, session, nativeImage, desktopCapturer } from 'electron'
import { join } from 'path'
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

// Default the perf log to the user data dir so marks double as lightweight prod
// telemetry. The bench runner overrides OMI_PERF_LOG to point at .bench/.
// app.getPath('userData') is valid before app.whenReady().
if (!process.env.OMI_PERF_LOG) {
  process.env.OMI_PERF_LOG = join(app.getPath('userData'), 'perf.jsonl')
}
perfMark('app:start')

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

const icon = nativeImage.createFromPath(iconPath)
import {
  remapConversationId,
  insertLocalConversation,
  getLocalConversation,
  listLocalConversations,
  deleteLocalConversation,
  updateLocalConversationTitle
} from './ipc/db'

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
    mainWindow.show()
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

  const mainWindow = createWindow()

  // Defer non-essential background services until the window is ready to show, so
  // their synchronous setup (foreground-monitor koffi/user32 init ~60ms, rewind
  // capture/OCR/retention loops, screen-source prewarm) runs AFTER first paint
  // instead of delaying the window from appearing. None are needed before the UI
  // is up; their IPC handlers are already registered above.
  mainWindow.once('ready-to-show', () => {
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
  registerOverlayHandlers(() => {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.show()
    mainWindow.focus()
  })
  const shortcutOk = registerOverlayShortcut(OVERLAY_ACCELERATOR, toggleOverlay)
  if (!shortcutOk) {
    console.warn(
      '[overlay] summon shortcut unavailable; overlay can still be opened via a future rebind UI'
    )
  }
  // Closing the main window must also tear down the always-alive (hidden) overlay
  // window — otherwise it keeps a window open, 'window-all-closed' never fires, and
  // the app lingers as an invisible background process (overlay has skipTaskbar).
  mainWindow.on('closed', () => {
    const overlay = getOverlayWindow()
    if (overlay && !overlay.isDestroyed()) overlay.destroy()
  })

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
    mainWindow.webContents.once('did-finish-load', async () => {
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
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// On a normal shutdown: flush buffered perf marks, release the overlay shortcut,
// and tear down the automation helper process + foreground-window hook.
app.on('will-quit', () => {
  unregisterOverlayShortcut()
  flushPerfMarks()
  automationBridge.dispose()
  stopAutomationTargetTracker()
})

// In this file you can include the rest of your app's specific main process
// code. You can also put them in separate files and require them here.
