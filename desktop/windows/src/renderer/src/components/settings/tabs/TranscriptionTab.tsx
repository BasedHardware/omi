import { useEffect, useState } from 'react'
import { Activity, Cpu, Languages, Mic, Radio } from 'lucide-react'
import type { ByokStatus, LocalSttStatus, SttMode } from '../../../../../shared/types'
import { LANGUAGES, languageLabel } from '../../../lib/languages'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { realtimeVoiceReadiness, type RealtimeVoiceProvider } from '../../../lib/realtimeVoice'
import {
  formatRecordingStatusTime,
  useContinuousRecordingStatus,
  websocketStateLabel,
  websocketStateTone
} from '../../../lib/continuousRecordingStatus'
import { syncLanguage } from '../../../lib/userProfile'
import { toast } from '../../../lib/toast'
import { SettingRow } from '../SettingRow'
import { StatusTile } from '../StatusTile'
import { Toggle } from '../Toggle'

function continuousRecordingDot(
  signedIn: boolean,
  enabled: boolean,
  websocketTone: 'good' | 'warn' | 'neutral'
): 'on' | 'off' | 'warn' {
  if (!enabled) return 'off'
  if (!signedIn || websocketTone === 'warn') return 'warn'
  return websocketTone === 'good' ? 'on' : 'warn'
}

function localRuntimeValue(status: LocalSttStatus | null): string {
  const state = status?.runtime.installState
  if (!state) return 'Checking'
  if (state === 'installed' || state === 'running') return 'Installed'
  if (state === 'installing') return 'Installing'
  if (state === 'not_installed') return 'Installs on first use'
  if (state === 'unsupported') return 'Unavailable'
  return 'Needs attention'
}

function localRuntimeSubtitle(sttMode: SttMode, status: LocalSttStatus | null): string {
  if (sttMode === 'cloud') return 'Hosted Omi /v4/listen'
  if (!status) return 'Checking local Parakeet'
  if (status.available) return 'Local Parakeet ready'
  if (status.runtime.installState === 'installing') return 'Installing local Parakeet'
  if (status.runtime.canInstall) return 'Local Parakeet installs on first use'
  return status.reason ?? 'Local Parakeet unavailable'
}

function localRuntimeTone(
  status: LocalSttStatus | null,
  sttMode: SttMode
): 'good' | 'warn' | 'neutral' {
  if (status?.available) return 'good'
  if (sttMode === 'local-parakeet' || status?.runtime.installState === 'error') return 'warn'
  return 'neutral'
}

