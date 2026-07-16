// Small main-process settings store (JSON in userData), following the pattern of
// usage/usageSettings.ts. Holds lifecycle-related flags that must survive
// restarts: whether the one-time close-to-tray notice was shown, and the
// (rebindable) mic record chord.
import { app } from 'electron'
import { join } from 'path'
import { readFileSync, writeFileSync } from 'fs'
import { DEFAULT_RECORD_HOTKEY } from './shortcuts'
import { OVERLAY_ACCELERATOR } from './overlay/shortcut'
import type { MeetingMode, MeetingSettings } from '../shared/types'

export type AppSettings = {
  /** Whether the one-time "Omi keeps running in the tray" notice has been shown. */
  closeToTrayNoticeShown: boolean
  /** Whether the one-time "a global shortcut couldn't be registered" notice has
   *  been shown. Set only after the notice actually fires on a real conflict, so
   *  a user who first sees a conflict months later is still told once. */
  hotkeyConflictNoticeShown: boolean
  /** Electron accelerator that toggles mic recording. */
  recordHotkey: string
  /** Whether the mic record chord is registered at all. Default true; the user
   *  can turn it fully off (Settings → Shortcuts) because the default Ctrl+Space
   *  collides with the Windows IME language-switch. When false, main leaves the
   *  chord unregistered so the OS never claims it. */
  recordHotkeyEnabled: boolean
  /** Electron accelerator that summons the floating bar. Persisted so a rebind
   *  survives restarts and main can register it at launch (a taken chord then
   *  fails loudly in Settings instead of only a console.warn). Kept in step with
   *  the legacy renderer `overlayShortcut` preference by the Settings rebind. */
  summonHotkey: string
  /** Exclude the bar/HUD from screen capture (WDA_EXCLUDEFROMCAPTURE). User
   *  toggle, default on — consistent with the old overlay's behavior. */
  hudContentProtection: boolean
  /** Meeting-detection behavior (Phase 5). */
  meeting: MeetingSettings
  /** App version whose "what's new" changelog was last shown post-update. null =
   *  never shown (fresh install / pre-feature) → baseline silently, no toast. */
  lastShownChangelogVersion: string | null
  /** Track 3 (AI user profile): whether the once-daily synthesized "about the
   *  user" doc auto-generates in the background. Default ON: the Focus assistant
   *  is now the consumer — the profile grounds Focus's context block, so the
   *  daily two-stage LLM call has a concrete payoff (a focus coach that knows who
   *  the user is). Was default OFF while it had no consumer. */
  aiProfileEnabled: boolean
  /** Track 3 (Focus assistant): whether Focus judges the screen at all. Default
   *  ON, mirroring Mac's `focusAssistantEnabled`. Gated further by
   *  `focusNotificationsEnabled` — see the AND-gate in focusAssistant.isEnabled. */
  focusEnabled: boolean
  /** Track 3 (Focus): Mac's `focusNotificationsEnabled`. Default ON. This is NOT
   *  the frequency throttle — it is Mac's second half of the master gate: with it
   *  off, Focus makes NO Gemini call at all ("no notification setting, no
   *  analysis"), not merely a silent verdict. Separate from
   *  `notificationFrequency` (0=Off), so out of the box Focus judges + glows but
   *  never toasts until the user raises the frequency. */
  focusNotificationsEnabled: boolean
  /** Track 3 (Focus): minutes of analysis cooldown after a distraction verdict,
   *  Mac's `focusCooldownInterval`. Default 10. A context switch bypasses it. */
  focusCooldownMinutes: number
  /** Track 3 (Focus): apps the user never wants Focus to look at, on top of the
   *  capture-time and privacy exclusions. Mac's `focusExcludedApps`. Default []. */
  focusExcludedApps: string[]
  /** Track 3 (focus halo): whether the Focus assistant may draw its glowing ring
   *  around the active window (red when it judges the user distracted, green when
   *  they refocus). Default ON — it only ever appears in response to a Focus
   *  verdict, which is itself gated, and it is click-through, so it costs nothing
   *  when Focus is idle. Mirrors Mac's `assistantsGlowOverlayEnabled`. */
  glowOverlayEnabled: boolean
  /** Track 3 (proactive framework): master switch for the whole screen-analysis
   *  loop. Default ON, mirroring Mac's `screenAnalysisEnabled`. It is not a
   *  per-frame gate — when off, the coordinator's tick timer does not run at all,
   *  so no frame is ever read. */
  screenAnalysisEnabled: boolean
  /** Track 3: master switch for proactive notifications, mirroring Mac's
   *  `notifications_enabled`. Default ON. Separate from `notificationFrequency`
   *  because a functional notification may bypass this gate
   *  (`respectFrequency: false`) while never bypassing snooze. */
  notificationsEnabled: boolean
  /** Track 3: how often a proactive assistant may interrupt, 0–5 →
   *  [off, 60m, 30m, 10m, 3m, no throttle]. Default 0 = Off: assistants that
   *  reach the throttle stay silent until the user opts in, which is Mac's
   *  post-migration default (`NotificationService.defaultFrequencyLevel`). */
  notificationFrequency: number
  /** Track 3 (Memory assistant): whether the interval-based memory extractor
   *  judges the screen at all. Default OFF — the screen-memory scraper is opt-in,
   *  matching Mac's net behavior (Mac gates it behind `notificationsEnabled`, which
   *  defaults off). Conversation-derived memories populate the store regardless;
   *  this is the supplementary on-screen source. It is the SOLE gate for the Memory
   *  assistant (see memoryAssistant.isEnabled) — decoupled from notifications, since
   *  memory writes durable facts whether or not a toast ever fires. The master
   *  "may I send screenshots to Gemini" lever remains `screenAnalysisEnabled`. */
  memoryEnabled: boolean
  /** Track 3 (Memory): minutes between extraction attempts, Mac's
   *  `memoryExtractionInterval` (600s = 10 min). Default 10. */
  memoryExtractionIntervalMin: number
  /** Track 3 (Memory): minimum confidence an extracted memory must clear to be
   *  kept, Mac's `memoryMinConfidence`. Default 0.7. */
  memoryMinConfidence: number
  /** Track 3 (Memory): apps the user never wants the memory extractor to look at,
   *  on top of the capture-time and privacy exclusions. Mac's
   *  `memoryExcludedApps`. Default []. */
  memoryExcludedApps: string[]
  /** Track 3 (Task assistant): whether the screen→task extractor judges the
   *  screen at all. Default ON, matching Mac's `taskAssistantEnabled`. It sits
   *  UNDER the `screenAnalysisEnabled` master (the actual "may I send screenshots
   *  to Gemini" consent, itself default-ON and shared with Focus/Insight), so a
   *  default-ON here adds tasks to the already-consented screen-analysis feature
   *  rather than opening a new cloud-vision surface. It is the SOLE task-specific
   *  gate (see taskAssistant.isEnabled) — decoupled from notifications, since
   *  extraction stages durable tasks whether or not a toast ever fires (Mac keeps
   *  a separate `taskNotificationsEnabled`; quiet discovery is never gated on the
   *  notification setting). */
  taskEnabled: boolean
  /** Track 3 (Task): apps the user never wants the task extractor to look at, on
   *  top of the capture-time and privacy exclusions. Mirrors `memoryExcludedApps`.
   *  Default []. */
  taskExcludedApps: string[]
  /** Track 3 (Task): minutes between fallback extraction attempts, Mac's
   *  `extractionInterval` (600s = 10 min). Default 10. */
  taskFallbackIntervalMin: number
  /** Track 3 (Task): minimum confidence an extracted task must clear to be
   *  staged, Mac's `minConfidence`. Default 0.75. */
  taskMinConfidence: number
  /** Which engine renders default typed chat. `'legacy_sse'` = today's
   *  `fetch('/v2/messages')` path; `'pi_mono'` = the kernel main_chat → pi-mono
   *  adapter path (PR-E). Default `'legacy_sse'` until pi-mono is proven end to
   *  end. INERT in PR-D1: no consumer reads it yet — PR-E's main_chat routing
   *  does. */
  chatEngine: 'legacy_sse' | 'pi_mono'
  /** "Screen Sharing in Chat" (Mac's `chatScreenshotSharingEnabled`). Default ON.
   *  The consent gate for the model-invoked `capture_screen` tool: when on, the
   *  chat model MAY capture the screen if it calls the tool; when off, the tool is
   *  refused at dispatch (see captureScreenExecutor.ts). It does NOT itself cause
   *  any capture — it only makes the (currently DARK) tool available. Mirrors Mac's
   *  ChatToolExecutor gate; only its Settings location differs (Windows: Privacy). */
  chatScreenshotSharingEnabled: boolean
  /** Track 3 (Goals, Wave C): whether the on-device goal generator runs on a
   *  periodic timer. Default OFF, mirroring Mac's `goalGenerationEnabled`. Gated
   *  further at runtime by [<3 active goals] + [once per calendar day]. The manual
   *  "Suggest" button (goals:generateNow) bypasses those two gates — it never reads
   *  this flag. */
  goalAutoGenerationEnabled: boolean
  /** Track 3 (Goals): calendar date (`YYYY-MM-DD`, local) of the last successful
   *  auto-generation, so the timer runs at most once per day. null = never. */
  goalGenerationLastDate: string | null
  /** Track 3 (Goals): the goal IDs THIS app auto-generated, with their create
   *  time. The stale-cleanup attribution set — the backend does not persist/return
   *  a `source` field, so a self-generated goal can only be identified from this
   *  local record. Cleanup deletes ONLY from this set (never a user-created goal);
   *  IDs are pruned as their goals are deleted. Bounded to cap file growth. */
  goalAutoGeneratedIds: GoalAutoGeneratedRecord[]
}

