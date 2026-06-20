import { useEffect, useState } from 'react'
import { MessagesSquare, ALargeSmall, PanelTop, Mic } from 'lucide-react'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { UI_SCALE_LEVELS, scalePercent } from '../../../lib/uiScale'
import { micOptions, isSelectionAvailable, type MicOption } from '../../../lib/micDevices'
import { SettingRow } from '../SettingRow'
import { LevelSlider } from '../LevelSlider'

export function GeneralTab(): React.JSX.Element {
  const [chatHistoryMode, setChatHistoryMode] = useState(getPreferences().chatHistoryMode)
  const [uiScale, setUiScale] = useState(getPreferences().uiScale)
  const [overlayScale, setOverlayScale] = useState(getPreferences().overlayScale)
  const [micDeviceId, setMicDeviceId] = useState(getPreferences().micDeviceId ?? '')
  const [mics, setMics] = useState<MicOption[]>([])

  // Enumerate audio inputs on mount and whenever devices change (plug/unplug).
  // Device labels are only populated once mic permission has been granted (it is,
  // after onboarding); before that they fall back to "Microphone N".
  useEffect(() => {
    let cancelled = false
    const refresh = async (): Promise<void> => {
      try {
        const devices = await navigator.mediaDevices.enumerateDevices()
        if (!cancelled) setMics(micOptions(devices))
      } catch {
        if (!cancelled) setMics([])
      }
    }
    void refresh()
    navigator.mediaDevices.addEventListener('devicechange', refresh)
    return () => {
      cancelled = true
      navigator.mediaDevices.removeEventListener('devicechange', refresh)
    }
  }, [])

  const micSelectionStale = !isSelectionAvailable(micDeviceId, mics)

  return (
    <>
      <SettingRow
        icon={ALargeSmall}
        title="App font size"
        subtitle={`Scale the main window — text, spacing, and controls. Scale: ${scalePercent(uiScale)}`}
        keywords="font size text display scale zoom larger smaller accessibility app window"
      >
        <LevelSlider
          ariaLabel="App font size"
          value={uiScale}
          levels={UI_SCALE_LEVELS}
          onChange={(v) => {
            setUiScale(v)
            // main.tsx re-applies the root zoom live on this pref change.
            setPreferences({ uiScale: v })
          }}
        />
      </SettingRow>

      <SettingRow
        icon={PanelTop}
        title="Floating bar font size"
        subtitle={`Scale the floating bar independently of the app. Scale: ${scalePercent(overlayScale)}`}
        keywords="font size floating bar overlay scale zoom larger smaller accessibility"
      >
        <LevelSlider
          ariaLabel="Floating bar font size"
          value={overlayScale}
          levels={UI_SCALE_LEVELS}
          onChange={(v) => {
            setOverlayScale(v)
            setPreferences({ overlayScale: v })
            // Resize + re-zoom the (warm) overlay window to match.
            window.omiOverlay?.setScale(v)
          }}
        />
      </SettingRow>

      <SettingRow
        icon={Mic}
        title="Microphone"
        subtitle="Which input device feeds voice transcription (the floating bar and always-on recording). Defaults to your system's default mic."
        keywords="mic microphone input device audio recording transcription dictation source"
        control={
          <select
            value={micSelectionStale ? '__stale__' : micDeviceId}
            onChange={(e) => {
              const v = e.target.value === '__stale__' ? micDeviceId : e.target.value
              setMicDeviceId(v)
              setPreferences({ micDeviceId: v || undefined })
            }}
            className="max-w-[220px] truncate rounded-md bg-white/10 px-2 py-1.5 text-sm text-white focus:outline-none"
          >
            <option value="" className="bg-neutral-900">
              System default
            </option>
            {mics.map((m) => (
              <option key={m.deviceId} value={m.deviceId} className="bg-neutral-900">
                {m.label}
              </option>
            ))}
            {micSelectionStale && (
              <option value="__stale__" className="bg-neutral-900">
                Selected mic (unavailable)
              </option>
            )}
          </select>
        }
      />

      <SettingRow
        icon={MessagesSquare}
        title="Chat history"
        subtitle="By default, one ongoing conversation (shared with the floating bar) that persists across launches — scroll up in chat to load older messages. Or start a fresh conversation each launch."
        keywords="conversation thread floating bar history infinite"
        control={
          <select
            value={chatHistoryMode}
            onChange={(e) => {
              const v = e.target.value as 'per-launch' | 'infinite'
              setChatHistoryMode(v)
              setPreferences({ chatHistoryMode: v })
            }}
            className="rounded-md bg-white/10 px-2 py-1.5 text-sm text-white focus:outline-none"
          >
            <option value="infinite" className="bg-neutral-900">
              One ongoing conversation (default)
            </option>
            <option value="per-launch" className="bg-neutral-900">
              New conversation each launch
            </option>
          </select>
        }
      />
    </>
  )
}
