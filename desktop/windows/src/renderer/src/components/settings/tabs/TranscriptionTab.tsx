import { useState } from 'react'
import { Languages, Mic2, Filter } from 'lucide-react'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'

const SUPPORTED_LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'es', label: 'Spanish' },
  { code: 'fr', label: 'French' },
  { code: 'de', label: 'German' },
  { code: 'it', label: 'Italian' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'nl', label: 'Dutch' },
  { code: 'pl', label: 'Polish' },
  { code: 'ru', label: 'Russian' },
  { code: 'zh', label: 'Chinese' },
  { code: 'ja', label: 'Japanese' },
  { code: 'ko', label: 'Korean' },
  { code: 'ar', label: 'Arabic' },
  { code: 'hi', label: 'Hindi' },
  { code: 'tr', label: 'Turkish' },
  { code: 'sv', label: 'Swedish' },
  { code: 'da', label: 'Danish' },
  { code: 'no', label: 'Norwegian' },
  { code: 'fi', label: 'Finnish' },
  { code: 'cs', label: 'Czech' },
  { code: 'uk', label: 'Ukrainian' },
  { code: 'ro', label: 'Romanian' },
  { code: 'hu', label: 'Hungarian' },
  { code: 'id', label: 'Indonesian' },
  { code: 'th', label: 'Thai' },
  { code: 'vi', label: 'Vietnamese' },
]

export function TranscriptionTab(): React.JSX.Element {
  const prefs = getPreferences()
  const [languageMode, setLanguageMode] = useState<'auto' | 'single'>(
    prefs.language && prefs.language !== 'auto' ? 'single' : 'auto'
  )
  const [language, setLanguage] = useState(prefs.language ?? 'en')
  const [vadEnabled, setVadEnabled] = useState(prefs.vadEnabled ?? true)

  const applyLanguageMode = (mode: 'auto' | 'single'): void => {
    setLanguageMode(mode)
    if (mode === 'auto') {
      setPreferences({ language: 'auto' })
    } else {
      setPreferences({ language: language !== 'auto' ? language : 'en' })
    }
  }

  const applyLanguage = (code: string): void => {
    setLanguage(code)
    setPreferences({ language: code })
  }

  return (
    <>
      <SettingRow
        icon={Languages}
        title="Language mode"
        subtitle="Auto-detect identifies the spoken language per audio segment. Single language mode is more accurate when you always speak one language."
        keywords="language auto detect single transcription speech"
      >
        <div className="mt-3 flex gap-2">
          {(['auto', 'single'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => applyLanguageMode(mode)}
              className={[
                'flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors',
                languageMode === mode
                  ? 'bg-[color:var(--accent)] text-white'
                  : 'bg-white/[0.06] text-text-tertiary hover:bg-white/10 hover:text-text-secondary'
              ].join(' ')}
            >
              {mode === 'auto' ? '🌐 Auto-Detect' : '🎯 Single Language'}
            </button>
          ))}
        </div>
        {languageMode === 'single' && (
          <div className="mt-3">
            <select
              value={language}
              onChange={(e) => applyLanguage(e.target.value)}
              className="rounded-md bg-white/10 px-3 py-1.5 text-sm text-white focus:outline-none"
            >
              {SUPPORTED_LANGUAGES.map((l) => (
                <option key={l.code} value={l.code} className="bg-neutral-900">
                  {l.label}
                </option>
              ))}
            </select>
          </div>
        )}
      </SettingRow>

      <SettingRow
        icon={Mic2}
        title="Voice activity detection"
        subtitle="Skip silence to reduce transcription cost and latency. Powered by Deepgram's VAD gate — only sends audio when speech is detected."
        keywords="vad voice activity detection silence skip deepgram"
        dot={vadEnabled ? 'on' : 'off'}
        control={
          <Toggle
            on={vadEnabled}
            onChange={(on) => {
              setVadEnabled(on)
              setPreferences({ vadEnabled: on })
            }}
            label="Voice activity detection"
          />
        }
      />

      <SettingRow
        icon={Filter}
        title="Custom vocabulary"
        subtitle="Add domain-specific terms, names, or technical jargon to improve recognition accuracy. Omi learns to recognize your specific vocabulary."
        keywords="vocabulary custom terms names brands accuracy recognition"
      >
        <div className="mt-3 rounded-xl bg-white/[0.04] px-4 py-4 text-sm text-text-tertiary">
          <p className="mb-2 font-medium text-text-secondary">How it works</p>
          <ul className="space-y-1 text-xs leading-relaxed">
            <li>• Omi automatically learns from your conversations over time</li>
            <li>• Technical terms, project names, and people mentioned frequently are picked up</li>
            <li>• The more you use Omi, the more accurate transcription becomes</li>
          </ul>
        </div>
      </SettingRow>
    </>
  )
}
