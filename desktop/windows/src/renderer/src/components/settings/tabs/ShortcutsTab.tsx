import { useEffect, useState } from 'react'
import { Keyboard, Mic, RotateCcw } from 'lucide-react'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import {
  DEFAULT_OVERLAY_ACCELERATOR,
  acceleratorToTokens,
  eventToAccelerator,
  validateCustomAccelerator
} from '../../../lib/overlayShortcut'
import { SettingRow } from '../SettingRow'

function ShortcutKeycaps({ accelerator }: { accelerator: string }): React.JSX.Element {
  const tokens = acceleratorToTokens(accelerator)
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

export function ShortcutsTab(): React.JSX.Element {
  const [accelerator, setAcceleratorState] = useState(
    () => getPreferences().overlayShortcut ?? DEFAULT_OVERLAY_ACCELERATOR
  )
  const [recording, setRecording] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!recording) return
    const onKeyDown = (e: KeyboardEvent): void => {
      e.preventDefault()
      e.stopPropagation()
      if (e.key === 'Escape') {
        void window.omiOverlay?.resumeShortcut()
        setRecording(false)
        setError(null)
        return
      }

      const next = eventToAccelerator(e)
      if (!next) return
      const valid = validateCustomAccelerator(next)
      if (!valid.ok) {
        setError(valid.reason)
        return
      }

      void (async () => {
        const ok = await window.omiOverlay?.setAccelerator(next)
        if (ok) {
          setAcceleratorState(next)
          setPreferences({ overlayShortcut: next })
          setError(null)
        } else {
          setError('That shortcut is already in use.')
        }
        setRecording(false)
      })()
    }

    window.addEventListener('keydown', onKeyDown, true)
    return () => {
      window.removeEventListener('keydown', onKeyDown, true)
      void window.omiOverlay?.resumeShortcut()
    }
  }, [recording])

  const startRecording = (): void => {
    setError(null)
    window.omiOverlay?.suspendShortcut()
    setRecording(true)
  }

  const resetShortcut = (): void => {
    void window.omiOverlay?.setAccelerator(DEFAULT_OVERLAY_ACCELERATOR)
    setAcceleratorState(DEFAULT_OVERLAY_ACCELERATOR)
    setPreferences({ overlayShortcut: DEFAULT_OVERLAY_ACCELERATOR })
    setError(null)
    setRecording(false)
  }

  return (
    <>
      <SettingRow
        icon={Keyboard}
        title="Ask Omi shortcut"
        subtitle="Global shortcut to open the floating chat bar from anywhere."
        keywords="shortcuts shortcut hotkey keyboard global ask omi floating bar summon command control ctrl space"
      >
        <div className="space-y-3">
          <ShortcutKeycaps accelerator={accelerator} />
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={startRecording}
              disabled={recording}
              className="btn-ghost disabled:opacity-40"
            >
              {recording ? 'Recording...' : 'Change shortcut'}
            </button>
            <button
              type="button"
              onClick={resetShortcut}
              className="btn-ghost inline-flex items-center gap-2"
            >
              <RotateCcw className="h-4 w-4" />
              Reset
            </button>
            <span className={error ? 'text-xs text-amber-300' : 'text-xs text-text-tertiary'}>
              {error ?? (recording ? 'Press your new shortcut, or Esc to cancel.' : '')}
            </span>
          </div>
        </div>
      </SettingRow>
      <SettingRow
        icon={Mic}
        title="Push to talk"
        subtitle="When the floating bar is open, hold Space to speak and release to send."
        keywords="shortcut push to talk ptt microphone voice hold space floating bar"
      />
    </>
  )
}
