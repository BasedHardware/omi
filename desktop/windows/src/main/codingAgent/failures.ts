// Typed adapter failures — Windows port of desktop/macos/agent/src/runtime/failures.ts.
// Adapter stderr is unstructured; sanitizeProcessDiagnostic redacts credentials
// before a diagnostic is ever logged or shown, and classifyAdapterProcessFailure
// is the one sanctioned stderr-sniffing site (known OpenClaw config errors).

import type { CodingAgentAdapterId } from './interface'

export type RuntimeFailureSource = 'adapter_process' | 'adapter_execution' | 'runtime'

export interface RuntimeFailure {
  code: string
  userMessage: string
  technicalMessage?: string
  source?: RuntimeFailureSource
  adapterId?: string
  provider?: string
  retryable?: boolean
}

export class AdapterRuntimeError extends Error {
  readonly failure: RuntimeFailure

  constructor(failure: RuntimeFailure) {
    super(failure.userMessage)
    this.name = 'AdapterRuntimeError'
    this.failure = normalizeRuntimeFailure(failure)
  }
}

export function messageFrom(error: unknown): string {
  if (error instanceof AdapterRuntimeError) {
    return error.failure.userMessage
  }
  const acpDetail = jsonRpcErrorDetail(error)
  if (acpDetail) return acpDetail
  return error instanceof Error ? error.message : String(error)
}

/**
 * Pull a human-meaningful message out of a JSON-RPC error (the ACP bridge's
 * `AcpError`: an Error carrying a numeric `code` and structured `data`). The
 * bridge reports the real cause — e.g. "claude.exe ... failed to launch" or a
 * provider 401 body — in `data`, while `.message` is often just the bare
 * "Internal error" for a -32603. Surfacing only `.message` swallowed the cause,
 * so every packaged spawn failure read as an unactionable "Internal error" in the
 * pill and the logs. This folds the structured detail back into the message so it
 * is always visible and never swallowed.
 *
 * Duck-typed rather than importing `AcpError` from ./acp, which imports this
 * module (would be an import cycle). Returns undefined for anything that is not a
 * JSON-RPC-shaped error, so plain Errors fall through to their `.message`.
 */
export function jsonRpcErrorDetail(error: unknown): string | undefined {
  if (!(error instanceof Error)) return undefined
  const candidate = error as Error & { code?: unknown; data?: unknown }
  if (typeof candidate.code !== 'number') return undefined
  const base = compactWhitespace(candidate.message ?? '')
  const detail = extractStructuredDetail(candidate.data)
  if (!detail) return base || undefined
  // Cap so a huge provider body can't flood a pill; keep the informative head.
  const cappedDetail = detail.length > 300 ? `${detail.slice(0, 300)}…` : detail
  if (!base) return cappedDetail
  // Avoid "Internal error: Internal error ..." when the detail repeats the base.
  return base.toLowerCase().includes(cappedDetail.toLowerCase()) ? base : `${base}: ${cappedDetail}`
}

/** Best-effort extraction of a readable string from a JSON-RPC error `data` field. */
function extractStructuredDetail(data: unknown): string | undefined {
  if (data == null) return undefined
  if (typeof data === 'string') return compactWhitespace(data) || undefined
  if (typeof data !== 'object') return undefined
  const obj = data as Record<string, unknown>
  // Common shapes: { details: "..." }, { message: "..." }, { error: { message: "..." } }.
  const stringField = (value: unknown): string | undefined =>
    typeof value === 'string' && value ? value : undefined
  const nestedError =
    typeof obj.error === 'object' && obj.error ? (obj.error as Record<string, unknown>) : undefined
  const direct =
    stringField(obj.details) ?? stringField(obj.message) ?? stringField(nestedError?.message)
  if (direct) return compactWhitespace(direct) || undefined
  try {
    return compactWhitespace(JSON.stringify(data)) || undefined
  } catch {
    return undefined
  }
}

export function failureFromError(
  error: unknown,
  fallback: Omit<RuntimeFailure, 'userMessage'> & { userMessage?: string }
): RuntimeFailure {
  if (error instanceof AdapterRuntimeError) {
    return error.failure
  }
  return normalizeRuntimeFailure({
    ...fallback,
    userMessage: fallback.userMessage ?? messageFrom(error),
    technicalMessage: fallback.technicalMessage ?? messageFrom(error)
  })
}

export function normalizeRuntimeFailure(failure: RuntimeFailure): RuntimeFailure {
  const userMessage = compactWhitespace(failure.userMessage) || 'Agent run failed'
  const technicalMessage = compactWhitespace(failure.technicalMessage ?? '')
  return {
    ...failure,
    userMessage,
    technicalMessage: technicalMessage || undefined
  }
}