/** One auto-generated goal's local attribution record (see `goalAutoGeneratedIds`). */
export type GoalAutoGeneratedRecord = {
  /** The backend goal id returned by POST /v1/goals. */
  id: string
  /** Epoch ms the goal was created (fallback age source for staleness). */
  createdAt: number
}

const MEETING_MODES: MeetingMode[] = ['off', 'ask', 'auto']

// Default 'ask': detection runs but never auto-starts capture silently — the
// first detected meeting asks via toast, and the toast carries a one-time
// first-run hint pointing at Settings.
function sanitizeMeeting(raw: Partial<MeetingSettings> | null | undefined): MeetingSettings {
  const r = raw ?? {}
  const mode = MEETING_MODES.includes(r.mode as MeetingMode) ? (r.mode as MeetingMode) : 'ask'
  const grace =
    typeof r.endGraceMinutes === 'number' && Number.isFinite(r.endGraceMinutes)
      ? Math.min(30, Math.max(1, Math.round(r.endGraceMinutes)))
      : 2
  // Bound the map: per-app overrides are keyed by pattern id (a handful of known
  // apps). Cap the count so a malformed/hostile patch can't bloat the settings
  // file. Keys longer than a reasonable pattern id are also dropped.
  const perApp: Record<string, MeetingMode> = {}
  if (r.perApp && typeof r.perApp === 'object') {
    for (const [k, v] of Object.entries(r.perApp)) {
      if (Object.keys(perApp).length >= 64) break
      if (typeof k === 'string' && k.length <= 64 && MEETING_MODES.includes(v as MeetingMode))
        perApp[k] = v as MeetingMode
    }
  }
  return { mode, endGraceMinutes: grace, perApp, firstRunToastShown: r.firstRunToastShown === true }
}

