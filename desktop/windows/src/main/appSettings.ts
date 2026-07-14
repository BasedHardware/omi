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
  /** Electron accelerator that toggles mic recording. */
  recordHotkey: string
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
   *  user" doc auto-generates in the background. Default OFF for now: nothing
   *  consumes the profile yet (the Focus assistant's context block is the
   *  consumer and lands in the next PR) and there is no Settings toggle yet, so
   *  a default-on daily two-stage LLM call that uploads a synthesized personal
   *  dossier would cost the user with no benefit and no off-switch. The PR that
   *  adds the consumer flips this default on. */
  aiProfileEnabled: boolean
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
    recordHotkey: hotkey,
    summonHotkey: summon,
    hudContentProtection: r.hudContentProtection !== false,
    meeting: sanitizeMeeting(r.meeting),
    lastShownChangelogVersion:
      typeof r.lastShownChangelogVersion === 'string' ? r.lastShownChangelogVersion : null,
    // Opt-IN (=== true), unlike the other flags' opt-out (!== false) — see the
    // AppSettings field comment.
    aiProfileEnabled: r.aiProfileEnabled === true
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
  return next
}

/** Test-only: drop the in-memory cache so the next read comes from disk. */
export function _resetForTests(): void {
  cache = null
}
