/**
 * Proactive lane client — Windows port of macOS ProactiveLaneClient: the
 * transport to the desktop backend's proactivity facade
 * (`POST {desktopApiBase}/v1/desktop/proactivity/completions`).
 *
 * The facade owns model routing (proactive_reasoning -> the reasoning lane,
 * proactive_extraction -> the extraction lane), strict json_schema validation,
 * per-uid daily quotas, and explicit prompt caching (breakpoint after the
 * first text part, 30m TTL). No temperature is ever sent.
 *
 * Client-side 429 discipline mirrors mac: a per-operation cooldown armed from
 * Retry-After (default 600s, clamped [60s, 3600s], longer existing cooldown
 * kept), throwing before any network call while cooling; cleared on session
 * reset.
 */

export type ProactiveOperation = 'proactive_extraction' | 'proactive_reasoning'

export interface LaneRequest {
  operation: ProactiveOperation
  prompt: string
  uncachedPrompt?: string
  imageBase64Jpeg?: string
  jsonSchema: Record<string, unknown>
  cacheKey?: string
  maxCompletionTokens: number
}

export interface LaneResult {
  content: string
  providerModel: string
  cachedTokens: number
  cacheWriteTokens: number
  cacheWrite: boolean
  fallbackClass: string
}

export type LaneFailureKind =
  | 'http_error'
  | 'quota_cooldown'
  | 'invalid_response'
  | 'decode'
  | 'network'

export class LaneError extends Error {
  readonly kind: LaneFailureKind
  readonly status?: number

  constructor(kind: LaneFailureKind, message: string, status?: number) {
    super(message)
    this.kind = kind
    this.status = status
  }

  /** Bounded failure-classification object for delivery-row provenance. */
  provenance(): Record<string, unknown> {
    const out: Record<string, unknown> = { failure: this.kind }
    if (this.status !== undefined) out.status = this.status
    return out
  }
}

export const LANE_TIMEOUT_MS = 90_000
export const QUOTA_COOLDOWN_DEFAULT_MS = 600_000
export const QUOTA_COOLDOWN_MIN_MS = 60_000
export const QUOTA_COOLDOWN_MAX_MS = 3_600_000

export interface LaneClientDeps {
  fetchImpl: (url: string, init: RequestInit) => Promise<Response>
  getSession: () => { desktopApiBase: string; token: string } | null
  /** Pre-call token freshness hook (wire to session.pullFreshSession when the
   *  cached token is near expiry) so a throttled hidden renderer cannot leave
   *  the lane sending dead tokens. Best-effort: failures fall through. */
  ensureFreshSession?: () => Promise<void>
  getAbortSignal?: () => AbortSignal | undefined
  now?: () => number
}

export interface LaneClient {
  complete(request: LaneRequest): Promise<LaneResult>
  cooldownRemainingMs(operation: ProactiveOperation): number
  reset(): void
}

