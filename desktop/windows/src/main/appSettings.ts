// Small main-process settings store (JSON in userData), following the pattern of
// usage/usageSettings.ts. Holds lifecycle-related flags that must survive
// restarts: whether the one-time close-to-tray notice was shown, and the
// (rebindable) mic record chord.
import { app } from 'electron'
import { join } from 'path'
import { readFileSync, writeFileSync } from 'fs'
import { DEFAULT_RECORD_HOTKEY } from './shortcuts'

export type AppSettings = {
  /** Whether the one-time "Omi keeps running in the tray" notice has been shown. */
  closeToTrayNoticeShown: boolean
  /** Electron accelerator that toggles mic recording. */
  recordHotkey: string
}

const DEFAULTS: AppSettings = {
  closeToTrayNoticeShown: false,
  recordHotkey: DEFAULT_RECORD_HOTKEY
}

// Coerce a partial/untrusted object into fully-valid settings.
export function sanitizeAppSettings(raw: Partial<AppSettings> | null | undefined): AppSettings {
  const r = raw ?? {}
  const hotkey =
    typeof r.recordHotkey === 'string' && r.recordHotkey.trim()
      ? r.recordHotkey.trim()
      : DEFAULT_RECORD_HOTKEY
  return {
    closeToTrayNoticeShown: r.closeToTrayNoticeShown === true,
    recordHotkey: hotkey
  }
}

function file(): string {
  return join(app.getPath('userData'), 'app-settings.json')
}

// Read persisted settings. Never throws — a missing/corrupt file yields defaults.
export function getAppSettings(): AppSettings {
  try {
    return sanitizeAppSettings(JSON.parse(readFileSync(file(), 'utf-8')) as Partial<AppSettings>)
  } catch {
    return { ...DEFAULTS }
  }
}

// Merge a patch over the current settings and persist. Returns the written value.
export function setAppSettings(patch: Partial<AppSettings>): AppSettings {
  const next = sanitizeAppSettings({ ...getAppSettings(), ...patch })
  try {
    writeFileSync(file(), JSON.stringify(next), 'utf-8')
  } catch (e) {
    console.warn('[app-settings] failed to persist:', e)
  }
  return next
}
