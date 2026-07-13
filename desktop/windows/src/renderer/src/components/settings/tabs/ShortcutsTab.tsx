// Shortcuts settings tab. Mac reference: ShortcutsSettingsSection.swift.
//
// Composition mirrors Mac: one CARD per global shortcut (Ask-omi/summon first,
// then record), each with a title/description, a row of selectable chips (the
// default preset + a Custom recorder chip), and a conflict warning — rendered in
// the Windows dark settings idiom (SettingRow chrome, white/neutral selection,
// no purple).
//
// Machinery (both chords are real, rebindable, persisted):
//  - Summon — window.omi.getSummonHotkey / setSummonHotkey (persisted in main
//    appSettings.summonHotkey; also mirrored to the legacy overlayShortcut pref so
//    App.tsx's startup re-apply converges). Default Shift+Space.
//  - Record — window.omi.getRecordHotkey / setRecordHotkey (persisted in main
//    appSettings.recordHotkey). Default Ctrl+Space.
// Rebinds reuse the shared capture-phase recorder (useChordRecorder) and the
// shared suspend/resume of ALL global chords, so pressing the CURRENT chord during
// a rebind is captured instead of firing. A chord already owned by another app
// surfaces registered=false → the amber "held by another app" warning (the real
// silent-failure fix: a persisted/conflicting chord previously failed with only a
// console.warn at boot).
//
// Deliberately NOT built — no Windows machinery for any of these (all macOS-only):
// disabling a global chord, double-tap-to-lock, PTT sound cues, and mute-audio-
// while-talking.
import { useEffect, useState } from 'react'
import { Keyboard, MessageSquareText } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { RecordHotkeyState } from '../../../../../shared/types'
import { setPreferences } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'
import { acceleratorToTokens, DEFAULT_OVERLAY_ACCELERATOR } from '../../../lib/overlayShortcut'
import { useChordRecorder } from '../../../hooks/useChordRecorder'
import { DEFAULT_RECORD_HOTKEY } from '../../../../../shared/hotkeyDefaults'

export function ShortcutsTab(): React.JSX.Element {
  return (
    <>
      <ShortcutCard
        icon={MessageSquareText}
        title="Summon hotkey"
        subtitle="Global shortcut to reveal the floating bar and ask a question."
        keywords="hotkey shortcut summon floating bar overlay ask accelerator keybinding rebind custom"
        defaultAccel={DEFAULT_OVERLAY_ACCELERATOR}
        load={() => window.omi?.getSummonHotkey?.() ?? Promise.resolve(null)}
        commit={(next) =>
          window.omi?.setSummonHotkey?.(next) ?? Promise.resolve({ ok: false, registered: false })
        }
        // Mirror to the legacy pref so App.tsx's startup re-apply converges.
        onCommitted={(next) => setPreferences({ overlayShortcut: next })}
      />
      <ShortcutCard
        icon={Keyboard}
        title="Record hotkey"
        subtitle="Global shortcut to start and stop recording."
        keywords="hotkey shortcut record accelerator keybinding rebind mic custom"
        defaultAccel={DEFAULT_RECORD_HOTKEY}
        load={() => window.omi?.getRecordHotkey?.() ?? Promise.resolve(null)}
        commit={(next) =>
          window.omi?.setRecordHotkey?.(next) ?? Promise.resolve({ ok: false, registered: false })
        }
      />
    </>
  )
}

/** Keycap chips for an accelerator (e.g. "Ctrl" + "Space"). */
function Keycaps({ accel }: { accel: string }): React.JSX.Element {
  return (
    <span className="flex items-center gap-1">
      {acceleratorToTokens(accel).map((t, i) => (
        <kbd
          key={`${t}-${i}`}
          className="flex h-6 min-w-6 items-center justify-center rounded-md bg-black/30 px-1.5 text-xs font-semibold text-white/85"
        >
          {t}
        </kbd>
      ))}
    </span>
  )
}

