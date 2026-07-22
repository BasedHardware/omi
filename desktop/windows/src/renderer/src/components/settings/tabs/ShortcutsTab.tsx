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
// Disabling a chord (macOS's per-shortcut Off): built for the RECORD card only —
// its default Ctrl+Space collides with the Windows IME language-switch, so an
// "Off" chip lets the user release it. Deliberately NOT offered for Summon: that
// accelerator is also the push-to-talk hold trigger (main/bar gesture machine),
// so disabling it would silently kill PTT.
//
// Deliberately NOT built — no Windows machinery for any of these (all macOS-only):
// double-tap-to-lock, PTT sound cues, and mute-audio-while-talking.
import { useEffect, useRef, useState } from 'react'
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
        // Record-only: the "Off" chip. Summon omits this (coupled to PTT), so its
        // card renders no Off affordance.
        onSetEnabled={(enabled) =>
          window.omi?.setRecordHotkeyEnabled?.(enabled) ??
          Promise.resolve({ accelerator: '', registered: false, enabled })
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
  /** When provided, the card renders an "Off" chip that fully disables the chord
   *  (Record card only; Summon omits it — it's coupled to push-to-talk). */
  onSetEnabled?: (enabled: boolean) => Promise<RecordHotkeyState>
}): React.JSX.Element {
  const { icon, title, subtitle, keywords, defaultAccel, load, commit, onCommitted, onSetEnabled } =
    props
  const [accel, setAccel] = useState<string | null>(null)
  const [registered, setRegistered] = useState(true)
  const [enabled, setEnabled] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Set as soon as the user picks a chip / records a chord. The mount `load()` is
  // async, so a fast click whose commit resolves FIRST would otherwise be undone
  // by the (now stale) load result — ignore the load once the user has acted.
  const acted = useRef(false)

  useEffect(() => {
    let unmounted = false
    void load().then((h) => {
      if (unmounted || acted.current || !h) return
      setAccel(h.accelerator)
      setRegistered(h.registered)
      setEnabled(h.enabled !== false)
    })
    return () => {
      unmounted = true
    }
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
      acted.current = true
      const res = await commit(next)
      // Record card (intent model): a declined OS claim is still a SUCCESSFUL
      // commit — main persisted `next` and released the old chord. Report ok so
      // the hook takes its onCommitted path and the single canonical !registered
      // note ("held by another app") renders, rather than CHORD_IN_USE_MESSAGE
      // ("try another"), which reads as "nothing was applied" — and which a
      // re-opened Settings would then contradict. Summon (no onSetEnabled) keeps
      // the rollback semantics: ok:false there really does mean nothing changed.
      if (onSetEnabled) return { ok: true, registered: !!res?.registered }
      return { ok: !!res?.ok, registered: !!res?.registered }
    },
    onCommitted: (next, result) => {
      setAccel(next)
      setRegistered(result.registered)
      // Committing a binding implicitly re-enables the chord (main persists this).
      setEnabled(true)
      onCommitted?.(next)
    },
    onError: setError
  })

  // Clicking the default preset chip re-binds to the default (unless already there
  // AND enabled — a click while "Off" must still re-enable at the default).
  const selectDefault = async (): Promise<void> => {
    if (enabled && accel === defaultAccel) return
    acted.current = true
    setError(null)
    const res = await commit(defaultAccel)
    if (res?.ok) {
      setAccel(defaultAccel)
      setRegistered(true)
      setEnabled(true)
      onCommitted?.(defaultAccel)
    } else if (onSetEnabled) {
      // Record card: selecting a preset is an enable intent even when the OS can't
      // claim the chord (conflict) — reflect enabled; the !registered branch below
      // surfaces the same "held by another app" note as a fresh load (consistent
      // copy, rather than a second "try another" string for the identical state).
      setAccel(defaultAccel)
      setRegistered(false)
      setEnabled(true)
    } else {
      setError('That shortcut is already in use — try another.')
    }
  }

  // Clicking the "Off" chip fully disables the chord (Record card only).
  const selectOff = async (): Promise<void> => {
    if (!onSetEnabled || !enabled) return
    acted.current = true
    setError(null)
    const res = await onSetEnabled(false)
    setEnabled(res.enabled === true)
    setRegistered(!!res.registered)
  }

  // While off, neither preset appears selected — the "Off" chip owns selection.
  const isDefault = enabled && accel === defaultAccel
  const isCustom = enabled && accel != null && accel !== defaultAccel

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

          {/* Off chip — Record card only (onSetEnabled provided). Disables the
              chord entirely; the presets stay visible so the user can re-pick. */}
          {onSetEnabled && (
            <Chip selected={!enabled} onClick={() => void selectOff()}>
              <span>Off</span>
            </Chip>
          )}
        </div>

        {!enabled ? (
          <p className="text-xs text-white/40">Recording shortcut is off.</p>
        ) : error || !registered ? (
          <p className="text-xs text-amber-300">
            {error ?? 'This shortcut is held by another app — pick a different one.'}
          </p>
        ) : null}
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
