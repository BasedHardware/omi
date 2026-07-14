// Auto realtime-model selection ("Auto") — Windows port of macOS
// AutoModelSelector.swift + RealtimeOmniSettings.effectiveProvider.
//
// When the user leaves the voice provider on "Auto" (the default), we connect
// with the realtime provider whose underlying model currently scores best on a
// quality/speed formula, refreshed once a day from the omi backend
// (GET /v1/auto/model-pick, which runs the Artificial Analysis scoring
// server-side so the AA key stays off the client). It degrades gracefully: no
// network / junk shape / unknown provider → keep the last good pick, or fall
// back to Gemini (cheapest + fastest) only when we have never had a pick. This
// mirrors AutoModelSelector.swift 1:1 (localStorage here ≈ UserDefaults there).

import { omiApi } from '../apiClient'
import { getPreferences } from '../preferences'
import type { VoiceProvider } from './sessionMachine'

// Backend provider ids — the PROXY keys in routers/auto_model.py, identical to
// Mac's RealtimeOmniProvider rawValues. The pick is ALWAYS one of these two
// concrete ids, never "auto".
export type AutoModelProviderId = 'geminiFlashLive' | 'gptRealtime2'

// Mirror Mac's UserDefaults keys so behavior is identical across platforms.
const PICK_KEY = 'realtimeOmniAutoPick'
const PICK_DATE_KEY = 'realtimeOmniAutoPickDate'
const REFRESH_INTERVAL_MS = 24 * 60 * 60 * 1000 // 24h, matches the backend cache TTL
const REQUEST_TIMEOUT_MS = 15_000 // mirror Mac's 15s request timeout

// geminiFlashLive → 'gemini', gptRealtime2 → 'openai' — the same mapping macOS
// RealtimeHubSettings.provider applies to RealtimeOmniProvider.
export function mapProviderIdToVoiceProvider(id: AutoModelProviderId): VoiceProvider {
  return id === 'gptRealtime2' ? 'openai' : 'gemini'
}

function isProviderId(raw: unknown): raw is AutoModelProviderId {
  return raw === 'geminiFlashLive' || raw === 'gptRealtime2'
}

// localStorage may be unavailable (non-renderer import context) or throw
// (quota / privacy mode). Fail soft in every path — a missed cache read just
// means we treat it as "no pick" and refetch.
function readLocal(key: string): string | null {
  try {
    if (typeof localStorage === 'undefined') return null
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

/** The current cached pick, or null if never set / unknown (defensive against an
 *  old build's stale value), mirroring AutoModelSelector.currentPick. */
export function currentPick(): AutoModelProviderId | null {
  const raw = readLocal(PICK_KEY)
  return isProviderId(raw) ? raw : null
}

function lastRefresh(): number | null {
  const raw = readLocal(PICK_DATE_KEY)
  if (raw === null) return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

function store(id: AutoModelProviderId): void {
  try {
    if (typeof localStorage === 'undefined') return
    localStorage.setItem(PICK_KEY, id)
    localStorage.setItem(PICK_DATE_KEY, String(Date.now()))
  } catch {
    /* quota / privacy mode — a failed cache write just means we refetch next time */
  }
}

/** Call at launch and at session start. No-op (fires no request) when a fresh
 *  pick already exists — age < 24h AND a valid cached pick. Fire-and-forget,
 *  never awaited: effectiveProvider resolves synchronously from the cache. */
export function refreshIfStale(): void {
  const last = lastRefresh()
  if (last !== null && Date.now() - last < REFRESH_INTERVAL_MS && currentPick() !== null) return
  void refresh()
}

/** Read the daily pick from the omi backend (Firebase-authed via omiApi, which
 *  attaches the bearer token + platform headers). On any non-2xx / parse miss /
 *  unknown provider / network error, keep the last good pick; only write the
 *  Gemini default when we have never had a pick — never clobber a good cache with
 *  a transient failure. */
export async function refresh(): Promise<void> {
  try {
    const res = await omiApi.get<{ provider?: unknown }>('/v1/auto/model-pick', {
      timeout: REQUEST_TIMEOUT_MS
    })
    const raw = res.data?.provider
    if (isProviderId(raw)) {
      store(raw)
    } else if (currentPick() === null) {
      store('geminiFlashLive')
    }
  } catch {
    if (currentPick() === null) store('geminiFlashLive')
  }
}

/** The concrete provider to actually connect with right now — mirrors macOS
 *  RealtimeOmniSettings.effectiveProvider. A concrete setting ('openai'/'gemini')
 *  returns itself, bypassing the selector; 'auto' (the default) resolves via the
 *  cached daily pick, falling back to Gemini when no pick exists. Always returns a
 *  concrete VoiceProvider — never 'auto'. */
export function resolveEffectiveVoiceProvider(): VoiceProvider {
  const setting = getPreferences().voiceProvider ?? 'auto'
  if (setting !== 'auto') return setting
  const pick = currentPick()
  return pick ? mapProviderIdToVoiceProvider(pick) : 'gemini'
}
