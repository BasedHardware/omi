// Settings → Developer Keys: bring-your-own-key (BYOK). Provide all four
// provider keys and Omi runs entirely on them — the "free forever" plan — with
// no Omi subscription charge. Ported from the macOS DeveloperKeys section
// (SettingsContentView+DeveloperKeys.swift): same all-or-nothing model, same
// copy, same up-front live validation before the backend is ever flipped on.
//
// Keys are encrypted at rest in the main process (ByokKeyStore, DPAPI). This UI
// never persists or logs raw keys; enrollment sends only SHA-256 fingerprints.

import { useEffect, useState } from 'react'
import { KeyRound, ShieldCheck, AlertTriangle, Eye, EyeOff, Loader2 } from 'lucide-react'
import { SettingRow } from '../SettingRow'
import { useSearchableRow } from '../searchContext'
import { auth } from '../../../lib/firebase'
import {
  BYOK_PROVIDERS,
  type ByokProvider,
  type ByokValidationResults
} from '../../../../../shared/byok'

/** Field metadata per provider — titles/subtitles verbatim from the macOS view. */
const PROVIDERS: { id: ByokProvider; title: string; subtitle: string; displayName: string }[] = [
  { id: 'openai', title: 'OpenAI API Key', subtitle: 'For GPT calls.', displayName: 'OpenAI' },
  { id: 'anthropic', title: 'Anthropic API Key', subtitle: 'For chat (Claude).', displayName: 'Anthropic' },
  {
    id: 'gemini',
    title: 'Gemini API Key',
    subtitle: 'For proactive AI (memory, tasks, insights, focus).',
    displayName: 'Gemini'
  },
  { id: 'deepgram', title: 'Deepgram API Key', subtitle: 'For live transcription.', displayName: 'Deepgram' }
]

const emptyKeys = (): Record<ByokProvider, string> => ({
  openai: '',
  anthropic: '',
  gemini: '',
  deepgram: ''
})

