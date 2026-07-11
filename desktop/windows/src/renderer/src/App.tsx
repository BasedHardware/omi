import { useEffect } from 'react'
import { HashRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from './hooks/useAuth'
import { Login } from './pages/Login'
import { Sidebar } from './components/layout/Sidebar'
import { MainViews } from './components/layout/MainViews'
import { TitleBar } from './components/layout/TitleBar'
import { Spinner } from './components/ui/Spinner'
import { purgeAppMemoriesOnce } from './lib/appMemories'
import { AppStateProvider } from './state/AppStateProvider'
import { useAppState } from './state/appState'
import { SourcePicker } from './components/SourcePicker'
// Imported DIRECTLY (NOT lazy/Suspense). Code-splitting the Onboarding page
// (commit c226cac, for the three.js bundle win) repeatedly blanked the onboarding
// brain map — wrapping the page in Suspense breaks the BrainGraph render. The
// direct import keeps the map reliable; the bundle-size win is not worth it.
import { Onboarding } from './pages/Onboarding'
import { consumePendingRoute } from './lib/preferences'
import { useOnboardingComplete } from './hooks/useOnboardingComplete'
import { getPreferences } from './lib/preferences'
import { SandboxBadge } from './components/SandboxBadge'
import { BarApp } from './components/bar/BarApp'
import { CaptureApp } from './capture/CaptureApp'
import { LiveMirrorHost } from './components/recording/LiveMirrorHost'
import { auth, onAuthStateChanged } from './lib/firebase'
import { invalidateConversationsCache } from './lib/pageCache'
import { runAnimBench } from './lib/dev/animBench'
import { InsightToast } from './components/insight/InsightToast'
import { TrayStateHost } from './components/tray/TrayStateHost'
import { ChatBridgeHost } from './components/chat/ChatBridgeHost'
import { RecordHotkeyHost } from './components/hotkeys/RecordHotkeyHost'
import { BackgroundConsentInterstitial } from './components/consent/BackgroundConsentInterstitial'
import { isSecondaryWindow } from './lib/windowRole'
import { attachVoiceE2eHook } from './lib/voice/e2eHook'

// The overlay, insight-toast, and hidden capture windows load this same bundle at
// their own hash routes. Window-singleton hosts (tray state, auth-change fan-out)
// must run only in the main window, so gate on the initial hash — set by main at
// load time, before routing.
const IS_SECONDARY_WINDOW = isSecondaryWindow()

function AppShellInner(): React.JSX.Element {
  const { recorder, pickerOpen, setPickerOpen } = useAppState()
  // Settings is a full-screen view with its own tab rail + Back button, so the
  // main app sidebar is hidden there.
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const hideSidebar = pathname === '/settings'

  // Honor a one-shot destination requested by onboarding (e.g. the final
  // "Take me to my tasks" button). The shell mounts at /home after the
  // onboarding gate redirects; we consume the pending route here and jump to it.
  useEffect(() => {
    const dest = consumePendingRoute()
    if (dest) navigate(dest, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Startup-phase mark for the AUTHENTICATED path: the heavy authed shell
  // (MainViews + sidebar + providers) has now mounted, so a double-rAF lands
  // after its first painted frame. The bench (OMI_BENCH) waits for this before
  // measuring/quitting, so the loop can target real authed-startup cost rather
  // than the lightweight Login screen. No-op on prod (perfMark is buffered).
  useEffect(() => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => window.omi?.perfMark('renderer:app-ready'))
    })
    // Start the animation-jank probe (dev-only; no-op unless OMI_ANIM_BENCH).
    // Runs as the entrance animations (sidebar slide, content fade) play.
    if (import.meta.env.DEV) runAnimBench()
  }, [])

  // The overlay is a separate window with its own conversations cache, so when it
  // saves a chat it can't invalidate ours directly. Main rebroadcasts the change
  // here so this window's Conversations tab refreshes without a relaunch.
  useEffect(() => window.omi.onConversationsChanged(() => invalidateConversationsCache()), [])

  return (
    <div className="app-canvas flex h-full min-h-0 flex-col">
      {/* Native-caption drag strip (Window Controls Overlay). */}
      <TitleBar />
      <div className="flex min-h-0 flex-1">
        {!hideSidebar && <Sidebar />}
        <main className="page-outlet relative z-10 min-h-0 flex-1 overflow-hidden">
          <MainViews />
        </main>
      </div>
      <SourcePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onPick={recorder.pickScreen}
      />
      {/* Mirror the capture window's always-on live transcript into this window and
          run the on-save UI side effects. Capture itself (Rewind, mic, PTT, screen)
          runs in the hidden capture window now. */}
      <LiveMirrorHost />
      {/* One-time background/privacy consent for existing (already-onboarded)
          users. Self-gates via shouldShowBackgroundConsent. */}
      <BackgroundConsentInterstitial />
      {/* Bridges the bar's chat viewport to this window's single chat engine
          (INV-CHAT-1): drives chat.send on bar:sendChat, broadcasts projected
          state back to the bar. Main window only (this shell never mounts in the
          bar/capture windows). */}
      <ChatBridgeHost />
    </div>
  )
}

// Marks the root when the window was created with the Win11 Mica material so
// the canvas goes translucent. Main window only — the bar/toast/capture windows
// own their own transparent backgrounds (they never get data-mica). The tint
// itself lives entirely in CSS: globals.css `html[data-mica='true']` paints
// body/#root with `rgba(15,15,15,0.82) !important`, which outranks the inline
// `style="background: transparent"` that index.html (shared by every window)
// hardcodes. So this effect only has to flip the attribute.
function useMicaChrome(): void {
  useEffect(() => {
    if (IS_SECONDARY_WINDOW) return
    if (window.omi?.micaEnabled) document.documentElement.dataset.mica = 'true'
  }, [])
}