// Anything that is not a valid level reads as 0 = Off — NOT as the nearest level.
// Clamping (Mac's behavior) would map a corrupt file or a backend settings-sync
// sending `notification_frequency: 10` onto level 5, which is "no throttle": a
// user whose default was Off would start getting unthrottled proactive toasts.
// Junk must always fail quiet, never loud.
function sanitizeFrequency(raw: unknown): number {
  if (typeof raw !== 'number' || !Number.isInteger(raw) || raw < 0 || raw > 5) return 0
  return raw
}

// Cooldown minutes: a positive integer, else Mac's default 10. Zero/negative/
// junk falls back rather than disabling the cooldown (which would let a
// distracted user be re-billed for a Gemini call every few seconds).
function sanitizeCooldownMinutes(raw: unknown): number {
  if (typeof raw !== 'number' || !Number.isInteger(raw) || raw <= 0) return 10
  return Math.min(raw, 24 * 60) // a day is already absurd; cap the blast radius.
}

// Excluded apps: a bounded array of non-empty strings. Cap the count and length
// so a malformed/hostile settings file can't bloat memory or a query.
function sanitizeExcludedApps(raw: unknown): string[] {
  if (!Array.isArray(raw)) return []
  const out: string[] = []
  for (const v of raw) {
    if (out.length >= 256) break
    if (typeof v === 'string' && v.trim() && v.length <= 256) out.push(v.trim())
  }
  return out
}

