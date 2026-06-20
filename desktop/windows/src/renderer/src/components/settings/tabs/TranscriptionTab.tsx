import { useState } from 'react'
import { Activity, Languages, Mic } from 'lucide-react'
import { LANGUAGES, languageLabel } from '../../../lib/languages'
import { getPreferences, setPreferences } from '../../../lib/preferences'
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

export function TranscriptionTab(): React.JSX.Element {
  const [language, setLanguage] = useState(getPreferences().language)
  const [continuousRec, setContinuousRec] = useState<boolean>(
    () => !!getPreferences().continuousRecording
  )
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
