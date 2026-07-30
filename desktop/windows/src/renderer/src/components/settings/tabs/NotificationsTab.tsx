import { useEffect, useState } from 'react'
import { Bell, Gauge, Focus, Brain, Sparkles, Lightbulb } from 'lucide-react'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'
import { Slider } from '../controls/Slider'
import type { AssistantSettingsView } from '../../../../../shared/types'

// Frequency levels 0–5, mirroring Mac's stepped slider labels and the interval
// table in main/assistants/core/notify.ts (LEVEL_INTERVALS_MS).
const FREQUENCY_LABELS = ['Off', 'Minimal', 'Low', 'Balanced', 'High', 'Maximum']
const FREQUENCY_CAPTIONS = [
  'No proactive notifications',
  'At most every 60 min',
  'At most every 30 min',
  'At most every 10 min',
  'At most every 3 min',
  'No limit'
]

/**
 * Notifications tab — the opt-in that unblocks proactive assistants. Windows ships
 * with notificationFrequency=0 (Off, matching Mac's post-migration default), so
 * every proactive toast (Insight/Focus/Goals) is permanently silent until the user
 * raises the frequency here. This tab is the only surface that lets them.
 *
 * Scoped bridge only (assistantsGetSettings/SetSettings) — a whitelisted view of
 * the central app-settings store, never a generic settings pass-through. Writing a
 * setting is the whole action: the proactive coordinator re-syncs on any write.
 */
export function NotificationsTab(): React.JSX.Element {
  const [settings, setSettings] = useState<AssistantSettingsView | null>(null)

  useEffect(() => {
    void window.omi.assistantsGetSettings().then(setSettings)
    // Stay in lock-step if the same flag is written elsewhere (tray checkbox, a
    // future backend sync) — the broadcast pushes the fresh projection.
    return window.omi.onAssistantSettingsChanged(setSettings)
  }, [])

  const patch = (p: Partial<AssistantSettingsView>): void => {
    setSettings((cur) => (cur ? { ...cur, ...p } : cur)) // optimistic
    void window.omi.assistantsSetSettings(p).then(setSettings)
  }

  const notifOn = !!settings?.notificationsEnabled
  const level = settings?.notificationFrequency ?? 0
  // Per-assistant rows read as OFF and grey out while the master toggle is off,
  // mirroring Mac's `if notificationsEnabled` reveal.
  const subDisabled = !settings || !notifOn

  return (
    <>
      <SettingRow
        icon={Bell}
        dot={notifOn ? 'on' : 'off'}
        title="Notifications"
        subtitle="Control how often Omi's proactive assistants can notify you."
        keywords="proactive notifications master enable assistants"
        control={
          <Toggle
            on={notifOn}
            onChange={(on) => patch({ notificationsEnabled: on })}
            disabled={!settings}
            label="Notifications"
          />
        }
      />

      <SettingRow
        icon={Gauge}
        title="Frequency"
        subtitle="How often to receive notifications."
        keywords="frequency rate throttle interval off minimal low balanced high maximum"
        note={
          level === 0 ? (
            <span className="text-xs text-amber-400/90">
              Proactive notifications are off. Raise the frequency to let Omi notify you.
            </span>
          ) : undefined
        }
      >
        <div className="space-y-2">
          <div className="flex items-baseline justify-between text-sm">
            <span className="font-medium text-text-primary">{FREQUENCY_LABELS[level]}</span>
            <span className="text-text-tertiary">{FREQUENCY_CAPTIONS[level]}</span>
          </div>
          <Slider
            value={level}
            onChange={(v) => patch({ notificationFrequency: v })}
            min={0}
            max={5}
            step={1}
            ticks={[0, 1, 2, 3, 4, 5]}
            ariaLabel="Notification frequency"
            disabled={!settings}
            leftLabel={<span className="text-xs">Off</span>}
            rightLabel={<span className="text-xs">Max</span>}
          />
        </div>
      </SettingRow>

      <SettingRow
        icon={Focus}
        dot={settings && settings.focusNotificationsEnabled && notifOn ? 'on' : 'off'}
        title="Focus notifications"
        subtitle="Show a notification on focus changes."
        keywords="focus notifications distraction refocus"
        note={
          <span className="text-xs text-text-tertiary">
            Turning this off also pauses focus analysis entirely.
          </span>
        }
        control={
          <Toggle
            on={!!settings?.focusNotificationsEnabled}
            onChange={(on) => patch({ focusNotificationsEnabled: on })}
            disabled={subDisabled}
            label="Focus notifications"
          />
        }
      />

      <SettingRow
        icon={Brain}
        dot={settings && settings.memoryEnabled && notifOn ? 'on' : 'off'}
        title="Extract memories from your screen"
        subtitle="Periodically looks at your screen and saves useful facts to your Omi memories. Runs quietly — no notifications. Requires Screen Analysis (Settings → General)."
        keywords="memory notifications extraction screen facts memories synth"
        control={
          <Toggle
            on={!!settings?.memoryEnabled}
            onChange={(on) => patch({ memoryEnabled: on })}
            disabled={subDisabled}
            label="Extract memories from your screen"
          />
        }
      />

      <SettingRow
        icon={Sparkles}
        dot={settings && settings.glowOverlayEnabled && notifOn ? 'on' : 'off'}
        title="Focus glow"
        subtitle="Draw a colored ring around the active window when Focus detects a distraction or a refocus."
        keywords="focus glow ring overlay halo distraction"
        control={
          <Toggle
            on={!!settings?.glowOverlayEnabled}
            onChange={(on) => patch({ glowOverlayEnabled: on })}
            disabled={subDisabled}
            label="Focus glow"
          />
        }
      />

      <SettingRow
        icon={Lightbulb}
        title="Proactive insights"
        subtitle="Proactive insights are configured in Settings → Rewind."
        keywords="insights proactive suggestion notification rewind"
      />
    </>
  )
}
