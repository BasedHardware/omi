// Client-side preferences persisted in localStorage. Read once on import; the
// setters write back to localStorage and notify subscribers so live components
// can react.
import { DEFAULT_LANGUAGE } from './languages'
import type { VoiceProviderSetting } from './voice/sessionMachine'

const KEY = 'omi-windows-prefs-v1'

// Font-scale bounds live here (the SSOT) and are re-exported by lib/fontScale.ts,
// which consumers import from. Declaring them in this low-level module keeps the
// dependency one-directional (fontScale.ts → preferences.ts) with no import cycle,
// so `normalizeFontScale` can run safely at eval time (in load() below) regardless
// of module load order.
export const FONT_SCALE_MIN = 0.5
export const FONT_SCALE_MAX = 2.0
export const FONT_SCALE_DEFAULT = 1.0

// Font scale is user-tunable in [0.5, 2.0] (see lib/fontScale.ts). Clamp on both
// read and write so a hand-edited localStorage blob can't push the whole UI to an
// unusable size; drop non-finite junk so the 1.0 default applies.
function normalizeFontScale(p: Preferences): void {
  if (typeof p.fontScale !== 'number' || !Number.isFinite(p.fontScale)) {
    delete p.fontScale
    return
  }
  p.fontScale = Math.min(FONT_SCALE_MAX, Math.max(FONT_SCALE_MIN, p.fontScale))
}