// Auto-generated goal IDs: a bounded array of {id: non-empty string, createdAt:
// finite number}. Cap the count so the attribution record can't grow without
// bound. A junk entry is dropped rather than kept — a bad record must never let
// cleanup match (and delete) the wrong goal, so only well-formed entries survive.
function sanitizeGoalAutoGeneratedIds(raw: unknown): GoalAutoGeneratedRecord[] {
  if (!Array.isArray(raw)) return []
  const out: GoalAutoGeneratedRecord[] = []
  for (const v of raw) {
    if (out.length >= 256) break
    const r = v as Partial<GoalAutoGeneratedRecord> | null
    const id = typeof r?.id === 'string' ? r.id.trim() : ''
    const createdAt =
      typeof r?.createdAt === 'number' && Number.isFinite(r.createdAt) ? r.createdAt : NaN
    if (id && id.length <= 128 && Number.isFinite(createdAt)) out.push({ id, createdAt })
  }
  return out
}

// Min confidence: a number in [0, 1], else the caller's default (Memory 0.7,
// Task 0.75). Junk/out-of-range clamps rather than disabling the gate (a 0 floor
// would keep every low-quality item the model emits; a >1 floor would keep none).
function sanitizeMinConfidence(raw: unknown, fallback = 0.7): number {
  if (typeof raw !== 'number' || !Number.isFinite(raw)) return fallback
  return Math.min(1, Math.max(0, raw))
}

// Coerce a partial/untrusted object into fully-valid settings. Passing null/
// undefined yields the defaults, so defaults live in exactly one place.
export function sanitizeAppSettings(raw: Partial<AppSettings> | null | undefined): AppSettings {
  const r = raw ?? {}
  const hotkey =
    typeof r.recordHotkey === 'string' && r.recordHotkey.trim()
      ? r.recordHotkey.trim()
      : DEFAULT_RECORD_HOTKEY
  const summon =
    typeof r.summonHotkey === 'string' && r.summonHotkey.trim()
      ? r.summonHotkey.trim()
      : OVERLAY_ACCELERATOR
  return {
    closeToTrayNoticeShown: r.closeToTrayNoticeShown === true,
    hotkeyConflictNoticeShown: r.hotkeyConflictNoticeShown === true,
    recordHotkey: hotkey,
    // Default ON: only an explicit false turns the record chord off (matches the
    // hudContentProtection convention above — non-boolean coerces to the default).
    recordHotkeyEnabled: r.recordHotkeyEnabled !== false,
    summonHotkey: summon,
    hudContentProtection: r.hudContentProtection !== false,
    meeting: sanitizeMeeting(r.meeting),
    lastShownChangelogVersion:
      typeof r.lastShownChangelogVersion === 'string' ? r.lastShownChangelogVersion : null,
    // Opt-OUT (!== false): default ON now that Focus consumes the profile.
    aiProfileEnabled: r.aiProfileEnabled !== false,
    focusEnabled: r.focusEnabled !== false,
    focusNotificationsEnabled: r.focusNotificationsEnabled !== false,
    focusCooldownMinutes: sanitizeCooldownMinutes(r.focusCooldownMinutes),
    focusExcludedApps: sanitizeExcludedApps(r.focusExcludedApps),
    glowOverlayEnabled: r.glowOverlayEnabled !== false,
    screenAnalysisEnabled: r.screenAnalysisEnabled !== false,
    notificationsEnabled: r.notificationsEnabled !== false,
    notificationFrequency: sanitizeFrequency(r.notificationFrequency),
    memoryEnabled: r.memoryEnabled === true,
    // Reuses the cooldown sanitizer: same contract (positive integer minutes,
    // default 10, capped at a day). A junk interval falls back to 10, never 0.
    memoryExtractionIntervalMin: sanitizeCooldownMinutes(r.memoryExtractionIntervalMin),
    memoryMinConfidence: sanitizeMinConfidence(r.memoryMinConfidence),
    memoryExcludedApps: sanitizeExcludedApps(r.memoryExcludedApps),
    // Default ON (!== false, same idiom as screenAnalysisEnabled), matching Mac's
    // `taskAssistantEnabled`. The screenAnalysisEnabled master is the screenshot
    // consent gate; this only decides whether tasks ride that already-on feature.
    taskEnabled: r.taskEnabled !== false,
    // Reuses the cooldown sanitizer: same contract (positive integer minutes,
    // default 10, capped at a day). A junk interval falls back to 10, never 0.
    taskFallbackIntervalMin: sanitizeCooldownMinutes(r.taskFallbackIntervalMin),
    // Task's floor is 0.75 (vs Memory's 0.7) — pass it as the junk/absent fallback.
    taskMinConfidence: sanitizeMinConfidence(r.taskMinConfidence, 0.75),
    taskExcludedApps: sanitizeExcludedApps(r.taskExcludedApps),
    // Only the explicit 'pi_mono' opt-in flips this; anything else (junk, unset)
    // is the safe legacy path.
    chatEngine: r.chatEngine === 'pi_mono' ? 'pi_mono' : 'legacy_sse',
    // Default ON (opt-out): only an explicit false turns Screen Sharing in Chat
    // off. Matches Mac's absent-key-means-enabled default.
    chatScreenshotSharingEnabled: r.chatScreenshotSharingEnabled !== false,
    // Default OFF (opt-IN, === true): goal auto-generation only runs once the user
    // turns it on. Mirrors Mac's `goalGenerationEnabled` default.
    goalAutoGenerationEnabled: r.goalAutoGenerationEnabled === true,
    goalGenerationLastDate:
      typeof r.goalGenerationLastDate === 'string' ? r.goalGenerationLastDate : null,
    goalAutoGeneratedIds: sanitizeGoalAutoGeneratedIds(r.goalAutoGeneratedIds)
  }
}