export function sanitizeProcessDiagnostic(text: string): string {
  return (
    text
      .replace(/Bearer\s+[A-Za-z0-9._~+/=-]+/gi, 'Bearer [redacted]')
      .replace(/sk-[A-Za-z0-9_-]{12,}/g, 'sk-[redacted]')
      // Common provider token shapes (GitHub, Slack) that appear bare in stderr.
      .replace(/\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{16,}\b/g, '[redacted]')
      .replace(/\bgithub_pat_[A-Za-z0-9_]{20,}\b/g, '[redacted]')
      .replace(/\bxox[a-z]-[A-Za-z0-9-]{10,}\b/gi, '[redacted]')
      // Field-style secrets: api_key=..., token: "...", password=..., etc.
      .replace(
        /((?:api[_-]?key|token|secret|password|passwd|pwd|credentials?|authorization)["'\s:=]+)[A-Za-z0-9._~+/=-]+/gi,
        '$1[redacted]'
      )
      .replace(/\s+/g, ' ')
      .trim()
      // Keep the TAIL: the final stderr lines carry the actual crash cause
      // (and the strings classifyAdapterProcessFailure sniffs for).
      .slice(-1_000)
  )
}

export function failureFromProcessExit(input: {
  adapterId: CodingAgentAdapterId
  exitCode: number | null
  recentStderr: string
}): RuntimeFailure {
  const diagnostic = sanitizeProcessDiagnostic(input.recentStderr)
  const technicalMessage =
    diagnostic || `${input.adapterId} ACP process exited with code ${input.exitCode}`
  const classified = classifyAdapterProcessFailure(input.adapterId, diagnostic)
  if (classified) {
    return normalizeRuntimeFailure({
      source: 'adapter_process',
      adapterId: input.adapterId,
      technicalMessage,
      ...classified
    })
  }
  const provider = providerFromDiagnostic(diagnostic)
  const label = adapterFailureLabel(input.adapterId, provider)
  return normalizeRuntimeFailure({
    code: 'adapter_process_exited',
    source: 'adapter_process',
    adapterId: input.adapterId,
    provider,
    retryable: true,
    userMessage: `${label} failed: ${technicalMessage}`,
    technicalMessage
  })
}

function classifyAdapterProcessFailure(
  adapterId: CodingAgentAdapterId,
  diagnostic: string
): (Pick<RuntimeFailure, 'code' | 'userMessage'> & Partial<RuntimeFailure>) | undefined {
  if (adapterId === 'openclaw' && isOpenClawInvalidConfig(diagnostic)) {
    return {
      code: 'adapter_config_invalid',
      retryable: false,
      userMessage:
        'OpenClaw needs a config migration. Run `openclaw doctor --fix`, then retry. Inspect with `openclaw config validate`.'
    }
  }
  return undefined
}

function isOpenClawInvalidConfig(diagnostic: string): boolean {
  const lower = diagnostic.toLowerCase()
  return (
    lower.includes('openclaw config is invalid') ||
    lower.includes('invalid config at') ||
    lower.includes('legacy config keys detected') ||
    lower.includes('openclaw doctor --fix') ||
    lower.includes('openclaw config validate') ||
    lower.includes('channels.telegram.streaming: invalid config')
  )
}

export function failureFromProcessError(input: {
  adapterId: CodingAgentAdapterId
  message: string
}): RuntimeFailure {
  const diagnostic = sanitizeProcessDiagnostic(input.message)
  const provider = providerFromDiagnostic(diagnostic)
  const label = adapterFailureLabel(input.adapterId, provider)
  return normalizeRuntimeFailure({
    code: 'adapter_process_error',
    source: 'adapter_process',
    adapterId: input.adapterId,
    provider,
    retryable: true,
    userMessage: `${label} failed: ${diagnostic || `${input.adapterId} ACP process error`}`,
    technicalMessage: diagnostic
  })
}

function providerFromDiagnostic(diagnostic: string): string | undefined {
  const lower = diagnostic.toLowerCase()
  if (lower.includes('openai')) return 'openai'
  if (lower.includes('anthropic') || lower.includes('claude')) return 'anthropic'
  if (lower.includes('gemini') || lower.includes('google')) return 'google'
  return undefined
}

function adapterFailureLabel(adapterId: CodingAgentAdapterId, provider?: string): string {
  switch (adapterId) {
    case 'openclaw':
      return 'OpenClaw'
    case 'hermes':
      return 'Hermes'
    case 'codex':
      return 'Codex'
    case 'acp':
      if (provider === 'openai') {
        return 'OpenAI'
      }
      return 'Claude Code'
  }
}

function compactWhitespace(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}
