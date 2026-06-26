import { app } from 'electron'
import { readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import type { FloatingBarSettings, RealtimeVoiceProvider } from '../../shared/types'

const DEFAULT_SUMMON_SHORTCUT = 'Shift+Space'
const PROVIDERS: RealtimeVoiceProvider[] = [
  'omi-relay',
  'openai-byok',
  'local-kokoro',
  'elevenlabs'
]

const DEFAULTS: FloatingBarSettings = {
  enabled: true,
  summonOnShortcut: true,
  summonShortcut: DEFAULT_SUMMON_SHORTCUT,
  alwaysOnTop: true,
  voiceAnswersEnabled: false,
  realtimeVoiceEnabled: false,
  realtimeVoiceProvider: 'omi-relay',
  summonCount: 0,
  askCount: 0,
  voiceCaptureCount: 0,
  lastSummonedAt: null,
  lastOpenedAt: null,
  lastAskedAt: null,
  lastVoiceCapturedAt: null
}

function file(): string {
  return join(app.getPath('userData'), 'floating-bar-settings.json')
}

function bool(raw: unknown, fallback: boolean): boolean {
  return typeof raw === 'boolean' ? raw : fallback
}

function count(raw: unknown): number {
  return typeof raw === 'number' && Number.isFinite(raw) && raw >= 0 ? Math.floor(raw) : 0
}

function timestamp(raw: unknown): number | null {
  return typeof raw === 'number' && Number.isFinite(raw) && raw > 0 ? raw : null
}

function shortcut(raw: unknown): string {
  return typeof raw === 'string' && raw.trim() ? raw.trim() : DEFAULT_SUMMON_SHORTCUT
}

function provider(raw: unknown): RealtimeVoiceProvider {
  return PROVIDERS.includes(raw as RealtimeVoiceProvider)
    ? (raw as RealtimeVoiceProvider)
    : DEFAULTS.realtimeVoiceProvider
}

function sanitize(raw: Partial<FloatingBarSettings>): FloatingBarSettings {
  return {
    enabled: bool(raw.enabled, DEFAULTS.enabled),
    summonOnShortcut: bool(raw.summonOnShortcut, DEFAULTS.summonOnShortcut),
    summonShortcut: shortcut(raw.summonShortcut),
    alwaysOnTop: bool(raw.alwaysOnTop, DEFAULTS.alwaysOnTop),
    voiceAnswersEnabled: bool(raw.voiceAnswersEnabled, DEFAULTS.voiceAnswersEnabled),
    realtimeVoiceEnabled: bool(raw.realtimeVoiceEnabled, DEFAULTS.realtimeVoiceEnabled),
    realtimeVoiceProvider: provider(raw.realtimeVoiceProvider),
    summonCount: count(raw.summonCount),
    askCount: count(raw.askCount),
    voiceCaptureCount: count(raw.voiceCaptureCount),
    lastSummonedAt: timestamp(raw.lastSummonedAt),
    lastOpenedAt: timestamp(raw.lastOpenedAt),
    lastAskedAt: timestamp(raw.lastAskedAt),
    lastVoiceCapturedAt: timestamp(raw.lastVoiceCapturedAt)
  }
}

export function getFloatingBarSettings(): FloatingBarSettings {
  try {
    return sanitize(JSON.parse(readFileSync(file(), 'utf-8')) as Partial<FloatingBarSettings>)
  } catch {
    return { ...DEFAULTS }
  }
}

export function setFloatingBarSettings(next: FloatingBarSettings): FloatingBarSettings {
  const value = sanitize(next)
  try {
    writeFileSync(file(), JSON.stringify(value), 'utf-8')
  } catch (e) {
    console.warn('[floating-bar] failed to persist settings:', e)
  }
  return value
}

export function updateFloatingBarSettings(
  patch: Partial<FloatingBarSettings>
): FloatingBarSettings {
  return setFloatingBarSettings({ ...getFloatingBarSettings(), ...patch })
}

export function recordFloatingBarSummon(): FloatingBarSettings {
  const current = getFloatingBarSettings()
  return setFloatingBarSettings({
    ...current,
    summonCount: current.summonCount + 1,
    lastSummonedAt: Date.now()
  })
}

export function recordFloatingBarOpened(): FloatingBarSettings {
  return updateFloatingBarSettings({ lastOpenedAt: Date.now() })
}

export function recordFloatingBarAsked(): FloatingBarSettings {
  const current = getFloatingBarSettings()
  return setFloatingBarSettings({
    ...current,
    askCount: current.askCount + 1,
    lastAskedAt: Date.now()
  })
}

export function recordFloatingBarVoiceCaptured(): FloatingBarSettings {
  const current = getFloatingBarSettings()
  return setFloatingBarSettings({
    ...current,
    voiceCaptureCount: current.voiceCaptureCount + 1,
    lastVoiceCapturedAt: Date.now()
  })
}
