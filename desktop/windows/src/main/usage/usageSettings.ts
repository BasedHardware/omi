import { app } from 'electron'
import { join } from 'path'
import { readFileSync, writeFileSync } from 'fs'
import type { UsageSettings } from '../../shared/types'
import { DEFAULT_RETENTION_DAYS, normalizeRetentionDays } from './usageRetention'

const DEFAULTS: UsageSettings = { enabled: true, retentionDays: DEFAULT_RETENTION_DAYS }

function file(): string {
  return join(app.getPath('userData'), 'usage-settings.json')
}

// Coerce a partial/untrusted settings object into a fully-valid one.
function sanitize(raw: Partial<UsageSettings>): UsageSettings {
  return {
    enabled: raw.enabled !== false,
    retentionDays: normalizeRetentionDays(raw.retentionDays)
  }
}

// Read the persisted settings, defaulting to enabled with the default retention.
// Never throws — a missing/corrupt file yields the defaults.
export function getUsageSettings(): UsageSettings {
  try {
    return sanitize(JSON.parse(readFileSync(file(), 'utf-8')) as Partial<UsageSettings>)
  } catch {
    return { ...DEFAULTS }
  }
}

export function setUsageSettings(next: UsageSettings): UsageSettings {
  const value = sanitize(next)
  try {
    writeFileSync(file(), JSON.stringify(value), 'utf-8')
  } catch (e) {
    console.warn('[usage] failed to persist settings:', e)
  }
  return value
}