export type Preferences = {
  captionIntervalMs: number
  showRecordingBadge: boolean
  reduceMotion: boolean
  // Set during the startup wizard.
  displayName?: string
  language: string
  // Spoken-language candidates for push-to-talk (A3). Empty/undefined (default)
  // ⇒ INERT: PTT transcribes with the static `language` above, exactly as
  // before. Non-empty ⇒ per-turn feed-forward — the last provider-detected
  // language, when it is one of these candidates, hints the NEXT PTT turn
  // instead of the static pref (corrects the provider mislabeling short
  // utterances). Base ISO 639-1 codes, e.g. ['en', 'ru'].
  voiceLanguages?: string[]
  // Chat conversation grouping. 'per-launch' = a new conversation each app run
  // (default, original behavior); 'infinite' = one ongoing conversation shared
  // by the main window and the overlay.
  chatHistoryMode: 'per-launch' | 'infinite'
  // Multi-chat sessions (macOS @AppStorage("multiChatEnabled")). Default OFF:
  // the Hub shows the single Synced Chat thread, byte-identical to today. When ON
  // *and* the chat engine is pi_mono, the Hub chat panel gains the multi-chat
  // header (session switcher + new-chat + history). Undefined ⇒ OFF; the header
  // reads it as `=== true`. It does NOT flip the engine — the two flags are
  // independent (the header simply stays hidden under the legacy engine).
  multiChatEnabled?: boolean
  recordingConsentedAt?: number
  // The single goal the user picked during onboarding ("Pick one goal"). Stored
  // locally and best-effort synced to the Omi goals backend.
  goal?: string
  // Opt-in for the desktop-automation bridge ("let Omi take actions"). Set when
  // the user grants the Automation onboarding step. Undefined = not opted in, so
  // the chat action-planner pre-step stays off (in addition to the OMI_AUTOMATION
  // env kill-switch).
  automationConsentedAt?: number
  // The user's chosen floating-bar summon shortcut (Electron accelerator string,
  // e.g. "CommandOrControl+Space"). Set in the onboarding shortcut step; pushed
  // to main on startup so it survives restarts. Undefined = use main's default.
  overlayShortcut?: string
  // Always-on microphone capture. When true, the app streams the mic to
  // /v4/listen from launch and the backend creates conversations (macOS-faithful).
  // Set by the onboarding opt-in step; toggled in Settings → Rewind. Undefined =
  // off (opt-in), so existing users are unaffected until they enable it.
  continuousRecording?: boolean
  // Auto-cleanup of empty conversations + junk memories. 'dry-run' (default) logs
  // what it WOULD delete without deleting; 'live' deletes (rate-limited); 'off'
  // disables the sweep. Read with `?? 'dry-run'`.
  retentionMode?: 'off' | 'dry-run' | 'live'
  onboardingCompletedAt?: number
  // The onboarding step the user last reached, persisted so quitting mid-wizard
  // resumes where they left off instead of restarting at step 0. Cleared when
  // onboarding completes or is reset. Clamped on read (the step list can change
  // between app versions).
  onboardingStep?: number
  // Set when the user acknowledges the one-time "Background & privacy"
  // interstitial (existing users, post-update). Undefined = not yet shown. New
  // users consent inline during onboarding instead, so this stays undefined for
  // them and the interstitial never fires (it's gated on onboardingCompletedAt).
  backgroundConsentAt?: number
  // Local VAD gate: when the on-device voice-activity gate runs, silence is
  // dropped before audio reaches the transcription backend (saves cost). Applies
  // to the always-on / ambient capture lanes (read at session start in
  // AudioSessionHost); PTT is passthrough regardless. Undefined = enabled
  // (gated), the macOS-faithful default. Set false to send all audio ungated.
  vadGateEnabled?: boolean
  // Fall back to the original Home screen instead of the Hub. Undefined = off, so
  // the Hub is what a user sees by default; Settings → Appearance can switch back.
  useLegacyHomeDesign?: boolean
  // Mute other apps' system audio while push-to-talk is capturing (macOS
  // SystemAudioMuteController parity — so a playing video doesn't bleed into the
  // mic and you can hear yourself think). Undefined = ON, the macOS-faithful
  // default; set false to leave system audio alone. Only the MUTE call is gated
  // on this — the restore is unconditional, so flipping the pref off mid-hold can
  // never strand the machine muted.
  pttMuteSystemAudio?: boolean
  // Speak Omi's reply to TYPED floating-bar questions too (macOS
  // shortcut_floatingBarTypedQuestionVoiceAnswersEnabled). Undefined = off
  // (opt-in), matching macOS's default: PTT/voice-originated replies are always
  // spoken; a typed bar question is spoken only when this is true.
  floatingBarTypedVoiceEnabled?: boolean
  // Launch commands for the external coding agents (OpenClaw/Hermes/Codex).
  // Set in Settings → Agents; undefined = not connected (the matching
  // OMI_*_ADAPTER_COMMAND env var still works as a power-user override).
  // Claude Code is built in and needs no command.
  agentCommands?: { openclaw?: string; hermes?: string; codex?: string }
  // Global UI font-scale multiplier (macOS FontScaleSettings parity), applied as
  // a root rem multiplier in lib/fontScale.ts. Range [0.5, 2.0], clamped on
  // read/write; undefined = 1.0 (default). Set in Settings → General → Font Size
  // and via the Ctrl+= / Ctrl+- / Ctrl+0 shortcuts.
  fontScale?: number
  // Realtime-voice provider selection (macOS RealtimeOmniProvider.selectedProvider).
  // 'auto' (default) defers to autoModelSelector's daily quality/speed pick;
  // 'openai'/'gemini' pins a concrete lane. Resolved to a concrete VoiceProvider
  // at session start via resolveEffectiveVoiceProvider(). Track-6 owns the UI toggle.
  voiceProvider?: VoiceProviderSetting
  // Warm-hub system-wide PTT kill-switch (Track 2 / A5 PR-6). Default ON (flipped
  // after the driver was made functional + live-verified end-to-end): a PTT press
  // whose hub is available routes to the warm realtime hub (native audio in + reply,
  // recorded into the one chat timeline), with graceful byte-for-byte cascade
  // fallback when the hub is cold/unavailable. Setting it explicitly false restores
  // the shipped `omniSTT`-only cascade with no restart — the next route selection
  // picks `omniSTT` and the eager warm tears down. (`selectPttRoute` still treats
  // undefined as off at the structural layer; the ON default is applied here so
  // every user gets the hub unless they opt out.)
  pttHubEnabled?: boolean
  // Tap-to-lock (macOS PushToTalkManager.doubleTapForLock): a quick double-tap of
  // the summon hotkey latches hands-free listening (mic stays open, no key held)
  // until the next tap. DEFAULT ON — read as `!== false` so an unset pref latches.
  // Hold-to-talk is unchanged either way.
  doubleTapForLock?: boolean
}

