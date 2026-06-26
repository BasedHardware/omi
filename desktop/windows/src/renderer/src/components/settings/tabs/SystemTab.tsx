import { useEffect, useState } from 'react'
import { Bluetooth, Download, Globe, Rocket, Settings, UploadCloud } from 'lucide-react'
import type { WindowsSystemStatus, WindowsUpdateStatus } from '../../../../../shared/types'
import { SettingRow } from '../SettingRow'
import { StatusTile } from '../StatusTile'
import { Toggle } from '../Toggle'

export function SystemTab(): React.JSX.Element {
  const [system, setSystem] = useState<WindowsSystemStatus | null>(null)
  const [updates, setUpdates] = useState<WindowsUpdateStatus | null>(null)
  const [checking, setChecking] = useState(false)

  const refresh = async (): Promise<void> => {
    const [systemStatus, updateStatus] = await Promise.all([
      window.omi.systemGetStatus(),
      window.omi.updaterGetStatus()
    ])
    setSystem(systemStatus)
    setUpdates(updateStatus)
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0)
    return () => window.clearTimeout(timer)
  }, [])

  const setLaunchAtLogin = async (enabled: boolean): Promise<void> => {
    setSystem(await window.omi.systemSetLaunchAtLogin(enabled))
  }

  const checkNow = async (): Promise<void> => {
    if (checking) return
    setChecking(true)
    try {
      setUpdates(await window.omi.updaterCheckNow())
    } finally {
      setChecking(false)
    }
  }

  return (
    <>
      <SettingRow
        icon={Rocket}
        dot={system?.launchAtLogin ? 'on' : 'off'}
        title="Launch at login"
        subtitle="Start Omi automatically when Windows signs in."
        keywords="launch login startup boot windows auto start"
        control={
          <Toggle
            on={!!system?.launchAtLogin}
            onChange={(enabled) => void setLaunchAtLogin(enabled)}
            disabled={!system}
            label="Launch at login"
          />
        }
      >
        <button
          onClick={() => void window.omi.systemOpenExternal('windowsStartupSettings')}
          className="btn-ghost px-3 py-2"
        >
          Open Windows startup settings
        </button>
      </SettingRow>

      <SettingRow
        icon={Download}
        dot={updates?.enabled && updates.configured ? 'on' : 'warn'}
        title="Updates"
        subtitle="Signed Windows update feed status, manual check, release notes, and last updater event."
        keywords="updates release notes changelog signed installer feed auto update"
        control={
          <button
            onClick={() => void checkNow()}
            disabled={checking}
            className="btn-ghost px-3 py-2 disabled:opacity-45"
          >
            {checking ? 'Checking...' : 'Check'}
          </button>
        }
      >
        <div className="grid gap-2 sm:grid-cols-3">
          <StatusTile
            label="Feed"
            value={!updates ? 'Checking' : updates.configured ? 'Configured' : 'Missing'}
            tone={updates?.configured ? 'good' : 'warn'}
          />
          <StatusTile
            label="Last event"
            value={updates?.lastEvent ?? 'None'}
            tone={updates?.lastError ? 'warn' : 'neutral'}
          />
          <StatusTile
            label="Version"
            value={updates?.lastVersion ?? 'Unknown'}
            tone={updates?.downloaded ? 'good' : 'neutral'}
          />
        </div>
        {updates?.lastError && (
          <div className="mt-3 rounded-lg border border-red-300/20 bg-red-950/20 px-3 py-2 text-xs text-red-100/80">
            {updates.lastError}
          </div>
        )}
        <button
          onClick={() => void window.omi.systemOpenExternal('releaseNotes')}
          className="btn-ghost mt-3 px-3 py-2"
        >
          Open release notes
        </button>
      </SettingRow>

      <SettingRow
        icon={Globe}
        title="Browser extension"
        subtitle="Windows exposes browser-extension setup from Settings instead of a separate macOS-style sidebar item."
        keywords="browser extension chrome setup"
        control={
          <button
            onClick={() => void window.omi.systemOpenExternal('browserExtension')}
            className="btn-ghost px-3 py-2"
          >
            Open
          </button>
        }
      />

      <SettingRow
        icon={Bluetooth}
        title="Omi device support"
        subtitle="Windows desktop uses this PC's microphone, system audio, screen capture, and local tools. Dedicated wearable pairing remains outside the Windows shell for now."
        keywords="device bluetooth hardware wearable omi pairing support decision"
      />

      <SettingRow
        icon={UploadCloud}
        title="Package validation"
        subtitle="Final installer/package launch checks remain a manual Windows verification step."
        keywords="package installer validation manual windows launch verification"
      />

      <SettingRow
        icon={Settings}
        title="Platform decision"
        subtitle="Device, browser-extension, launch-at-login, and update controls live here to preserve the redesigned Windows UX."
        keywords="platform decision parity macos windows redesign"
      />
    </>
  )
}