function file(): string {
  return join(app.getPath('userData'), 'app-settings.json')
}

// Read + sanitize the on-disk settings. Never throws — a missing/corrupt file
// yields defaults.
function readFromDisk(): AppSettings {
  try {
    return sanitizeAppSettings(JSON.parse(readFileSync(file(), 'utf-8')) as Partial<AppSettings>)
  } catch {
    return sanitizeAppSettings(null)
  }
}

// The file is read at most once per process; every getAppSettings after that is
// served from memory, and setAppSettings keeps the cache in lock-step with disk.
let cache: AppSettings | null = null

// Read persisted settings (cached after the first call).
export function getAppSettings(): AppSettings {
  if (!cache) cache = readFromDisk()
  return cache
}

// Subscribers notified after every write. This exists so a feature whose master
// toggle lives here can re-arm itself when the toggle flips (the proactive
// coordinator's loop, which otherwise could only ever be turned OFF at runtime —
// turning it back on would need an app restart). Listeners must not throw.
type SettingsListener = (settings: AppSettings) => void
const listeners = new Set<SettingsListener>()

/** Subscribe to settings writes. Returns an unsubscribe function. */
export function onAppSettingsChanged(listener: SettingsListener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

// Merge a patch over the current settings, update the cache, and persist. Returns
// the written value.
export function setAppSettings(patch: Partial<AppSettings>): AppSettings {
  const next = sanitizeAppSettings({ ...getAppSettings(), ...patch })
  cache = next
  try {
    writeFileSync(file(), JSON.stringify(next), 'utf-8')
  } catch (e) {
    console.warn('[app-settings] failed to persist:', e)
  }
  // A listener blowing up must not lose the caller its write.
  for (const l of listeners) {
    try {
      l(next)
    } catch (e) {
      console.warn('[app-settings] listener failed:', e)
    }
  }
  return next
}

/** Test-only: drop the in-memory cache so the next read comes from disk. */
export function _resetForTests(): void {
  cache = null
  listeners.clear()
}
