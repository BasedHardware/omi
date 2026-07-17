import { useEffect } from 'react'
import { HashRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { HOME_PATH } from './routes/manifest'
import { useAuth } from './hooks/useAuth'
import { Login } from './pages/Login'
import { AppChrome } from './components/layout/AppChrome'
import { MainViews } from './components/layout/MainViews'
import { TitleBar } from './components/layout/TitleBar'
import { Spinner } from './components/ui/Spinner'
import { DbRecoveryNotice } from './components/ui/DbRecoveryNotice'
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
import { GlowWindow } from './components/glow/GlowWindow'
import { CaptureApp } from './capture/CaptureApp'
import { LiveMirrorHost } from './components/recording/LiveMirrorHost'
import { LiveNotesHost } from './components/recording/LiveNotesHost'
import { auth, onAuthStateChanged } from './lib/firebase'
import { invalidateConversationsCache } from './lib/pageCache'
import { startOutboxSweep, stopOutboxSweep } from './lib/sync/outboxSweep'
import { useAppLifetimeJobs } from './lib/appLifetimeJobs'
import { runAnimBench } from './lib/dev/animBench'
import { InsightToast } from './components/insight/InsightToast'
import { TrayStateHost } from './components/tray/TrayStateHost'
import { ChatBridgeHost } from './components/chat/ChatBridgeHost'
import { VoiceHubDriverHost } from './components/chat/VoiceHubDriverHost'
import { UsageLimitPopup } from './components/settings/billing/UsageLimitPopup'
import { ClaudeAuthSheet } from './components/settings/billing/ClaudeAuthSheet'
import { UsageLimitTriggerHost } from './components/settings/billing/UsageLimitTriggerHost'
import { RecordHotkeyHost } from './components/hotkeys/RecordHotkeyHost'
import { BackgroundConsentInterstitial } from './components/consent/BackgroundConsentInterstitial'
import { isSecondaryWindow } from './lib/windowRole'
import { attachVoiceE2eHook } from './lib/voice/e2eHook'
import { attachLiveNotesE2eHook } from './lib/liveNotes/e2eHook'
import { PrimitivesGallery } from './components/ui/__gallery/PrimitivesGallery'
import { refreshIfStale } from './lib/voice/autoModelSelector'
import { refreshAboutUserCard, resetAboutUserCard } from './lib/voice/aboutUser'
import { refreshUserVocabulary, resetUserVocabulary } from './lib/ptt/userVocabulary'

// The overlay, insight-toast, and hidden capture windows load this same bundle at
// their own hash routes. Window-singleton hosts (tray state, auth-change fan-out)
// must run only in the main window, so gate on the initial hash — set by main at
// load time, before routing.
const IS_SECONDARY_WINDOW = isSecondaryWindow()

function AppShellInner(): React.JSX.Element {
  const { recorder, pickerOpen, setPickerOpen } = useAppState()
  const navigate = useNavigate()
  // Home paints a darker stage than the app base; tell the title-bar strip so it
  // matches that stage instead of floating as a lighter band above it (see TitleBar).
  const isHome = useLocation().pathname === HOME_PATH
  // The transparent strip blends via CSS, but the native WCO caption cluster can't
  // be transparent — flip its tone to the home stage on Home (and back elsewhere)
  // so the min/max/close buttons don't sit as a lighter box. Main window only.
  useEffect(() => {
    window.omi?.setTitleBarSurface?.(isHome)
  }, [isHome])

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

  // App-lifetime outbox retry sweep. This shell mounts only in the main window
  // once signed in + onboarded, and unmounts on sign-out, so it doubles as the
  // sweep's start-on-sign-in / stop-on-sign-out gate. Without it a PTT-only user
  // who never opens Conversations has a failed sync wedged all session.
  useEffect(() => {
    startOutboxSweep()
    return () => stopOutboxSweep()
  }, [])

  // The four app-lifetime background engines (knowledge graph, screen synthesis,
  // insights, retention). They live in the shell — NOT in a page — so that neither
  // Home design owns them and swapping Home cannot silently switch them off. See
  // lib/appLifetimeJobs.ts for the full why.
  useAppLifetimeJobs()

  return (
    <div className="app-canvas flex h-full min-h-0 flex-col">
      {/* Native-caption drag strip (Window Controls Overlay). */}
      <TitleBar onHome={isHome} />
      {/* Only renders when omi.db was found corrupt and repaired at startup. */}
      <DbRecoveryNotice />
      <AppChrome>
        <MainViews />
      </AppChrome>
      <SourcePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onPick={recorder.pickScreen}
      />
      {/* Mirror the capture window's always-on live transcript into this window and
          run the on-save UI side effects. Capture itself (Rewind, mic, PTT, screen)
          runs in the hidden capture window now. */}
      <LiveMirrorHost />
      {/* Generates live AI notes off the mirrored transcript, app-root scoped so
          generation isn't gated on the notes panel being open. */}
      <LiveNotesHost />
      {/* One-time background/privacy consent for existing (already-onboarded)
          users. Self-gates via shouldShowBackgroundConsent. */}
      <BackgroundConsentInterstitial />
      {/* Bridges the bar's chat viewport to this window's single chat engine
          (INV-CHAT-1): drives chat.send on bar:sendChat, broadcasts projected
          state back to the bar. Main window only (this shell never mounts in the
          bar/capture windows). */}
      <ChatBridgeHost />
      {/* Warm-hub PTT driver (A5 PR-6b, gated on pttHubEnabled). Main window only:
          the coordinator + hub + pcmPlayer live here (D1). Inert until the bar
          delegates a hold (flag on) — flag off it never receives a begin. */}
      <VoiceHubDriverHost />
      {/* Usage-limit popup + its chat-quota trigger. The popup deep-links into
          the Plan & Usage settings tab; the trigger watches the shared chat
          engine and raises it once when a send lands on an exhausted quota. */}
      <UsageLimitTriggerHost />
      <UsageLimitPopup />
      {/* "Upgrade to Omi Pro" upsell shown alongside the parallel Claude Code
          OAuth launch — ONLY on an in-chat auth_required event (Claude Code's
          token rejected mid-turn), matching macOS's isClaudeAuthRequired sheet.
          The Settings → Agents sign-in button does plain OAuth, no upsell.
          Completing sign-in auto-closes it and grants Claude with no purchase. */}
      <ClaudeAuthSheet />
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
    if (!IS_SECONDARY_WINDOW) {
      attachVoiceE2eHook()
      attachLiveNotesE2eHook()
    }
  }, [])

  // Warm the daily "Auto" realtime-voice model pick, so the user's FIRST voice
  // session already connects on the current pick instead of the Gemini default
  // (macOS warms it at launch — OmiApp.swift:310; starting a session also refreshes,
  // but that resolves synchronously from the cache, so the in-flight fetch lands too
  // late for that session). No-op when the cached pick is < 24h old.
  //
  // Gated on a signed-in user, NOT on mount: Firebase restores the session
  // asynchronously, so firing at mount would go out unauthenticated, 401, and cache
  // the Gemini fallback with a fresh 24h timestamp — pinning the user to Gemini for
  // a day. (Mac has no such window; its auth is restored before the launch call.)
  //
  // The <about_user> card is warmed on the same signal and for the same reason
  // (macOS builds it when the hub starts — RealtimeHubController.swift:813 — not
  // when a session starts). Starting a session refreshes it too, but reads the
  // CACHE synchronously, so a launch-time miss would ship the user's FIRST voice
  // session with no card at all — exactly the "assistant doesn't know who I am"
  // gap this card exists to close. Sign-out drops it so it cannot outlive the
  // account (and abandons any in-flight build).
  //
  // The PTT custom-vocabulary cache is warmed and dropped on the same signal for
  // the same reason: collectPttKeywords reads it synchronously, so a launch-time
  // miss would ship the first hold without the user's custom terms.
  useEffect(() => {
    if (IS_SECONDARY_WINDOW) return
    return onAuthStateChanged(auth, (user) => {
      if (user) {
        refreshIfStale()
        refreshAboutUserCard()
        refreshUserVocabulary()
      } else {
        resetAboutUserCard()
        resetUserVocabulary()
      }
    })
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
        {/* The focus halo: a click-through ring around the user's active window.
            Ungated (like /capture) — it paints geometry main hands it and holds
            no user data. */}
        <Route path="/glow" element={<GlowWindow />} />
        {/* The hidden capture window. Ungated (like /overlay) — it owns capture
            regardless of the UI auth gate; its hosts self-gate on auth. */}
        <Route path="/capture" element={<CaptureApp />} />
        {/* Dev-only visual harness for the shared ui/* primitives. DEV-gated so
            it tree-shakes out of packaged renderer builds; placed before the
            auth-gated catch-all so it renders without sign-in. */}
        {import.meta.env.DEV && <Route path="/__ui-gallery" element={<PrimitivesGallery />} />}
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