/**
 * One rebindable global-shortcut card: the default preset chip + a Custom chip
 * (which records a new chord), the current chord shown as keycaps, and an amber
 * warning when the OS hasn't claimed it. `load` fetches the current accelerator +
 * registration; `commit` persists a captured chord and reports OS acceptance.
 */
function ShortcutCard(props: {
  icon: LucideIcon
  title: string
  subtitle: string
  keywords: string
  defaultAccel: string
  load: () => Promise<RecordHotkeyState | null>
  commit: (accelerator: string) => Promise<{ ok: boolean; registered: boolean }>
  onCommitted?: (accelerator: string) => void
}): React.JSX.Element {
  const { icon, title, subtitle, keywords, defaultAccel, load, commit, onCommitted } = props
  const [accel, setAccel] = useState<string | null>(null)
  const [registered, setRegistered] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void load().then((h) => {
      if (!h) return
      setAccel(h.accelerator)
      setRegistered(h.registered)
    })
    // Mount-only: `load` is a stable inline closure per card.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // suspend/resume release ALL global chords while recording — otherwise pressing
  // the CURRENT chord (e.g. Ctrl+Space / Shift+Space) fires it instead of being
  // captured. Shared handlers cover both the record and summon chords.
  const recorder = useChordRecorder({
    suspend: () => window.omi?.suspendShortcutCapture?.(),
    resume: () => window.omi?.resumeShortcutCapture?.(),
    commit: async (next) => {
      const res = await commit(next)
      return { ok: !!res?.ok, registered: !!res?.registered }
    },
    onCommitted: (next, result) => {
      setAccel(next)
      setRegistered(result.registered)
      onCommitted?.(next)
    },
    onError: setError
  })

  // Clicking the default preset chip re-binds to the default (unless already there).
  const selectDefault = async (): Promise<void> => {
    if (accel === defaultAccel) return
    setError(null)
    const res = await commit(defaultAccel)
    if (res?.ok) {
      setAccel(defaultAccel)
      setRegistered(!!res.registered)
      onCommitted?.(defaultAccel)
    } else {
      setError('That shortcut is already in use — try another.')
    }
  }

  const isDefault = accel === defaultAccel
  const isCustom = accel != null && accel !== defaultAccel

  return (
    <SettingRow icon={icon} title={title} subtitle={subtitle} keywords={keywords}>
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          {/* Default preset chip. */}
          <Chip selected={isDefault} onClick={() => void selectDefault()}>
            <Keycaps accel={defaultAccel} />
            <span className="text-white/50">Default</span>
          </Chip>

          {/* Custom chip — shows the current custom chord, or records a new one. */}
          <Chip selected={isCustom} onClick={() => recorder.start()} disabled={recorder.recording}>
            {recorder.recording ? (
              <span className="text-white/60">Press keys… (Esc to cancel)</span>
            ) : isCustom && accel ? (
              <>
                <Keycaps accel={accel} />
                <span className="text-white/50">Custom</span>
              </>
            ) : (
              <span>Custom…</span>
            )}
          </Chip>
        </div>

        {(error || !registered) && (
          <p className="text-xs text-amber-300">
            {error ?? 'This shortcut is held by another app — pick a different one.'}
          </p>
        )}
      </div>
    </SettingRow>
  )
}

/** A selectable chip (Mac's preset/custom chips, Windows chrome). Selected uses a
 *  neutral white ring/tint — never purple (INV-UI-1). */
function Chip(props: {
  selected: boolean
  onClick: () => void
  disabled?: boolean
  children: React.ReactNode
}): React.JSX.Element {
  const { selected, onClick, disabled, children } = props
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={
        'flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-colors disabled:opacity-40 ' +
        (selected
          ? 'border-white/25 bg-white/[0.08] text-white'
          : 'border-white/10 bg-white/[0.02] text-white/80 hover:bg-white/[0.06]')
      }
    >
      {children}
    </button>
  )
}
