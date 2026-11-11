// Client-reported realtime usage → POST /v2/realtime/usage (Phase 6).
// The realtime WS is client↔provider direct, so the backend never sees usage
// inline; managed (ephemeral-token) sessions report the provider's own token
// counts so spend lands in the llm_usage ledger. Mapping is pure and tested;
// posting is best-effort (a lost report must never break the session UX).

import { desktopApi } from '../apiClient'
import type { VoiceProvider } from './sessionMachine'

export type RealtimeUsageBody = {
  provider: VoiceProvider
  model: string
  input_text_tokens: number
  input_audio_tokens: number
  input_cached_tokens: number
  output_text_tokens: number
  output_audio_tokens: number
}

function num(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) && v > 0 ? Math.round(v) : 0
}

/** OpenAI agents-SDK cumulative Usage → report body. Details arrive as arrays of
 *  raw provider objects ({ text_tokens, audio_tokens, cached_tokens, … }); sum
 *  tolerantly and derive text = total − audio (never negative). */
export function mapOpenAiUsage(
  usage: {
    inputTokens?: number
    outputTokens?: number
    inputTokensDetails?: Array<Record<string, number>>
    outputTokensDetails?: Array<Record<string, number>>
  },
  model: string
): RealtimeUsageBody {
  const sum = (details: Array<Record<string, number>> | undefined, key: string): number =>
    (details ?? []).reduce((n, d) => n + num(d?.[key]), 0)
  const inTotal = num(usage.inputTokens)
  const outTotal = num(usage.outputTokens)
  const inAudio = Math.min(sum(usage.inputTokensDetails, 'audio_tokens'), inTotal)
  const outAudio = Math.min(sum(usage.outputTokensDetails, 'audio_tokens'), outTotal)
  const cached = sum(usage.inputTokensDetails, 'cached_tokens')
  return {
    provider: 'openai',
    model,
    input_text_tokens: Math.max(0, inTotal - inAudio),
    input_audio_tokens: inAudio,
    input_cached_tokens: cached,
    output_text_tokens: Math.max(0, outTotal - outAudio),
    output_audio_tokens: outAudio
  }
}

/** Gemini per-message usageMetadata → report body. Modality breakdowns arrive as
 *  [{ modality: 'AUDIO' | 'TEXT', tokenCount }]. */
export function mapGeminiUsage(
  meta: {
    promptTokenCount?: number
    responseTokenCount?: number
    cachedContentTokenCount?: number
    promptTokensDetails?: Array<{ modality?: string; tokenCount?: number }>
    responseTokensDetails?: Array<{ modality?: string; tokenCount?: number }>
  },
  model: string
): RealtimeUsageBody {
  const byModality = (
    details: Array<{ modality?: string; tokenCount?: number }> | undefined,
    modality: string
  ): number =>
    (details ?? [])
      .filter((d) => (d?.modality ?? '').toUpperCase() === modality)
      .reduce((n, d) => n + num(d?.tokenCount), 0)
  const inTotal = num(meta.promptTokenCount)
  const outTotal = num(meta.responseTokenCount)
  const inAudio = Math.min(byModality(meta.promptTokensDetails, 'AUDIO'), inTotal)
  const outAudio = Math.min(byModality(meta.responseTokensDetails, 'AUDIO'), outTotal)
  return {
    provider: 'gemini',
    model,
    input_text_tokens: Math.max(0, inTotal - inAudio),
    input_audio_tokens: inAudio,
    input_cached_tokens: num(meta.cachedContentTokenCount),
    output_text_tokens: Math.max(0, outTotal - outAudio),
    output_audio_tokens: outAudio
  }
}

/** Difference of two cumulative reports (a − b, floored at 0 per field) — used
 *  to turn OpenAI's cumulative session usage into per-report deltas. */
export function usageDelta(a: RealtimeUsageBody, b: RealtimeUsageBody | null): RealtimeUsageBody {
  if (!b) return a
  const d = (x: number, y: number): number => Math.max(0, x - y)
  return {
    provider: a.provider,
    model: a.model,
    input_text_tokens: d(a.input_text_tokens, b.input_text_tokens),
    input_audio_tokens: d(a.input_audio_tokens, b.input_audio_tokens),
    input_cached_tokens: d(a.input_cached_tokens, b.input_cached_tokens),
    output_text_tokens: d(a.output_text_tokens, b.output_text_tokens),
    output_audio_tokens: d(a.output_audio_tokens, b.output_audio_tokens)
  }
}

export function usageTotal(u: RealtimeUsageBody): number {
  return (
    u.input_text_tokens +
    u.input_audio_tokens +
    u.input_cached_tokens +
    u.output_text_tokens +
    u.output_audio_tokens
  )
}

/** Fire-and-forget report. Zero-token bodies are skipped client-side. */
export async function reportRealtimeUsage(body: RealtimeUsageBody): Promise<void> {
  if (usageTotal(body) <= 0) return
  try {
    await desktopApi.post('/v2/realtime/usage', body)
  } catch (e) {
    console.warn('[voice] usage report failed (non-fatal):', (e as Error)?.message)
  }
}
