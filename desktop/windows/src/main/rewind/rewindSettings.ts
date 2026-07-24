import { app } from 'electron'
import { join } from 'path'
import { readFileSync, writeFileSync } from 'fs'
import type { RewindSettings } from '../../shared/types'

// Rewind capture is OFF by default. A fresh install must receive explicit user
// consent before screenshots can be persisted. Once the user changes a
// setting it is persisted and these defaults no longer apply. excludedApps holds
// only USER additions; the built-in screenshot-tool exclusions live in
// shared/rewindExclusions and are merged in at capture time.
const DEFAULTS: RewindSettings = {
  captureEnabled: false,
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
    // Privacy boundary: only an explicit `true` enables capture.
    captureEnabled: raw.captureEnabled === true,
    intervalMs,
    retentionDays,
    excludedApps
  }
}

// Read the persisted settings, defaulting to capture-off. Never throws — a
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
