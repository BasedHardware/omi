// Transcription settings tab. Mac reference: SettingsContentView+Transcription.swift.
//
// Composition mirrors Mac: a "Language Mode" card with two radio options
// (auto-detect vs single language, the dropdown living inside the single card),
// then a "Local VAD gate" card — rendered in the Windows dark settings idiom
// (SettingRow chrome, white/neutral selection, no purple).
//
// Machinery: the single `language` preference feeds the /v4/listen and PTT
// transcribe sockets (read at session start), with the 'multi' sentinel meaning
// auto-detect. Persisted via setPreferences + synced to the account with the
// shared syncLanguage helper (PATCH /v1/users/language) — the same contract the
// old AccountTab profile row used, relocated here to match Mac. The VAD gate
// toggles the on-device silence gate on the ambient capture lanes
// (AudioSessionHost reads `vadGateEnabled` at session start).
//
// Deliberately NOT built (no Windows machinery — see the settings-parity report):
//  - Custom vocabulary (PATCH /v1/users/transcription-preferences carries
//    vocabulary + single_language_mode, but nothing plumbs keywords into the
//    listen/PTT params — a dead control until that lands).
//  - A separate voice-assistant languages multi-select (Windows uses the single
//    `language` for PTT too; there is no per-turn LID / voiceLanguages backend).
import { useState } from 'react'
import { Languages, Waves } from 'lucide-react'
import { LANGUAGES, DEFAULT_LANGUAGE } from '../../../lib/languages'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { syncLanguage } from '../../../lib/userProfile'
import { toast } from '../../../lib/toast'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'

const AUTO_DETECT = 'multi'
// Single-language choices exclude the 'multi' auto-detect sentinel.
const SINGLE_LANGUAGES = LANGUAGES.filter((l) => l.code !== AUTO_DETECT)

export function TranscriptionTab(): React.JSX.Element {
  const [language, setLanguageState] = useState(() => getPreferences().language)
  // Remember the last single-language pick so toggling auto-detect on then off
  // restores it instead of snapping back to English.
  const [lastSingle, setLastSingle] = useState(() =>
    getPreferences().language === AUTO_DETECT ? DEFAULT_LANGUAGE : getPreferences().language
  )
  // Default ON (gated) — matches the macOS-faithful default; undefined = enabled.
  const [vadGate, setVadGate] = useState(() => getPreferences().vadGateEnabled !== false)

  const autoDetect = language === AUTO_DETECT

  const applyLanguage = (code: string): void => {
    setLanguageState(code) // optimistic
    if (code !== AUTO_DETECT) setLastSingle(code)
    setPreferences({ language: code })
    // Best-effort account sync (the local pref already drives transcription; this
    // keeps the account's language in step, like the macOS client). Never blocks.
    void syncLanguage(code).catch(() => toast('Language sync failed', { tone: 'warn' }))
  }

  const changeVadGate = (next: boolean): void => {
    setVadGate(next) // optimistic
    setPreferences({ vadGateEnabled: next })
  }

  return (
    <>
      <SettingRow
        icon={Languages}
        title="Language mode"
        subtitle="How Omi transcribes what you say. Applies to your next recording session."
        keywords="language transcription auto-detect multilingual single accuracy speech"
      >
        <div className="space-y-2">
          <RadioCard
            selected={autoDetect}
            onSelect={() => applyLanguage(AUTO_DETECT)}
            title="Auto-detect (multi-language)"
            subtitle="Detects and transcribes several languages at once — best when you switch languages."
          />
          <RadioCard
            selected={!autoDetect}
            onSelect={() => applyLanguage(lastSingle)}
            title="Single language (better accuracy)"
            subtitle="Best when you speak one language. Pick it below."
          >
            {!autoDetect && (
              <div className="mt-3 flex items-center gap-2 text-sm text-text-tertiary">
                Language
                <select
                  value={language}
                  onChange={(e) => applyLanguage(e.target.value)}
                  className="rounded-md bg-white/10 px-2 py-1.5 text-sm text-white focus:outline-none"
                >
                  {SINGLE_LANGUAGES.map((l) => (
                    <option key={l.code} value={l.code} className="bg-neutral-900">
                      {l.label}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </RadioCard>
        </div>
      </SettingRow>

      <SettingRow
        icon={Waves}
        dot={vadGate ? 'on' : 'off'}
        title="Local VAD gate"
        subtitle="On-device voice-activity detection skips silence before it reaches transcription, reducing usage and cost. Turn off to send all captured audio."
        keywords="vad voice activity detection silence gate deepgram cost usage"
        control={<Toggle on={vadGate} onChange={changeVadGate} label="Local VAD gate" />}
      />
    </>
  )
}

/** A selectable option card (Mac's radio-card composition, Windows chrome): a
 *  ring indicator + title/subtitle, with an optional expanded body when selected.
 *  Selected state uses a neutral white ring/tint — never purple (INV-UI-1). */
function RadioCard(props: {
  selected: boolean
  onSelect: () => void
  title: string
  subtitle: string
  children?: React.ReactNode
}): React.JSX.Element {
  const { selected, onSelect, title, subtitle, children } = props
  return (
    <div
      role="radio"
      aria-checked={selected}
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect()
        }
      }}
      className={
        'cursor-pointer rounded-xl border px-4 py-3 transition-colors ' +
        (selected
          ? 'border-white/25 bg-white/[0.06]'
          : 'border-white/10 bg-white/[0.02] hover:bg-white/[0.04]')
      }
    >
      <div className="flex items-start gap-3">
        <span
          className={
            'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors ' +
            (selected ? 'border-white' : 'border-white/30')
          }
        >
          {selected && <span className="h-2 w-2 rounded-full bg-white" />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium text-text-primary">{title}</div>
          <div className="mt-0.5 text-xs text-text-tertiary">{subtitle}</div>
          {children}
        </div>
      </div>
    </div>
  )
}
