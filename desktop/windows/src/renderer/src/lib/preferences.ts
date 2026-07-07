// Client-side preferences persisted in localStorage. Read once on import; the
// setters write back to localStorage and notify subscribers so live components
// can react.
import { DEFAULT_LANGUAGE } from './languages'

const KEY = 'omi-windows-prefs-v1'

export type Preferences = {
  captionIntervalMs: number
  showRecordingBadge: boolean
  reduceMotion: boolean
  // Set during the startup wizard.
  displayName?: string
  language: string
  // Chat conversation grouping. 'per-launch' = a new conversation each app run
  // (default, original behavior); 'infinite' = one ongoing conversation shared
  // by the main window and the overlay.
  chatHistoryMode: 'per-launch' | 'infinite'
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
}

const defaults: Preferences = {
  captionIntervalMs: 2000,
  showRecordingBadge: true,
  reduceMotion: false,
  language: DEFAULT_LANGUAGE,
  // Infinite by default: one ongoing conversation that persists across launches
  // and is accessible from the beginning (the Home thread windows it in as you
  // scroll up). Users can switch back to 'per-launch' in Settings.
  chatHistoryMode: 'infinite'
}

function load(): Preferences {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return { ...defaults }
    const parsed = JSON.parse(raw) as Partial<Preferences>
    return { ...defaults, ...parsed }
  } catch {
    return { ...defaults }
  }
}

let current: Preferences = load()
const listeners = new Set<(p: Preferences) => void>()

export function getPreferences(): Preferences {
  return current
}

export function setPreferences(patch: Partial<Preferences>): void {
  current = { ...current, ...patch }
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
  setPreferences({ onboardingCompletedAt: Date.now() })
}

// Clear the completion flag so the startup wizard runs again. Keeps the rest of
// the saved preferences (name, language, consent). Subscribers are notified, so
// App's reactive onboarding gate re-routes to the wizard immediately.
export function resetOnboarding(): void {
  const next = { ...current }
  delete next.onboardingCompletedAt
  current = next
  try {
    localStorage.setItem(KEY, JSON.stringify(current))
  } catch {
    /* quota / privacy mode */
  }
  listeners.forEach((cb) => cb(current))
}