const defaults: Preferences = {
  captionIntervalMs: 2000,
  showRecordingBadge: true,
  reduceMotion: false,
  language: DEFAULT_LANGUAGE,
  // Infinite by default: one ongoing conversation that persists across launches
  // and is accessible from the beginning (the Home thread windows it in as you
  // scroll up). Users can switch back to 'per-launch' in Settings.
  chatHistoryMode: 'infinite',
  // Auto is the out-of-the-box default (macOS RealtimeOmniProvider.auto): the
  // daily benchmark pick decides the lane until the user pins one in Settings.
  voiceProvider: 'auto',
  // Warm realtime hub is ON by default (flipped after live end-to-end verification):
  // a PTT press routes to the hub when available, with cascade fallback and its text
  // recorded to the one chat timeline. Users can opt out in Settings (sets false).
  pttHubEnabled: true
}

function load(): Preferences {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return { ...defaults }
    const parsed = JSON.parse(raw) as Partial<Preferences>
    const merged = { ...defaults, ...parsed }
    normalizeFontScale(merged)
    return merged
  } catch {
    return { ...defaults }
  }
}

let current: Preferences = load()
const listeners = new Set<(p: Preferences) => void>()

// Cross-window sync: the main window, overlay, and hidden capture window are
// separate renderer processes sharing one localStorage origin, but each caches
// `current` at module load. A write in one window fires the 'storage' event in
// the OTHERS — reload there so e.g. an agent command saved in the main window's
// Settings reaches the overlay's chat, or a continuousRecording flip from the
// tray/Settings reaches the capture window, without an app restart.
if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('storage', (e) => {
    if (e.key !== KEY) return
    current = load()
    listeners.forEach((cb) => cb(current))
  })
}

export function getPreferences(): Preferences {
  return current
}

export function setPreferences(patch: Partial<Preferences>): void {
  // Read-modify-write against the LIVE stored value, not this window's cache:
  // several windows (main, overlay, toast, capture) share the key, and the
  // `storage`-event cache refresh is asynchronous — writing `current` here can
  // resurrect a stale blob and silently drop another window's recent write
  // (lost-update clobber, found live during Phase 2 verification). Merging the
  // patch onto a fresh load makes writes field-granular.
  current = { ...load(), ...patch }
  normalizeFontScale(current)
  try {
    localStorage.setItem(KEY, JSON.stringify(current))
  } catch {
    /* quota / privacy mode */
  }
  listeners.forEach((cb) => cb(current))
}

export function onPreferencesChange(cb: (p: Preferences) => void): () => void {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

export function isOnboardingComplete(): boolean {
  return typeof getPreferences().onboardingCompletedAt === 'number'
}

// Clear the user-identity fields (name, chosen goal) on sign-out so a different
// account on the same machine doesn't inherit them. Device settings, consents,
// and onboarding state in the same blob are machine-scoped and kept. Read-
// modify-writes the live stored value like setPreferences (multi-window safe).
export function clearUserScopedPreferences(): void {
  const next = { ...load() }
  delete next.displayName
  delete next.goal
  current = next
  try {
    localStorage.setItem(KEY, JSON.stringify(current))
  } catch {
    /* quota / privacy mode */
  }
  listeners.forEach((cb) => cb(current))
}

// One-shot, in-memory route the app shell should jump to right after onboarding
// finishes (e.g. "Take me to my tasks" → '/tasks'). Not persisted — it only
// bridges the onboarding→shell handoff. Navigating from the onboarding screen
// directly races the onboarding gate's redirect to /home, so instead we record
// the destination here and let the shell consume it once it mounts.
let pendingRoute: string | null = null

export function setPendingRoute(path: string | null): void {
  pendingRoute = path
}

export function consumePendingRoute(): string | null {
  const path = pendingRoute
  pendingRoute = null
  return path
}

export function completeOnboarding(): void {
  // Clear the saved step so a future re-onboarding starts fresh rather than
  // resuming at the (now stale) final step.
  setPreferences({ onboardingCompletedAt: Date.now(), onboardingStep: undefined })
}

// Clear the completion flag so the startup wizard runs again. Keeps the rest of
// the saved preferences (name, language, consent). Subscribers are notified, so
// App's reactive onboarding gate re-routes to the wizard immediately.
export function resetOnboarding(): void {
  const next = { ...load() }
  delete next.onboardingCompletedAt
  // Restart the wizard from the beginning, not the previously saved step.
  delete next.onboardingStep
  current = next
  try {
    localStorage.setItem(KEY, JSON.stringify(current))
  } catch {
    /* quota / privacy mode */
  }
  listeners.forEach((cb) => cb(current))
}
