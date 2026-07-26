import { useEffect, useState } from 'react'
import { Activity, EyeOff, Monitor, ShieldCheck } from 'lucide-react'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'
import type { UsageSettings } from '../../../../../shared/types'

const RETENTION_OPTIONS: ReadonlyArray<{ days: number; label: string }> = [
  { days: 30, label: '30 days' },
  { days: 45, label: '45 days (recommended)' },
  { days: 60, label: '60 days' },
  { days: 90, label: '90 days' },
  { days: 180, label: '180 days' }
]

export function PrivacyTab(): React.JSX.Element {
  const [usage, setUsage] = useState<UsageSettings | null>(null)
  useEffect(() => {
    window.omi
      .usageGetSettings()
      .then(setUsage)
      .catch(() => setUsage(null))
  }, [])
  const saveUsage = async (next: UsageSettings): Promise<void> => {
    setUsage(await window.omi.usageSetSettings(next))
  }

  // Bar/HUD screen-share privacy: exclude the top-edge bar from captures
  // (WDA_EXCLUDEFROMCAPTURE). Persisted in main's app settings; applied live.
  const [hudProtected, setHudProtected] = useState<boolean | null>(null)
  useEffect(() => {
    window.omiBar
      .getContentProtection()
      .then(setHudProtected)
      .catch(() => setHudProtected(null))
  }, [])
  const toggleHudProtection = (on: boolean): void => {
    setHudProtected(on)
    void window.omiBar.setContentProtection(on).then(setHudProtected)
  }

  // "Screen Sharing in Chat" (Mac's chatScreenshotSharingEnabled, default ON).
  // The consent gate for the model-invoked capture_screen tool: on → Omi may
  // capture the screen when you ask about it; off → the tool is refused. Turning
  // it on captures nothing by itself — it only permits the tool.
  const [screenShareInChat, setScreenShareInChat] = useState<boolean | null>(null)
  useEffect(() => {
    window.omi
      .getChatScreenshotSharing()
      .then(setScreenShareInChat)
      .catch(() => setScreenShareInChat(null))
  }, [])
  const toggleScreenShareInChat = (on: boolean): void => {
    setScreenShareInChat(on)
    void window.omi.setChatScreenshotSharing(on).then(setScreenShareInChat)
  }

  return (
    <>
      <SettingRow
        icon={Activity}
        dot={usage?.enabled ? 'on' : 'off'}
        title="App-usage tracking"
        subtitle="Records which apps you actively use (app name only, never window titles) — locally — to improve memory ranking."
        keywords="usage foreground app tracking privacy"
        control={
          <Toggle
            on={!!usage?.enabled}
            onChange={(on) => usage && void saveUsage({ ...usage, enabled: on })}
            disabled={!usage}
            label="App-usage tracking"
          />
        }
      >
        {usage?.enabled && (
          <label className="flex items-center gap-2 text-sm text-text-secondary">
            <span>Forget apps not used in</span>
            <select
              value={usage.retentionDays}
              onChange={(e) => void saveUsage({ ...usage, retentionDays: Number(e.target.value) })}
              className="rounded-md bg-white/10 px-3 py-1.5 text-sm text-white focus:outline-none"
            >
              {RETENTION_OPTIONS.map((o) => (
                <option key={o.days} value={o.days} className="bg-neutral-900">
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </SettingRow>
      <SettingRow
        icon={EyeOff}
        dot={hudProtected ? 'on' : 'off'}
        title="Hide the Omi bar from screen sharing"
        subtitle="Excludes the top-edge bar from screenshots, recordings, and shared screens. Turn off if you want it visible in captures."
        keywords="bar hud screen share capture protection privacy exclude recording"
        control={
          <Toggle
            on={!!hudProtected}
            onChange={toggleHudProtection}
            disabled={hudProtected === null}
            label="Hide the Omi bar from screen sharing"
          />
        }
      />
      <SettingRow
        icon={Monitor}
        dot={screenShareInChat ? 'on' : 'off'}
        title="Screen Sharing in Chat"
        subtitle="Let Omi capture your screen when you ask about what's on it. Omi only captures when you ask — turning this on doesn't share anything on its own."
        keywords="screen sharing chat capture screenshot ask omi see my screen vision"
        control={
          <Toggle
            on={!!screenShareInChat}
            onChange={toggleScreenShareInChat}
            disabled={screenShareInChat === null}
            label="Screen Sharing in Chat"
          />
        }
      />
      <SettingRow
        icon={ShieldCheck}
        title="On-device by default"
        subtitle="Your screen timeline, file index, and app usage stay on this PC. Only synthesized facts (memories) are sent to your Omi account, and only for features you turn on."
        keywords="privacy local data on-device cloud"
      />
    </>
  )
}