export function TranscriptionTab(): React.JSX.Element {
  const [language, setLanguage] = useState(getPreferences().language)
  const [continuousRec, setContinuousRec] = useState<boolean>(
    () => !!getPreferences().continuousRecording
  )
  const [sttMode, setSttMode] = useState<SttMode>(() => getPreferences().sttMode ?? 'auto')
  const [localSttStatus, setLocalSttStatus] = useState<LocalSttStatus | null>(null)
  const [realtimeVoiceEnabled, setRealtimeVoiceEnabled] = useState<boolean>(
    () => !!getPreferences().realtimeVoiceEnabled
  )
  const [realtimeVoiceProvider, setRealtimeVoiceProvider] = useState<RealtimeVoiceProvider>(
    () => getPreferences().realtimeVoiceProvider ?? 'omi-relay'
  )
  const [byokStatus, setByokStatus] = useState<ByokStatus | null>(null)
  const recordingStatus = useContinuousRecordingStatus()
  const socketTone = websocketStateTone(recordingStatus.websocketState)
  const authValue = recordingStatus.signedIn
    ? recordingStatus.authEmail
      ? `Signed in as ${recordingStatus.authEmail}`
      : 'Signed in'
    : 'Not signed in'
  const recordingValue = !recordingStatus.recordingEnabled
    ? 'Off'
    : recordingStatus.sessionActive
      ? 'Enabled, session active'
      : recordingStatus.signedIn
        ? 'Enabled, waiting'
        : 'Enabled, sign-in required'
  const websocketValue = `${websocketStateLabel(recordingStatus.websocketState)}${
    recordingStatus.websocketUpdatedAt
      ? `, updated ${formatRecordingStatusTime(recordingStatus.websocketUpdatedAt)}`
      : ''
  }`
  const boundaryValue = recordingStatus.lastConversationBoundaryAt
    ? formatRecordingStatusTime(recordingStatus.lastConversationBoundaryAt)
    : recordingStatus.lastEventType
      ? recordingStatus.lastEventType
      : 'None'

  const toggleContinuous = (): void => {
    const next = !continuousRec
    setContinuousRec(next)
    setPreferences({ continuousRecording: next })
  }

  const toggleRealtimeVoice = (): void => {
    const next = !realtimeVoiceEnabled
    setRealtimeVoiceEnabled(next)
    setPreferences({ realtimeVoiceEnabled: next })
  }

  const saveSttMode = (next: SttMode): void => {
    setSttMode(next)
    setPreferences({ sttMode: next })
  }

  const voiceReadiness = realtimeVoiceReadiness(
    {
      ...getPreferences(),
      realtimeVoiceEnabled,
      realtimeVoiceProvider
    },
    byokStatus
  )

  useEffect(() => {
    let canceled = false
    window.omi
      .byokStatus()
      .then((status) => {
        if (!canceled) setByokStatus(status)
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
        .localSttStatus()
        .then((status) => {
          if (!canceled) setLocalSttStatus(status)
        })
        .catch(() => {
          if (!canceled) setLocalSttStatus(null)
        })
    }
    refresh()
    const timer = setInterval(refresh, 15000)
    return () => {
      canceled = true
      clearInterval(timer)
    }
  }, [])

  const saveLanguage = (): void => {
    setPreferences({ language })
    void syncLanguage(language).catch(() => toast('Language sync failed', { tone: 'warn' }))
    toast('Transcription language saved', { tone: 'success' })
  }

  return (
    <>
      <SettingRow
        icon={Languages}
        title="Transcription language"
        subtitle="Language used for continuous recording and voice transcription."
        keywords="transcription language speech to text stt locale microphone audio"
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="glass-subtle min-w-0 flex-1 rounded-lg px-4 py-3 text-sm text-text-secondary focus:outline-none"
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code} className="bg-neutral-900">
                {l.label}
              </option>
            ))}
          </select>
          <button onClick={saveLanguage} className="btn-ghost">
            Save · {languageLabel(language)}
          </button>
        </div>
      </SettingRow>
      <SettingRow
        icon={Mic}
        dot={continuousRec ? 'on' : 'off'}
        title="Continuous recording"
        subtitle="Always-on microphone. Omi turns what you hear into conversations automatically."
        keywords="continuous recording microphone audio always-on transcription listen"
        control={
          <Toggle on={continuousRec} onChange={toggleContinuous} label="Continuous recording" />
        }
      />
      <SettingRow
        icon={Cpu}
        dot={
          sttMode === 'cloud'
            ? 'off'
            : localSttStatus?.available
              ? 'on'
              : sttMode === 'local-parakeet'
                ? 'warn'
                : 'off'
        }
        title="Speech-to-text runtime"
        subtitle={localRuntimeSubtitle(sttMode, localSttStatus)}
        keywords="local stt parakeet nvidia cuda offline speech transcription runtime"
      >
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_180px]">
          <select
            value={sttMode}
            onChange={(e) => saveSttMode(e.target.value as SttMode)}
            className="glass-subtle min-w-0 rounded-lg px-4 py-3 text-sm text-text-secondary focus:outline-none"
          >
            <option value="auto" className="bg-neutral-900">
              Auto
            </option>
            <option value="cloud" className="bg-neutral-900">
              Hosted Omi
            </option>
            <option value="local-parakeet" className="bg-neutral-900">
              Local Parakeet
            </option>
          </select>
          <StatusTile
            label="Local STT"
            value={
              localSttStatus?.available
                ? 'Ready'
                : localSttStatus?.runtime.canInstall
                  ? 'First-use install'
                  : 'Unavailable'
            }
            tone={localRuntimeTone(localSttStatus, sttMode)}
          />
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <StatusTile
            label="Local runtime"
            value={localRuntimeValue(localSttStatus)}
            tone={localRuntimeTone(localSttStatus, sttMode)}
          />
          <StatusTile
            label="NVIDIA"
            value={
              localSttStatus?.nvidiaAvailable == null
                ? 'Not checked'
                : localSttStatus.nvidiaAvailable
                  ? 'Detected'
                  : 'Not detected'
            }
            tone={
              localSttStatus?.nvidiaAvailable == null
                ? 'neutral'
                : localSttStatus.nvidiaAvailable
                  ? 'good'
                  : 'warn'
            }
          />
        </div>
      </SettingRow>
      <SettingRow
        icon={Radio}
        dot={!realtimeVoiceEnabled ? 'off' : voiceReadiness.ready ? 'on' : 'warn'}
        title="Realtime voice"
        subtitle={`${voiceReadiness.label} · ${voiceReadiness.keyPath}`}
        keywords="realtime voice omni openai byok microphone voice conversation relay"
        control={
          <Toggle on={realtimeVoiceEnabled} onChange={toggleRealtimeVoice} label="Realtime voice" />
        }
      >
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_180px]">
          <select
            value={realtimeVoiceProvider}
            onChange={(e) => {
              const provider = e.target.value as RealtimeVoiceProvider
              setRealtimeVoiceProvider(provider)
              setPreferences({ realtimeVoiceProvider: provider })
            }}
            className="glass-subtle min-w-0 rounded-lg px-4 py-3 text-sm text-text-secondary focus:outline-none"
          >
            <option value="omi-relay" className="bg-neutral-900">
              Omi relay
            </option>
            <option value="openai-byok" className="bg-neutral-900">
              OpenAI BYOK
            </option>
          </select>
          <StatusTile
            label="Voice readiness"
            value={
              !realtimeVoiceEnabled
                ? 'Off'
                : voiceReadiness.ready
                  ? 'Ready'
                  : (voiceReadiness.reason ?? 'Needs setup')
            }
            tone={!realtimeVoiceEnabled ? 'neutral' : voiceReadiness.ready ? 'good' : 'warn'}
          />
        </div>
        <div className="mt-3 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-white/45">
          {voiceReadiness.transcriptionPath}
        </div>
      </SettingRow>
      <SettingRow
        icon={Activity}
        dot={continuousRecordingDot(
          recordingStatus.signedIn,
          recordingStatus.recordingEnabled,
          socketTone
        )}
        title="Continuous recording status"
        subtitle="Auth, microphone, Omi listen socket, and latest transcript/conversation refresh."
        keywords="continuous recording status microphone websocket listen transcript sync auth"
      >
        <div className="space-y-3">
          <div className="grid gap-2 sm:grid-cols-2">
            <StatusTile
              label="Auth"
              value={authValue}
              tone={recordingStatus.signedIn ? 'good' : 'warn'}
            />
            <StatusTile
              label="Recording"
              value={recordingValue}
              tone={
                !recordingStatus.recordingEnabled
                  ? 'neutral'
                  : recordingStatus.sessionActive
                    ? 'good'
                    : 'warn'
              }
            />
            <StatusTile label="WebSocket" value={websocketValue} tone={socketTone} />
            <StatusTile
              label="Last transcript"
              value={formatRecordingStatusTime(recordingStatus.lastTranscriptAt)}
              tone={recordingStatus.lastTranscriptAt ? 'good' : 'neutral'}
            />
            <StatusTile
              label="Last conversation sync"
              value={formatRecordingStatusTime(recordingStatus.lastConversationSyncAt)}
              tone={recordingStatus.lastConversationSyncAt ? 'good' : 'neutral'}
            />
            <StatusTile
              label="Last boundary"
              value={boundaryValue}
              tone={recordingStatus.lastConversationBoundaryAt ? 'good' : 'neutral'}
            />
          </div>
          {recordingStatus.lastError && (
            <div className="rounded-lg border border-amber-300/20 bg-amber-300/10 px-3 py-2 text-xs text-amber-100">
              Last listen error: {recordingStatus.lastError}
            </div>
          )}
        </div>
      </SettingRow>
    </>
  )
}