export function DeveloperKeysTab(): React.JSX.Element {
  // Register the whole panel for cross-tab Settings search (the banner/error are
  // not SettingRows; each provider row also self-registers via SettingRow).
  useSearchableRow(
    'developer keys byok bring your own key api openai anthropic gemini deepgram free plan'
  )

  const [keys, setKeys] = useState<Record<ByokProvider, string>>(emptyKeys)
  const [statuses, setStatuses] = useState<ByokValidationResults>({})
  const [checking, setChecking] = useState(false)
  const [activationError, setActivationError] = useState<string | null>(null)
  const [reveal, setReveal] = useState<Record<ByokProvider, boolean>>({
    openai: false,
    anthropic: false,
    gemini: false,
    deepgram: false
  })

  // Load stored keys once on mount so the fields reflect what's saved. We do NOT
  // validate on open (no network on open) — the banner reflects presence only;
  // badges populate after a change triggers enrollment (Mac parity).
  useEffect(() => {
    void window.omi.byokGetAll().then((stored) => {
      setKeys({ ...emptyKeys(), ...stored })
    })
  }, [])

  const hasAll = BYOK_PROVIDERS.every((p) => keys[p].trim().length > 0)

  // Persist the changed key, then reconcile backend activation. Runs on blur
  // (not per keystroke) so a half-typed/pasted key doesn't storm the providers.
  const commit = async (provider: ByokProvider, raw: string): Promise<void> => {
    const value = raw.trim()
    await window.omi.byokSet(provider, value)
    const next = { ...keys, [provider]: value }
    // Live-validate only when the full set is present (matches the enroll IPC's
    // own gate); a partial set just deactivates with no network per provider.
    const willValidate = BYOK_PROVIDERS.every((p) => next[p].trim().length > 0)
    setChecking(willValidate)
    setActivationError(null)
    const token = await auth.currentUser?.getIdToken().catch(() => undefined)
    if (!token) {
      // Not signed in — keys are saved; enrollment happens once authenticated.
      setChecking(false)
      return
    }
    const result = await window.omi.byokEnroll(token)
    setChecking(false)
    setStatuses(result.results)
    if (result.active) {
      setActivationError(null)
    } else if (result.backendError) {
      setActivationError("Couldn't reach Omi to switch on the free plan. Try again.")
    } else if (willValidate) {
      const rejected = PROVIDERS.filter((p) => result.results[p.id] && !result.results[p.id]?.ok)
        .map((p) => p.displayName)
        .sort()
      setActivationError(
        rejected.length
          ? `Rejected by provider: ${rejected.join(', ')}. Free plan stays off until all 4 keys authenticate.`
          : null
      )
    }
  }

  const clearAll = async (): Promise<void> => {
    setKeys(emptyKeys())
    setStatuses({})
    setActivationError(null)
    setChecking(false)
    await window.omi.byokClearAll()
    const token = await auth.currentUser?.getIdToken().catch(() => undefined)
    if (token) await window.omi.byokEnroll(token) // deactivates (empty set)
  }

  const hasAnyKey = BYOK_PROVIDERS.some((p) => keys[p].trim().length > 0)

  return (
    <div>
      {/* Status banner — verbatim macOS copy, "this Mac" adapted to "this device". */}
      <div className="mb-4 flex items-start gap-3 rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
        {hasAll ? (
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" strokeWidth={1.75} />
        ) : (
          <KeyRound className="mt-0.5 h-5 w-5 shrink-0 text-white/55" strokeWidth={1.75} />
        )}
        <div className="min-w-0">
          <div className="text-[15px] font-semibold text-text-primary">
            {hasAll ? 'Free plan active' : 'Use Omi free forever'}
          </div>
          <div className="mt-0.5 text-sm text-text-tertiary">
            {hasAll
              ? "You're paying your own providers. Omi skips the subscription charge. Keys stay on this device."
              : 'Provide all four keys (OpenAI, Anthropic, Gemini, Deepgram) to switch to the free plan. Keys stay on this device — we never store them on our servers.'}
          </div>
        </div>
      </div>

      {activationError && (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-amber-400/25 bg-amber-400/[0.06] px-4 py-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
          <span className="text-sm text-amber-400">{activationError}</span>
        </div>
      )}

      {PROVIDERS.map(({ id, title, subtitle, displayName }) => {
        const status = statuses[id]
        const showChecking = checking && keys[id].trim().length > 0
        const dot = status?.ok ? 'on' : status && !status.ok ? 'warn' : undefined
        return (
          <SettingRow
            key={id}
            title={title}
            subtitle={subtitle}
            keywords={`${id} ${displayName} api key byok`}
            dot={dot}
            control={
              showChecking ? (
                <span className="flex items-center gap-1.5 text-sm text-text-tertiary">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Checking…
                </span>
              ) : status?.ok ? (
                <span className="text-sm font-semibold text-emerald-400">Valid</span>
              ) : status && !status.ok ? (
                <span className="text-sm font-semibold text-amber-400">Invalid</span>
              ) : undefined
            }
          >
            <div className="relative">
              <input
                type={reveal[id] ? 'text' : 'password'}
                value={keys[id]}
                onChange={(e) => setKeys((k) => ({ ...k, [id]: e.target.value }))}
                onBlur={(e) => void commit(id, e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
                }}
                placeholder="Leave blank for default"
                className="glass-subtle w-full rounded-lg px-4 py-3 pr-11 font-mono text-sm text-text-secondary focus:outline-none"
                spellCheck={false}
                autoComplete="off"
              />
              <button
                type="button"
                onClick={() => setReveal((r) => ({ ...r, [id]: !r[id] }))}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-white/45 hover:text-white/75"
                aria-label={reveal[id] ? `Hide ${title}` : `Show ${title}`}
              >
                {reveal[id] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {status && !status.ok && status.detail && (
              <div className="mt-2 text-xs text-amber-400">{status.detail}</div>
            )}
          </SettingRow>
        )
      })}

      {hasAnyKey && (
        <div className="mt-5 flex justify-center">
          <button onClick={() => void clearAll()} className="text-sm font-medium text-red-400 hover:text-red-300">
            Clear All Custom Keys
          </button>
        </div>
      )}
    </div>
  )
}
