import { useEffect, useMemo, useState } from 'react'
import { Activity, Keyboard, Layers, Mic, RefreshCw, RotateCcw, Volume2 } from 'lucide-react'
import type {
  ByokStatus,
  FloatingBarSettings,
  FloatingBarStatus,
  LocalTtsStatus
} from '../../../../../shared/types'
import { DEFAULT_OVERLAY_ACCELERATOR, acceleratorToTokens } from '../../../lib/overlayShortcut'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { realtimeVoiceReadiness, type RealtimeVoiceProvider } from '../../../lib/realtimeVoice'
import { toast } from '../../../lib/toast'
import { SettingRow } from '../SettingRow'
import { StatusTile } from '../StatusTile'
import { Toggle } from '../Toggle'

const FLOATING_BAR_TAB_SEARCH_KEYWORDS =
  'floating bar ask omi overlay shortcut summon always on top above everything voice answers realtime voice status usage'

function ShortcutKeycaps({ accelerator }: { accelerator: string }): React.JSX.Element {
  const tokens = acceleratorToTokens(accelerator || DEFAULT_OVERLAY_ACCELERATOR)
  return (
    <div className="flex flex-wrap gap-2">
      {tokens.map((token, index) => (
        <kbd
          key={`${token}-${index}`}
          className="flex h-9 min-w-9 items-center justify-center rounded-lg bg-white/[0.08] px-2.5 text-xs font-semibold text-white/85"
        >
          {token}
        </kbd>
      ))}
    </div>
  )
}

function formatTime(ts: number | null | undefined): string {
  if (!ts) return 'Never'
  return new Date(ts).toLocaleString()
}

function providerLabel(provider: RealtimeVoiceProvider): string {
  if (provider === 'openai-byok') return 'OpenAI BYOK'
  if (provider === 'local-kokoro') return 'Local Kokoro'
  if (provider === 'elevenlabs') return 'ElevenLabs'
  return 'Omi relay'
}

function localTtsRuntimeValue(status: LocalTtsStatus | null): string {
  const state = status?.runtime.installState
  if (!state) return 'Checking'
  if (state === 'installed' || state === 'running') return 'Ready'
  if (state === 'installing') return 'Installing'
  if (state === 'not_installed') return 'Installs on first reply'
  if (state === 'unsupported') return 'Unavailable'
  return 'Needs attention'
}

function withVoicePreferences(settings: FloatingBarSettings): FloatingBarSettings {
  const prefs = getPreferences()
  const realtimeVoiceEnabled = !!prefs.realtimeVoiceEnabled
  return {
    ...settings,
    voiceAnswersEnabled: realtimeVoiceEnabled,
    realtimeVoiceEnabled,
    realtimeVoiceProvider: prefs.realtimeVoiceProvider ?? settings.realtimeVoiceProvider
  }
}

function voiceFieldsDiffer(a: FloatingBarSettings, b: FloatingBarSettings): boolean {
  return (
    a.voiceAnswersEnabled !== b.voiceAnswersEnabled ||
    a.realtimeVoiceEnabled !== b.realtimeVoiceEnabled ||
    a.realtimeVoiceProvider !== b.realtimeVoiceProvider
  )
}

