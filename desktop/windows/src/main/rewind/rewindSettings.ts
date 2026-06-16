import { app } from 'electron'
import { join } from 'path'
import { readFileSync, writeFileSync } from 'fs'
import type { RewindSettings } from '../../shared/types'

// Rewind capture is ON by default — screen history is a core feature, so a fresh
// install (no settings file yet) starts capturing. Once the user changes a
// setting it is persisted and these defaults no longer apply. excludedApps holds
// only USER additions; the built-in screenshot-tool exclusions live in
// shared/rewindExclusions and are merged in at capture time.
const DEFAULTS: RewindSettings = {
  captureEnabled: true,
  intervalMs: 1000,
  retentionDays: 14,
  excludedApps: []
}

function file(): string {
  return join(app.getPath('userData'), 'rewind-settings.json')
}

// Coerce a partial/untrusted settings object into a fully-valid one.
function sanitize(raw: Partial<RewindSettings>): RewindSettings {
  const intervalMs =
    typeof raw.intervalMs === 'number' && Number.isFinite(raw.intervalMs) && raw.intervalMs > 0
      ? raw.intervalMs
      : DEFAULTS.intervalMs
  const retentionDays =
    typeof raw.retentionDays === 'number' &&
    Number.isFinite(raw.retentionDays) &&
    raw.retentionDays >= 1
      ? Math.floor(raw.retentionDays)
      : DEFAULTS.retentionDays
  const excludedApps = Array.isArray(raw.excludedApps)
    ? raw.excludedApps
        .filter((s): s is string => typeof s === 'string')
        .map((s) => s.trim())
        .filter(Boolean)
    : []
  return {
    // Default ON: only an explicit `false` disables capture.
    captureEnabled: raw.captureEnabled !== false,
    intervalMs,
    retentionDays,
    excludedApps
  }
}

// Read the persisted settings, defaulting to capture-on. Never throws — a
// missing/corrupt file yields the defaults.
export function getPersistedRewindSettings(): RewindSettings {
  try {
    return sanitize(JSON.parse(readFileSync(file(), 'utf-8')) as Partial<RewindSettings>)
  } catch {
    return { ...DEFAULTS }
  }
}

export function persistRewindSettings(next: RewindSettings): RewindSettings {
  const value = sanitize(next)
  try {
    writeFileSync(file(), JSON.stringify(value), 'utf-8')
  } catch (e) {
    console.warn('[rewind] failed to persist settings:', e)
  }
  return value
}
