// Ephemeral realtime-token mint against the desktop Rust backend (Phase 6).
// Contract verified live 2026-07-10 against /v2/realtime/session:
//   POST { provider: 'openai' | 'gemini' }  (Firebase Bearer auth; plain token,
//   no platform requirements — works for the Windows client as-is)
//   → 200 { provider, token, expires_at? }
//       openai: token 'ek_…'          (Bearer / client secret for WebRTC)
//       gemini: token 'auth_tokens/…' (used as the SDK apiKey, v1alpha)
//   → 4xx/5xx { error, reason, retryable, provider?, code?, upstream_status_code? }
//   → 402 trial_expired / 403 byok mismatch from the auth extractor.
// The server locks the model at mint (gpt-realtime-2 / gemini-3.1-flash-live);
// clients configure everything else on connect.

import type { AxiosRequestConfig } from 'axios'
import { desktopApi } from '../apiClient'
import type { VoiceProvider } from './sessionMachine'

// The mint can run during eager warm (before any PTT press), so a dead-session 401
// must reject quietly and NOT yank the user to the sign-in screen — same
// `__sessionPreserving` knob autoModelSelector's background poll uses (apiClient
// responseErrorHandler still refreshes + retries once, but never forces reauth on
// death). Without it, warming the hub with a stale token routes the user to Login.
const MINT_CONFIG = { __sessionPreserving: true } as AxiosRequestConfig

// Server-locked models (mirror Backend-Rust routes/realtime.rs constants).
export const OPENAI_REALTIME_MODEL = 'gpt-realtime-2'
export const GEMINI_LIVE_MODEL = 'models/gemini-3.1-flash-live-preview'

export type MintedToken = {
  provider: VoiceProvider
  token: string
  expiresAt?: string
}

export type MintFailure = {
  /** Human-readable message for the error surface. */
  message: string
  /** Whether "try again" is worth offering. */
  retryable: boolean
  /** Whether the OTHER provider is worth attempting (this one is down/unconfigured). */
  tryOtherProvider: boolean
}

/** Pure classification of a mint failure from HTTP status + parsed body. */
export function classifyMintFailure(
  status: number | undefined,
  body: Record<string, unknown> | undefined
): MintFailure {
  const reason = typeof body?.reason === 'string' ? body.reason : undefined
  const error = typeof body?.error === 'string' ? body.error : undefined
  if (status === 401) {
    return { message: 'sign in to use voice', retryable: false, tryOtherProvider: false }
  }
  if (status === 402 || error === 'trial_expired' || /trial expired/i.test(error ?? '')) {
    return {
      message: 'Omi trial expired — upgrade to use realtime voice',
      retryable: false,
      tryOtherProvider: false
    }
  }
  if (status === 403) {
    return { message: error || 'voice access denied', retryable: false, tryOtherProvider: false }
  }
  // Provider-scoped failures (unconfigured / quota / provider outage): the other
  // lane may be healthy — fall back rather than erroring the session.
  const providerScoped =
    reason === 'provider_not_configured' ||
    reason === 'provider_quota_exceeded' ||
    reason === 'provider_auth_failed' ||
    reason === 'provider_mint_unavailable' ||
    reason === 'provider_mint_rejected' ||
    reason === 'provider_mint_transport_error'
  const retryable = body?.retryable === true || status === undefined || status >= 500
  return {
    message: error || `voice session mint failed${status ? ` (${status})` : ''}`,
    retryable,
    tryOtherProvider: providerScoped
  }
}

function isAxiosLikeError(
  e: unknown
): e is { response?: { status?: number; data?: Record<string, unknown> } } {
  return typeof e === 'object' && e !== null && 'response' in e
}

/** Mint one ephemeral token. Throws MintError (carries the classification). */
export class MintError extends Error {
  constructor(public readonly failure: MintFailure) {
    super(failure.message)
    this.name = 'MintError'
  }
}

export async function mintRealtimeToken(provider: VoiceProvider): Promise<MintedToken> {
  try {
    const res = await desktopApi.post<{ provider: string; token: string; expires_at?: string }>(
      '/v2/realtime/session',
      { provider },
      MINT_CONFIG
    )
    const token = res.data?.token
    if (typeof token !== 'string' || token.length === 0) {
      throw new MintError({
        message: 'voice session mint returned no token',
        retryable: true,
        tryOtherProvider: true
      })
    }
    return { provider, token, expiresAt: res.data.expires_at }
  } catch (e) {
    if (e instanceof MintError) throw e
    const resp = isAxiosLikeError(e) ? e.response : undefined
    throw new MintError(classifyMintFailure(resp?.status, resp?.data))
  }
}
