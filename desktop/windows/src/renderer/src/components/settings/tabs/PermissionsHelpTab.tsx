import { useEffect, useState } from 'react'
import { Bell, HelpCircle, Mic, Monitor, RotateCcw, ShieldCheck } from 'lucide-react'
import type { WindowsSystemStatus } from '../../../../../shared/types'
import { resetOnboarding } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'
import { StatusTile } from '../StatusTile'

function permissionTone(value: string): 'good' | 'warn' | 'neutral' {
  if (value === 'granted') return 'good'
  if (value === 'denied') return 'warn'
  return 'neutral'
}

export function PermissionsHelpTab(): React.JSX.Element {
  const [status, setStatus] = useState<WindowsSystemStatus | null>(null)

  const refresh = async (): Promise<void> => {
    setStatus(await window.omi.systemGetStatus())
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0)
    return () => window.clearTimeout(timer)
  }, [])

  return (
    <>
      <SettingRow
        icon={ShieldCheck}
        title="Permission health"
        subtitle="Inspect the Windows permissions Omi depends on after onboarding."
        keywords="permissions health onboarding privacy microphone screen notifications help"
      >
        <div className="grid gap-2 sm:grid-cols-3">
          <StatusTile
            label="Microphone"
            value={status?.microphone ?? 'Checking'}
            tone={permissionTone(status?.microphone ?? 'unknown')}
          />
          <StatusTile
            label="Screen"
            value={status?.screenCapture ?? 'Checking'}
            tone={permissionTone(status?.screenCapture ?? 'unknown')}
          />
          <StatusTile
            label="Notifications"
            value={status?.notificationsSupported ? 'Supported' : 'Unavailable'}
            tone={status?.notificationsSupported ? 'good' : 'warn'}
          />
        </div>
        <button onClick={() => void refresh()} className="btn-ghost mt-3 px-3 py-2">
          Refresh status
        </button>
      </SettingRow>

      <SettingRow
        icon={Mic}
        title="Microphone access"
        subtitle="Open Windows microphone privacy settings if live transcription cannot hear you."
        keywords="microphone mic permission windows privacy settings"
        control={
          <button
            onClick={() => void window.omi.systemOpenExternal('windowsMicrophoneSettings')}
            className="btn-ghost px-3 py-2"
          >
            Open
          </button>
        }
      />
      <SettingRow
        icon={Monitor}
        title="Screen and privacy settings"
        subtitle="Open Windows privacy settings for screen, OCR, and foreground activity troubleshooting."
        keywords="screen capture privacy ocr foreground activity settings"
        control={
          <button
            onClick={() => void window.omi.systemOpenExternal('windowsPrivacySettings')}
            className="btn-ghost px-3 py-2"
          >
            Open
          </button>
        }
      />
      <SettingRow
        icon={Bell}
        title="Windows notification settings"
        subtitle="Open Windows notification settings if native Omi alerts are muted by the OS."
        keywords="notifications windows action center permission settings"
        control={
          <button
            onClick={() => void window.omi.systemOpenExternal('windowsNotificationSettings')}
            className="btn-ghost px-3 py-2"
          >
            Open
          </button>
        }
      />
      <SettingRow
        icon={RotateCcw}
        title="Run onboarding again"
        subtitle="Reset onboarding so permission and setup steps can be reviewed again."
        keywords="reset onboarding permissions setup help"
        control={
          <button
            onClick={() => {
              resetOnboarding()
              location.hash = '#/onboarding'
            }}
            className="btn-ghost px-3 py-2"
          >
            Reset
          </button>
        }
      />
      <SettingRow
        icon={HelpCircle}
        title="Help and support"
        subtitle="Open the Omi support issue path with this build's diagnostics."
        keywords="help founder support issue report diagnostics"
        control={
          <button
            onClick={() => void window.omi.systemOpenExternal('help')}
            className="btn-ghost px-3 py-2"
          >
            Open
          </button>
        }
      />
    </>
  )
}
