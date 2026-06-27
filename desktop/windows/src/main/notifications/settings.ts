import { app } from 'electron'
import { readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import { getInsightSettings, updateInsightSettings } from '../insight/state'
import type {
  InsightNotificationStyle,
  InsightSettings,
  WindowsDailySummaryNotificationSettings,
  WindowsInsightNotificationSettings,
  WindowsNotificationCategorySettings,
  WindowsNotificationSettings,
  WindowsNotificationSettingsPatch
} from '../../shared/types'

type PersistedWindowsNotificationSettings = {
  nativeEnabled: boolean
  focus: WindowsNotificationCategorySettings
  tasks: WindowsNotificationCategorySettings
  memories: WindowsNotificationCategorySettings
  dailySummary: WindowsDailySummaryNotificationSettings
}

const INSIGHT_INTERVALS = [15, 20, 30, 60]

const DEFAULTS: PersistedWindowsNotificationSettings = {
  nativeEnabled: true,
  focus: { enabled: true },
  tasks: { enabled: false },
  memories: { enabled: false },
  dailySummary: { enabled: true, hour: 22 }
}

function file(): string {
  return join(app.getPath('userData'), 'notification-settings.json')
}

function enabledOrDefault(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback
}

function sanitizeCategory(
  raw: unknown,
  fallback: WindowsNotificationCategorySettings
): WindowsNotificationCategorySettings {
  const obj =
    raw && typeof raw === 'object' ? (raw as Partial<WindowsNotificationCategorySettings>) : {}
  return { enabled: enabledOrDefault(obj.enabled, fallback.enabled) }
}

function normalizeHour(value: unknown): number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 23
    ? value
    : DEFAULTS.dailySummary.hour
}

function sanitizeDailySummary(raw: unknown): WindowsDailySummaryNotificationSettings {
  const obj =
    raw && typeof raw === 'object' ? (raw as Partial<WindowsDailySummaryNotificationSettings>) : {}
  return {
    enabled: enabledOrDefault(obj.enabled, DEFAULTS.dailySummary.enabled),
    hour: normalizeHour(obj.hour)
  }
}

export function sanitizeStoredWindowsNotificationSettings(
  raw: unknown
): PersistedWindowsNotificationSettings {
  const obj =
    raw && typeof raw === 'object' ? (raw as Partial<PersistedWindowsNotificationSettings>) : {}
  return {
    nativeEnabled: enabledOrDefault(obj.nativeEnabled, DEFAULTS.nativeEnabled),
    focus: sanitizeCategory(obj.focus, DEFAULTS.focus),
    tasks: sanitizeCategory(obj.tasks, DEFAULTS.tasks),
    memories: sanitizeCategory(obj.memories, DEFAULTS.memories),
    dailySummary: sanitizeDailySummary(obj.dailySummary)
  }
}

function getPersistedWindowsNotificationSettings(): PersistedWindowsNotificationSettings {
  try {
    return sanitizeStoredWindowsNotificationSettings(JSON.parse(readFileSync(file(), 'utf-8')))
  } catch {
    return { ...DEFAULTS, dailySummary: { ...DEFAULTS.dailySummary } }
  }
}

function persistWindowsNotificationSettings(
  next: PersistedWindowsNotificationSettings
): PersistedWindowsNotificationSettings {
  const value = sanitizeStoredWindowsNotificationSettings(next)
  try {
    writeFileSync(file(), JSON.stringify(value, null, 2), 'utf-8')
  } catch (e) {
    console.warn('[notifications] failed to persist settings:', e)
  }
  return value
}

function normalizeIntervalMin(value: unknown): number {
  return typeof value === 'number' && INSIGHT_INTERVALS.includes(value) ? value : 15
}

function normalizeDenylist(value: unknown): string[] {
  return Array.isArray(value)
    ? value
        .filter((s): s is string => typeof s === 'string')
        .map((s) => s.trim())
        .filter(Boolean)
    : []
}

function normalizeNotificationStyle(value: unknown): InsightNotificationStyle {
  return value === 'native' ? 'native' : 'omi'
}

function snapshotInsightSettings(insight: InsightSettings): WindowsInsightNotificationSettings {
  return {
    enabled: insight.enabled !== false,
    intervalMin: normalizeIntervalMin(insight.intervalMin),
    notificationStyle: normalizeNotificationStyle(insight.notificationStyle),
    denylist: normalizeDenylist(insight.denylist),
    lastRunAt: typeof insight.lastRunAt === 'number' ? insight.lastRunAt : null
  }
}

function toInsightPatch(
  patch: Partial<WindowsInsightNotificationSettings>
): Partial<InsightSettings> {
  const next: Partial<InsightSettings> = {}
  if (typeof patch.enabled === 'boolean') next.enabled = patch.enabled
  if (patch.intervalMin !== undefined) next.intervalMin = normalizeIntervalMin(patch.intervalMin)
  if (patch.notificationStyle !== undefined) {
    next.notificationStyle = normalizeNotificationStyle(patch.notificationStyle)
  }
  if (patch.denylist !== undefined) next.denylist = normalizeDenylist(patch.denylist)
  if (patch.lastRunAt === null || typeof patch.lastRunAt === 'number')
    next.lastRunAt = patch.lastRunAt
  return next
}

export function getWindowsNotificationSettings(): WindowsNotificationSettings {
  const persisted = getPersistedWindowsNotificationSettings()
  return {
    ...persisted,
    insights: snapshotInsightSettings(getInsightSettings())
  }
}

export function updateWindowsNotificationSettings(
  patch: WindowsNotificationSettingsPatch
): WindowsNotificationSettings {
  const current = getPersistedWindowsNotificationSettings()
  const next = persistWindowsNotificationSettings({
    nativeEnabled: enabledOrDefault(patch.nativeEnabled, current.nativeEnabled),
    focus: sanitizeCategory({ ...current.focus, ...(patch.focus ?? {}) }, current.focus),
    tasks: sanitizeCategory({ ...current.tasks, ...(patch.tasks ?? {}) }, current.tasks),
    memories: sanitizeCategory(
      { ...current.memories, ...(patch.memories ?? {}) },
      current.memories
    ),
    dailySummary: sanitizeDailySummary({
      ...current.dailySummary,
      ...(patch.dailySummary ?? {})
    })
  })

  if (patch.insights) updateInsightSettings(toInsightPatch(patch.insights))
  return {
    ...next,
    insights: snapshotInsightSettings(getInsightSettings())
  }
}