export function FloatingBarTab(): React.JSX.Element {
  const [settings, setSettings] = useState<FloatingBarSettings | null>(null)
  const [status, setStatus] = useState<FloatingBarStatus | null>(null)
  const [byokStatus, setByokStatus] = useState<ByokStatus | null>(null)
  const [localTtsStatus, setLocalTtsStatus] = useState<LocalTtsStatus | null>(null)
  const [refreshingStatus, setRefreshingStatus] = useState(false)
  const [voiceEnabled, setVoiceEnabled] = useState<boolean>(
    () => !!getPreferences().realtimeVoiceEnabled
  )
  const [voiceProvider, setVoiceProvider] = useState<RealtimeVoiceProvider>(
    () => getPreferences().realtimeVoiceProvider ?? 'omi-relay'
  )

  const loadSettings = async (): Promise<void> => {
    const saved = await window.omi.floatingBarGetSettings()
    const next = withVoicePreferences(saved)
    setSettings(next)
    if (voiceFieldsDiffer(saved, next)) {
      setSettings(await window.omi.floatingBarSetSettings(next))
    }
  }

  const refreshStatus = async (): Promise<void> => {
    setRefreshingStatus(true)
    try {
      const next = await window.omi.floatingBarStatus()
      setStatus(next)
      setSettings(withVoicePreferences(next.settings))
    } finally {
      setRefreshingStatus(false)
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadSettings()
      void refreshStatus()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [])

  useEffect(() => {
    return window.omi.onFloatingBarSettings((saved) => {
      setSettings(withVoicePreferences(saved))
    })
  }, [])

  useEffect(() => {
    let canceled = false
    window.omi
      .byokStatus()
      .then((next) => {
        if (!canceled) setByokStatus(next)
      })
      .catch(() => {
        if (!canceled) setByokStatus(null)
      })
    return () => {
      canceled = true
    }
  }, [])

  useEffect(() => {
    let canceled = false
    const refresh = (): void => {
      window.omi
        .localTtsStatus()
        .then((next) => {
          if (!canceled) setLocalTtsStatus(next)
        })
        .catch(() => {
          if (!canceled) setLocalTtsStatus(null)
        })
    }
    refresh()
    const timer = setInterval(refresh, 15000)
    return () => {
      canceled = true
      clearInterval(timer)
    }
  }, [])

  const patchSettings = async (patch: Partial<FloatingBarSettings>): Promise<void> => {
    if (!settings) return
    const next = { ...settings, ...patch }
    setSettings(next)
    try {
      const saved = await window.omi.floatingBarSetSettings(next)
      setSettings(withVoicePreferences(saved))
      await refreshStatus()
    } catch (e) {
      toast('Could not save floating bar settings', { tone: 'error', body: (e as Error).message })
      await loadSettings()
    }
  }

  const saveVoiceEnabled = (on: boolean): void => {
    setVoiceEnabled(on)
    setPreferences({ realtimeVoiceEnabled: on })
    void patchSettings({
      voiceAnswersEnabled: on,
      realtimeVoiceEnabled: on
    })
  }

  const saveVoiceProvider = (provider: RealtimeVoiceProvider): void => {
    setVoiceProvider(provider)
    setPreferences({ realtimeVoiceProvider: provider })
    void patchSettings({ realtimeVoiceProvider: provider })
  }

  const resetShortcut = async (): Promise<void> => {
    const ok = await window.omiOverlay?.setAccelerator(DEFAULT_OVERLAY_ACCELERATOR)
    if (!ok) {
      toast('Default floating bar shortcut is already in use', { tone: 'warn' })
      return
    }
    setPreferences({ overlayShortcut: DEFAULT_OVERLAY_ACCELERATOR })
    await loadSettings()
    await refreshStatus()
  }

  const voiceReadiness = useMemo(
    () =>
      realtimeVoiceReadiness(
        {
          ...getPreferences(),
          realtimeVoiceEnabled: voiceEnabled,
          realtimeVoiceProvider: voiceProvider
        },
        byokStatus,
        localTtsStatus
      ),
    [byokStatus, localTtsStatus, voiceEnabled, voiceProvider]
  )

  const enabled = !!settings?.enabled
  const summonOnShortcut = !!settings?.summonOnShortcut
  const shortcut =
    status?.currentShortcut ?? settings?.summonShortcut ?? DEFAULT_OVERLAY_ACCELERATOR
  const shortcutRegistered = status?.shortcutRegistered ?? false
  const windowState = !status?.windowCreated ? 'Not created' : status.open ? 'Open' : 'Hidden'

  return (
    <>
      <SettingRow
        icon={Layers}
        dot={enabled ? 'on' : 'off'}
        title="Show floating bar"
        subtitle="Keep the Ask Omi floating bar available after onboarding."
        keywords={`${FLOATING_BAR_TAB_SEARCH_KEYWORDS} enable disable show hide ask omi`}
        control={
          <Toggle
            on={enabled}
            onChange={(on) => void patchSettings({ enabled: on })}
            disabled={!settings}
            label="Show floating bar"
          />
        }
      />
      <SettingRow
        icon={Keyboard}
        dot={enabled && summonOnShortcut && shortcutRegistered ? 'on' : 'off'}
        title="Summon shortcut"
        subtitle={
          shortcutRegistered
            ? 'Global shortcut is registered.'
            : 'Shortcut is disabled or unavailable.'
        }
        keywords="floating bar ask omi shortcut summon hotkey keyboard global open overlay"
        control={
          <Toggle
            on={summonOnShortcut}
            onChange={(on) => void patchSettings({ summonOnShortcut: on })}
            disabled={!settings}
            label="Summon shortcut"
          />
        }
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <ShortcutKeycaps accelerator={shortcut} />
          <button
            type="button"
            onClick={() => void resetShortcut()}
            className="btn-ghost inline-flex min-h-9 items-center gap-1.5"
          >
            <RotateCcw className="h-4 w-4" />
            Reset shortcut
          </button>
        </div>
      </SettingRow>
      <SettingRow
        icon={Layers}
        dot={settings?.alwaysOnTop ? 'on' : 'off'}
        title="Stay above everything"
        subtitle={
          settings?.alwaysOnTop
            ? 'Uses the above-everything window level when the bar is open.'
            : 'The bar stays at normal window level.'
        }
        keywords="floating bar always on top above everything screen saver z order fullscreen overlay"
        control={
          <Toggle
            on={!!settings?.alwaysOnTop}
            onChange={(on) => void patchSettings({ alwaysOnTop: on })}
            disabled={!settings}
            label="Stay above everything"
          />
        }
      />
      <SettingRow
        icon={Volume2}
        dot={!voiceEnabled ? 'off' : voiceReadiness.ready ? 'on' : 'warn'}
        title="Voice answers"
        subtitle={`${providerLabel(voiceProvider)} · ${voiceReadiness.keyPath}`}
        keywords="floating bar voice answers realtime voice speak assistant replies tts provider"
        control={<Toggle on={voiceEnabled} onChange={saveVoiceEnabled} label="Voice answers" />}
      >
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_180px]">
          <select
            value={voiceProvider}
            onChange={(e) => saveVoiceProvider(e.target.value as RealtimeVoiceProvider)}
            className="glass-subtle min-w-0 rounded-lg px-4 py-3 text-sm text-text-secondary focus:outline-none"
          >
            <option value="omi-relay" className="bg-neutral-900">
              Omi relay
            </option>
            <option value="openai-byok" className="bg-neutral-900">
              OpenAI BYOK
            </option>
            <option value="local-kokoro" className="bg-neutral-900">
              Local Kokoro
            </option>
            <option value="elevenlabs" className="bg-neutral-900">
              ElevenLabs
            </option>
          </select>
          <StatusTile
            label="Readiness"
            value={
              !voiceEnabled
                ? 'Off'
                : voiceReadiness.ready
                  ? 'Ready'
                  : (voiceReadiness.reason ?? 'Needs setup')
            }
            tone={!voiceEnabled ? 'neutral' : voiceReadiness.ready ? 'good' : 'warn'}
          />
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <StatusTile
            label="Local TTS"
            value={localTtsRuntimeValue(localTtsStatus)}
            tone={
              voiceProvider === 'local-kokoro' && !voiceReadiness.ready && voiceEnabled
                ? 'warn'
                : localTtsStatus?.available
                  ? 'good'
                  : 'neutral'
            }
          />
          <StatusTile
            label="ElevenLabs"
            value={byokStatus?.providers.elevenlabs.configured ? 'Ready' : 'Needs key'}
            tone={
              voiceProvider === 'elevenlabs'
                ? byokStatus?.providers.elevenlabs.configured
                  ? 'good'
                  : 'warn'
                : 'neutral'
            }
          />
          <StatusTile
            label="Realtime path"
            value={voiceReadiness.transcriptionPath}
            tone="neutral"
          />
        </div>
      </SettingRow>
      <SettingRow
        icon={Mic}
        title="Push to talk"
        subtitle="Hold Space in the floating bar to capture a voice question."
        keywords="floating bar push to talk ptt microphone voice hold space ask question"
      />
      <SettingRow
        icon={Activity}
        dot={status?.effectiveSummonEnabled ? 'on' : 'off'}
        title="Status and usage"
        subtitle="Shortcut registration, window state, above-everything state, and recent bar activity."
        keywords="floating bar status usage diagnostics activity last opened asked voice captured shortcut registered"
        control={
          <button
            type="button"
            disabled={refreshingStatus}
            onClick={() => void refreshStatus()}
            className="btn-ghost inline-flex min-h-9 items-center gap-1.5 disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${refreshingStatus ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        }
      >
        <div className="grid gap-2 sm:grid-cols-2">
          <StatusTile
            label="Shortcut"
            value={shortcutRegistered ? shortcut : 'Not registered'}
            tone={shortcutRegistered ? 'good' : 'warn'}
          />
          <StatusTile
            label="Window"
            value={windowState}
            tone={status?.open ? 'good' : status?.windowCreated ? 'neutral' : 'warn'}
          />
          <StatusTile
            label="Above everything"
            value={status?.alwaysOnTop ? status.alwaysOnTopLevel : 'Normal'}
            tone={status?.alwaysOnTop ? 'good' : 'neutral'}
          />
          <StatusTile
            label="Ready"
            value={status?.overlayReady ? 'Renderer measured' : 'Waiting for first open'}
            tone={status?.overlayReady ? 'good' : 'neutral'}
          />
          <StatusTile
            label="Last summoned"
            value={formatTime(settings?.lastSummonedAt)}
            tone={settings?.lastSummonedAt ? 'good' : 'neutral'}
          />
          <StatusTile
            label="Last opened"
            value={formatTime(settings?.lastOpenedAt)}
            tone={settings?.lastOpenedAt ? 'good' : 'neutral'}
          />
          <StatusTile
            label="Ask count"
            value={`${settings?.askCount ?? 0}`}
            tone={(settings?.askCount ?? 0) > 0 ? 'good' : 'neutral'}
          />
          <StatusTile
            label="Voice captures"
            value={`${settings?.voiceCaptureCount ?? 0}`}
            tone={(settings?.voiceCaptureCount ?? 0) > 0 ? 'good' : 'neutral'}
          />
        </div>
      </SettingRow>
    </>
  )
}