function AppShell(): React.JSX.Element {
  // One-time cleanup of legacy "Uses <App>" memories (macOS parity — app data
  // lives in the local KG, not in memories). Guarded internally so it runs at
  // most once per install; best-effort, never blocks the UI.
  useEffect(() => {
    void purgeAppMemoriesOnce()
  }, [])

  return (
    <AppStateProvider>
      <AppShellInner />
    </AppStateProvider>
  )
}

function App(): React.JSX.Element {
  const { user, loading } = useAuth()
  useMicaChrome()
  // Under the dev perf bench, treat the user as already onboarded so the authed
  // shell mounts (a returning user always is). The onboarding flag lives in
  // origin-scoped localStorage, which the file:// bench profile can't inherit
  // from the dev session, so without this the bench would stall on the wizard.
  // DEV-gated so the bypass tree-shakes out of packaged renderer builds. The
  // OMI_E2E_FAKE_AUTH shell E2E does the same on a fresh throwaway profile, but
  // must survive the production build (it runs the real out/ bundle). Forcing
  // onboarded here — rather than seeding the onboardingCompletedAt pref — also
  // keeps the background-consent interstitial closed (it gates on that pref),
  // so the sidebar under test is never obstructed.
  const onboarded =
    useOnboardingComplete() ||
    (import.meta.env.DEV && !!window.omi?.isBench) ||
    !!window.omi?.e2eFakeAuth

  // Tell main whether the summon shortcut may open the overlay. Enabled once
  // onboarding is complete; during onboarding the shortcut-setup step enables it
  // early (and warms the overlay) so the user can test the press there. This
  // effect never disables what that step turned on, since `onboarded` only
  // transitions false→true.
  useEffect(() => {
    if (onboarded) window.omiOverlay?.setEnabled(true)
  }, [onboarded])

  // Push the user's saved summon shortcut to main on startup so their choice
  // survives restarts (main registers its default at launch; this re-applies the
  // persisted accelerator once the renderer mounts).
  useEffect(() => {
    const accel = getPreferences().overlayShortcut
    if (accel) void window.omiOverlay?.setAccelerator(accel)
  }, [])

  // Main window fans out auth transitions to the hidden capture window so it can
  // refresh its own Firebase session (and thus its listen-WS auth). Re-sent when
  // the capture window restarts, so a fresh one syncs immediately.
  // Voice test hook (no-op unless OMI_E2E=1) — attached at the ROOT so the
  // smoke harness can drive the voice controller even on the signed-out screen
  // (its error-path assertion starts a session with no auth). Main window only.
  useEffect(() => {
    if (!IS_SECONDARY_WINDOW) attachVoiceE2eHook()
  }, [])

  useEffect(() => {
    if (IS_SECONDARY_WINDOW) return
    const send = (): void =>
      window.omi?.captureCommand?.({ type: 'auth-changed', uid: auth.currentUser?.uid ?? null })
    const unsubAuth = onAuthStateChanged(auth, send)
    const unsubRestart = window.omi?.onCaptureEvent?.((ev) => {
      if (ev.type === 'capture-window-restarted') send()
    })
    return () => {
      unsubAuth()
      unsubRestart?.()
    }
  }, [])

  if (loading) {
    return (
      <div className="app-canvas flex h-full items-center justify-center">
        {!IS_SECONDARY_WINDOW && <TitleBar variant="overlay" />}
        <SandboxBadge />
        <Spinner label="Loading Omi…" />
      </div>
    )
  }

  return (
    <HashRouter>
      <SandboxBadge />
      {/* Tray state reporting + tray-driven pause. Main window only (not the
          overlay/insight-toast windows sharing this bundle). */}
      {!IS_SECONDARY_WINDOW && <TrayStateHost />}
      {!IS_SECONDARY_WINDOW && <RecordHotkeyHost />}
      <Routes>
        <Route path="/insight-toast" element={<InsightToast />} />
        {/* The top-edge bar window (replaces the old floating overlay). */}
        <Route path="/bar" element={<BarApp />} />
        {/* The hidden capture window. Ungated (like /overlay) — it owns capture
            regardless of the UI auth gate; its hosts self-gate on auth. */}
        <Route path="/capture" element={<CaptureApp />} />
        <Route
          path="/login"
          element={
            user ? (
              <Navigate to="/home" replace />
            ) : (
              <>
                <TitleBar variant="overlay" />
                <Login />
              </>
            )
          }
        />
        <Route
          path="/onboarding"
          element={
            !user ? (
              <Navigate to="/login" replace />
            ) : onboarded ? (
              <Navigate to="/home" replace />
            ) : (
              // Onboarding is imported DIRECTLY (no lazy/Suspense) so the
              // BrainGraph map renders reliably — see the import comment. Screen
              // capture during onboarding is owned by the always-alive capture
              // window now (it seeds the hot currentScreen cache), so no capture
              // host is mounted here.
              <>
                <TitleBar variant="overlay" />
                <Onboarding />
              </>
            )
          }
        />
        <Route
          path="/*"
          element={
            !user ? (
              <Navigate to="/login" replace />
            ) : !onboarded ? (
              <Navigate to="/onboarding" replace />
            ) : (
              <AppShell />
            )
          }
        />
      </Routes>
    </HashRouter>
  )
}

export default App
