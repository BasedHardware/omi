// Settings → Advanced → "Developer API Keys" subsection: bring-your-own-key
// (BYOK). Provide all four provider keys and Omi runs entirely on them — the
// "free forever" plan — with no Omi subscription charge. Ported from the macOS
// DeveloperKeys section (SettingsContentView+DeveloperKeys.swift): same
// all-or-nothing model, same copy, same up-front live validation before the
// backend is ever flipped on.
//
// Keys are encrypted at rest in the main process (ByokKeyStore, DPAPI). This UI
// never persists or logs raw keys; enrollment sends only SHA-256 fingerprints.

import { useEffect, useRef, useState } from 'react'
import { KeyRound, ShieldCheck, AlertTriangle, Eye, EyeOff, Loader2 } from 'lucide-react'
import { SettingRow } from '../SettingRow'
import { auth } from '../../../lib/firebase'
import { dismissUsageLimit } from '../../../lib/usageLimit'
import { fetchSubscription, fetchChatQuota } from '../../../lib/billing'
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

// Mac fires refreshBYOKActivation on every keystroke; we debounce so a paste or
// fast typing doesn't storm the provider endpoints or POST/DELETE repeatedly.
const COMMIT_DEBOUNCE_MS = 600

export function DeveloperKeysSection(): React.JSX.Element {
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

  // Latest keys for the debounced commit (avoids a stale closure), plus the
  // pending timer so rapid edits collapse into one validate/enroll.
  const keysRef = useRef<Record<ByokProvider, string>>(emptyKeys())
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Load stored keys once on mount so the fields reflect what's saved. We do NOT
  // validate on open (no network on open) — the banner reflects presence only;
  // badges populate after a change triggers enrollment (Mac parity).
  useEffect(() => {
    void window.omi.byokGetAll().then((stored) => {
      const merged = { ...emptyKeys(), ...stored }
      keysRef.current = merged
      setKeys(merged)
    })
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  const hasAll = BYOK_PROVIDERS.every((p) => keys[p].trim().length > 0)
  const hasAnyKey = BYOK_PROVIDERS.some((p) => keys[p].trim().length > 0)

  // Persist the current key set, then reconcile backend activation. Runs
  // debounced after edits (not per keystroke).
  const commit = async (): Promise<void> => {
    const cur = keysRef.current
    await Promise.all(BYOK_PROVIDERS.map((p) => window.omi.byokSet(p, cur[p].trim())))
    // Live-validate only when the full set is present (matches the enroll IPC's
    // own gate); a partial set just deactivates with no per-provider network.
    const willValidate = BYOK_PROVIDERS.every((p) => cur[p].trim().length > 0)
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
      // Mac parity: on activation, refresh plan/quota and clear any sticky
      // paywall so a user who just hit their limit isn't left blocked.
      dismissUsageLimit()
      void fetchSubscription().catch(() => {})
      void fetchChatQuota().catch(() => {})
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

  const scheduleCommit = (): void => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => void commit(), COMMIT_DEBOUNCE_MS)
  }

  const onFieldChange = (provider: ByokProvider, value: string): void => {
    keysRef.current = { ...keysRef.current, [provider]: value }
    setKeys((k) => ({ ...k, [provider]: value }))
    scheduleCommit()
  }

  const clearAll = async (): Promise<void> => {
    if (timerRef.current) clearTimeout(timerRef.current)
    keysRef.current = emptyKeys()
    setKeys(emptyKeys())
    setStatuses({})
    setActivationError(null)
    setChecking(false)
    await window.omi.byokClearAll()
    const token = await auth.currentUser?.getIdToken().catch(() => undefined)
    if (token) await window.omi.byokEnroll(token) // deactivates (empty set)
  }

  return (
    <div>
      {/* Subsection header — Mac's "Developer API Keys" (key icon). */}
      <div className="mb-4 mt-2 flex items-center gap-2 border-t border-white/[0.06] pt-6">
        <KeyRound className="h-4 w-4 text-white/45" strokeWidth={1.9} />
        <h3 className="text-sm font-semibold uppercase tracking-wide text-text-tertiary">
          Developer API Keys
        </h3>
      </div>

      {/* Status banner — verbatim macOS copy, "this Mac" adapted to "this PC". */}
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
              ? "You're paying your own providers. Omi skips the subscription charge. Keys stay on this PC."
              : 'Provide all four keys (OpenAI, Anthropic, Gemini, Deepgram) to switch to the free plan. Keys stay on this PC — we never store them on our servers.'}
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
            keywords={`${id} ${displayName} api key byok developer bring your own key`}
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
                onChange={(e) => onFieldChange(id, e.target.value)}
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