export function createLaneClient(deps: LaneClientDeps): LaneClient {
  const now = deps.now ?? (() => Date.now())
  const cooldownUntil = new Map<ProactiveOperation, number>()

  function armCooldown(operation: ProactiveOperation, retryAfterHeader: string | null): void {
    const parsed = retryAfterHeader === null ? NaN : Number.parseInt(retryAfterHeader, 10)
    const requested = Number.isFinite(parsed) ? parsed * 1000 : QUOTA_COOLDOWN_DEFAULT_MS
    const clamped = Math.min(QUOTA_COOLDOWN_MAX_MS, Math.max(QUOTA_COOLDOWN_MIN_MS, requested))
    const until = now() + clamped
    const existing = cooldownUntil.get(operation) ?? 0
    if (until > existing) cooldownUntil.set(operation, until)
  }

  async function complete(request: LaneRequest): Promise<LaneResult> {
    const cooling = cooldownUntil.get(request.operation) ?? 0
    if (cooling > now()) throw new LaneError('quota_cooldown', 'operation cooling down after 429')

    try {
      await deps.ensureFreshSession?.()
    } catch {
      // Freshness is best-effort; the request may still succeed or 401.
    }
    const session = deps.getSession()
    if (!session) throw new LaneError('network', 'no backend session')

    const content: Array<Record<string, unknown>> = [{ type: 'text', text: request.prompt }]
    if (request.uncachedPrompt !== undefined && request.uncachedPrompt.length > 0) {
      content.push({ type: 'text', text: request.uncachedPrompt })
    }
    if (request.imageBase64Jpeg !== undefined) {
      content.push({
        type: 'image_url',
        image_url: { url: `data:image/jpeg;base64,${request.imageBase64Jpeg}` }
      })
    }

    const body: Record<string, unknown> = {
      operation: request.operation,
      messages: [{ role: 'user', content }],
      response_format: {
        type: 'json_schema',
        json_schema: { name: 'desktop_proactivity', strict: true, schema: request.jsonSchema }
      },
      max_completion_tokens: request.maxCompletionTokens
    }
    if (request.cacheKey !== undefined) body.cache_key = request.cacheKey

    const timeout = AbortSignal.timeout(LANE_TIMEOUT_MS)
    const sessionSignal = deps.getAbortSignal?.()
    const signal = sessionSignal ? AbortSignal.any([timeout, sessionSignal]) : timeout

    let response: Response
    try {
      response = await deps.fetchImpl(
        `${session.desktopApiBase.replace(/\/+$/, '')}/v1/desktop/proactivity/completions`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${session.token}`
          },
          body: JSON.stringify(body),
          signal
        }
      )
    } catch (err) {
      throw new LaneError('network', err instanceof Error ? err.message : 'fetch failed')
    }

    if (response.status === 429) {
      armCooldown(request.operation, response.headers.get('Retry-After'))
      throw new LaneError('quota_cooldown', 'lane returned 429', 429)
    }
    if (!response.ok) {
      throw new LaneError('http_error', `lane returned ${response.status}`, response.status)
    }

    let envelope: unknown
    try {
      envelope = await response.json()
    } catch {
      throw new LaneError('decode', 'lane response was not JSON')
    }
    const parsed = parseEnvelope(envelope)
    if (parsed === null)
      throw new LaneError('invalid_response', 'lane envelope missing required fields')
    return parsed
  }

  return {
    complete,
    cooldownRemainingMs(operation) {
      return Math.max(0, (cooldownUntil.get(operation) ?? 0) - now())
    },
    reset() {
      cooldownUntil.clear()
    }
  }
}

function parseEnvelope(envelope: unknown): LaneResult | null {
  if (typeof envelope !== 'object' || envelope === null) return null
  const raw = envelope as Record<string, unknown>
  if (typeof raw.operation !== 'string' || typeof raw.lane !== 'string') return null
  if (typeof raw.provider_model !== 'string') return null
  const usage = raw.usage
  if (typeof usage !== 'object' || usage === null) return null
  const usageRaw = usage as Record<string, unknown>
  if (typeof usageRaw.cached_tokens !== 'number' || typeof usageRaw.cache_write_tokens !== 'number')
    return null
  const responseField = raw.response
  if (typeof responseField !== 'object' || responseField === null) return null
  const choices = (responseField as Record<string, unknown>).choices
  if (!Array.isArray(choices) || choices.length === 0) return null
  const first = choices[0]
  if (typeof first !== 'object' || first === null) return null
  const message = (first as Record<string, unknown>).message
  if (typeof message !== 'object' || message === null) return null
  const messageContent = (message as Record<string, unknown>).content
  if (typeof messageContent !== 'string') return null
  return {
    content: messageContent,
    providerModel: raw.provider_model,
    cachedTokens: usageRaw.cached_tokens,
    cacheWriteTokens: usageRaw.cache_write_tokens,
    cacheWrite: raw.cache_write === true,
    fallbackClass: typeof raw.fallback_class === 'string' ? raw.fallback_class : ''
  }
}
