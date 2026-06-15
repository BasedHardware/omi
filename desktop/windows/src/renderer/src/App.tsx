import { useEffect } from 'react'
import { HashRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from './hooks/useAuth'
import { Login } from './pages/Login'
import { Sidebar } from './components/layout/Sidebar'
import { MainViews } from './components/layout/MainViews'
import { Spinner } from './components/ui/Spinner'
import { purgeAppMemoriesOnce } from './lib/appMemories'
import { AppStateProvider, useAppState } from './state/AppStateProvider'
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
import { OverlayApp } from './components/overlay/OverlayApp'
import { RewindCaptureHost } from './components/rewind/RewindCaptureHost'
import { ContinuousRecordingHost } from './components/recording/ContinuousRecordingHost'
import { invalidateConversationsCache } from './lib/pageCache'
import { runAnimBench } from './lib/animBench'
import { InsightToast } from './components/insight/InsightToast'

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
    // Start the animation-jank probe (no-op unless OMI_ANIM_BENCH). Runs as the
    // entrance animations (sidebar slide, content fade) play.
    runAnimBench()
  }, [])

  // The overlay is a separate window with its own conversations cache, so when it
  // saves a chat it can't invalidate ours directly. Main rebroadcasts the change
  // here so this window's Conversations tab refreshes without a relaunch.
  useEffect(() => window.omi.onConversationsChanged(() => invalidateConversationsCache()), [])

  return (
    <div className="app-canvas flex h-full min-h-0">
      {!hideSidebar && <Sidebar />}
      <main className="page-outlet relative z-10 min-h-0 flex-1 overflow-hidden">
        <MainViews />
      </main>
      {/* Hidden video sink for screen-capture recording mode. Invisible, but
          mounted app-wide so the screen stream has a render target regardless of
          which tab is active. */}
      <video
        ref={recorder.videoRef}
        muted
        className="pointer-events-none fixed left-0 top-0 h-px w-px opacity-0"
      />
      <SourcePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onPick={recorder.pickScreen}
      />
      {/* Background screen capture for Rewind (runs while the app is open). */}
      <RewindCaptureHost />
      {/* Always-on mic capture for continuous recording mode. */}
      <ContinuousRecordingHost />
    </div>
  )
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
  // Under the perf bench, treat the user as already onboarded so the authed
  // shell mounts (a returning user always is). The onboarding flag lives in
  // origin-scoped localStorage, which the file:// bench profile can't inherit
  // from the dev session, so without this the bench would stall on the wizard.
  const onboarded = useOnboardingComplete() || !!window.omi?.isBench

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

  if (loading) {
    return (
      <div className="app-canvas flex h-full items-center justify-center">
        <SandboxBadge />
        <Spinner label="Loading Omi…" />
      </div>
    )
  }

  return (
    <HashRouter>
      <SandboxBadge />
      <Routes>
        <Route path="/insight-toast" element={<InsightToast />} />
        <Route path="/overlay" element={<OverlayApp />} />
        <Route path="/login" element={user ? <Navigate to="/home" replace /> : <Login />} />
        <Route
          path="/onboarding"
          element={
            !user ? (
              <Navigate to="/login" replace />
            ) : onboarded ? (
              <Navigate to="/home" replace />
            ) : (
              <>
                {/* Run screen capture during onboarding too, so the hot
                    currentScreen cache is seeded and chat can read the screen
                    while the user is still in the wizard. Post-onboarding this
                    host is mounted by AppShell; routes are mutually exclusive so
                    only one host is ever live (no double getUserMedia stream). */}
                <RewindCaptureHost />
                {/* Onboarding is imported DIRECTLY (no lazy/Suspense) so the
                    BrainGraph map renders reliably — see the import comment. */}
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
