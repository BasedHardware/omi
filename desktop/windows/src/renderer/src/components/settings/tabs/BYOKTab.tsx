import { useState } from 'react'
import { Key, Eye, EyeOff, CheckCircle2, Loader2 } from 'lucide-react'
import { omiApi } from '../../../lib/apiClient'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { toast } from '../../../lib/toast'
import { SettingRow } from '../SettingRow'

async function sha256Hex(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
}

type BYOKKeys = { openai: string; anthropic: string; gemini: string; deepgram: string }

const PROVIDERS: { key: keyof BYOKKeys; label: string; placeholder: string }[] = [
  { key: 'openai', label: 'OpenAI', placeholder: 'sk-...' },
  { key: 'anthropic', label: 'Anthropic', placeholder: 'sk-ant-...' },
  { key: 'gemini', label: 'Gemini', placeholder: 'AIza...' },
  { key: 'deepgram', label: 'Deepgram', placeholder: 'your-deepgram-api-key' }
]

export function BYOKTab(): React.JSX.Element {
  const saved = getPreferences().byokKeys ?? {}
  const [keys, setKeys] = useState<BYOKKeys>({
    openai: saved.openai ?? '',
    anthropic: saved.anthropic ?? '',
    gemini: saved.gemini ?? '',
    deepgram: saved.deepgram ?? ''
  })
  const [show, setShow] = useState<Record<string, boolean>>({})
  const [activating, setActivating] = useState(false)
  const [clearing, setClearing] = useState(false)

  const allFilled = Boolean(keys.openai && keys.anthropic && keys.gemini && keys.deepgram)
  const currentlyActive = Boolean(saved.openai && saved.anthropic && saved.gemini && saved.deepgram)

  const activate = async (): Promise<void> => {
    if (!allFilled || activating) return
    setActivating(true)
    try {
      const fingerprints: Record<string, string> = {}
      for (const [provider, key] of Object.entries(keys)) {
        if (key) fingerprints[provider] = await sha256Hex(key)
      }
      await omiApi.post('/v1/users/me/byok-active', { fingerprints })
      setPreferences({ byokKeys: { ...keys } })
      toast('BYOK activated', {
        tone: 'success',
        body: 'Your keys will be attached to every Omi request.'
      })
    } catch (e) {
      toast('Activation failed', { tone: 'error', body: (e as Error).message })
    } finally {
      setActivating(false)
    }
  }

  const clear = async (): Promise<void> => {
    if (clearing) return
    setClearing(true)
    try {
      await omiApi.delete('/v1/users/me/byok-active')
      setPreferences({ byokKeys: {} })
      setKeys({ openai: '', anthropic: '', gemini: '', deepgram: '' })
      toast('BYOK deactivated', { tone: 'info' })
    } catch (e) {
      toast('Could not deactivate', { tone: 'error', body: (e as Error).message })
    } finally {
      setClearing(false)
    }
  }

  return (
    <SettingRow
      icon={Key}
      title="Bring Your Own Keys (BYOK)"
      subtitle="Use your own API keys for the free Omi plan. All four providers are required. Keys are stored locally and sent as request headers — only SHA-256 fingerprints reach the Omi server."
      keywords="byok bring own key openai anthropic gemini deepgram api keys free plan subscription"
    >
      <div className="space-y-3">
        {currentlyActive && (
          <div className="flex items-center gap-2 rounded-lg border border-emerald-400/30 bg-emerald-400/8 px-3 py-2">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-300" />
            <span className="text-sm text-emerald-200">BYOK active — your keys are in use</span>
          </div>
        )}
        {PROVIDERS.map(({ key, label, placeholder }) => (
          <div key={key} className="flex flex-col gap-1">
            <label className="text-xs text-text-tertiary">{label}</label>
            <div className="relative">
              <input
                type={show[key] ? 'text' : 'password'}
                value={keys[key]}
                onChange={(e) => setKeys((k) => ({ ...k, [key]: e.target.value }))}
                placeholder={placeholder}
                className="input-field w-full pr-10 font-mono text-sm"
                autoComplete="off"
              />
              <button
                type="button"
                onClick={() => setShow((s) => ({ ...s, [key]: !s[key] }))}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-white/40 hover:text-white/80"
                tabIndex={-1}
              >
                {show[key] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
        ))}
        <div className="flex items-center gap-2 pt-1">
          <button
            onClick={() => void activate()}
            disabled={!allFilled || activating}
            className="btn-primary flex items-center gap-1.5 px-4 py-2 disabled:opacity-40"
          >
            {activating && <Loader2 className="h-4 w-4 animate-spin" />}
            {activating ? 'Activating…' : 'Save & Activate'}
          </button>
          {currentlyActive && (
            <button
              onClick={() => void clear()}
              disabled={clearing}
              className="btn-ghost px-3 py-2 disabled:opacity-40"
            >
              {clearing ? 'Clearing…' : 'Deactivate'}
            </button>
          )}
        </div>
        <p className="text-xs text-text-quaternary">
          All four providers are required. Actual keys never leave your device — only fingerprints are sent to Omi for verification.
        </p>
      </div>
    </SettingRow>
  )
}
