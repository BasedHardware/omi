const REDACTED = '[Filtered]'
const CONTENT_REDACTED = '[Filtered content]'
const CIRCULAR_REDACTED = '[Circular]'
const MAX_STRING_LENGTH = 2048
const MAX_ARRAY_LENGTH = 50
const MAX_DEPTH = 8
const MAX_ERROR_CAUSE_DEPTH = 8

const AUTH_HEADER_RE = /\b(authorization\s*[:=]\s*)(bearer|basic)\s+([^"',\s;]+)/gi
const BARE_BEARER_RE = /\bbearer\s+[A-Za-z0-9._~+/=-]{12,}/gi
const JWT_RE = /\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g
const DATA_URL_RE = /\bdata:image\/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=]+/g
const LONG_BASE64_RE = /\b[A-Za-z0-9+/]{160,}={0,2}\b/g
const URL_SECRET_PARAM_RE =
  /([?&](?:access_token|id_token|refresh_token|token|api_key|apikey|key|secret|code)=)[^&#\s]+/gi
const INLINE_SECRET_RE =
  /\b([A-Za-z0-9_.-]*(?:api[_-]?key|mcp[_-]?key|byok|secret|token|password)[A-Za-z0-9_.-]*\s*[:=]\s*)(["']?)([^"',\s&;}]{6,})(\2)/gi
const INLINE_CONTENT_KEY =
  '(?:response[_-]?text|response[_-]?body|api[_-]?response|ocr[_-]?text|transcript|body|messages|sql|query)'
const QUOTED_INLINE_CONTENT_RE = new RegExp(
  `\\b(${INLINE_CONTENT_KEY}\\s*[:=]\\s*)(["'])([\\s\\S]*?)(\\2)`,
  'gi'
)
const UNQUOTED_INLINE_CONTENT_RE = new RegExp(
  `\\b(${INLINE_CONTENT_KEY}\\s*[:=]\\s*)(?!["'])([^,;&}\\]\\r\\n]{6,})`,
  'gi'
)
const LIKELY_API_KEY_RE =
  /\b(?:sk-[A-Za-z0-9][A-Za-z0-9_-]{12,}|sk-proj-[A-Za-z0-9_-]{12,}|AIza[0-9A-Za-z_-]{20,}|dg_[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|mcp_[A-Za-z0-9_-]{12,}|omi_[A-Za-z0-9_-]{12,}|secret_[A-Za-z0-9_-]{12,})\b/g

const SECRET_FIELD_KEYS = new Set([
  'authorization',
  'cookie',
  'setcookie',
  'token',
  'idtoken',
  'idtoken',
  'firebasetoken',
  'accesstoken',
  'refreshtoken',
  'apikey',
  'key',
  'hostedkey',
  'localtoken',
  'byok',
  'byokkey',
  'password',
  'secret',
  'credential',
  'credentials'
])

const CONTENT_FIELD_KEYS = new Set([
  'body',
  'requestbody',
  'responsebody',
  'responsetext',
  'apiresponse',
  'ocr',
  'ocrtext',
  'transcript',
  'transcription',
  'messages',
  'content',
  'prompt',
  'texttosend',
  'query',
  'sql',
  'statement',
  'screenshot',
  'image',
  'imagedata',
  'dataurl',
  'base64',
  'thumbnaildataurl'
])

function normalizedKey(key: string): string {
  return key.toLowerCase().replace(/[^a-z0-9]/g, '')
}

function shouldRedactSecretField(key: string): boolean {
  const normalized = normalizedKey(key)
  return (
    SECRET_FIELD_KEYS.has(normalized) ||
    normalized.endsWith('token') ||
    normalized.endsWith('apikey') ||
    normalized.endsWith('secret') ||
    normalized.includes('authorization')
  )
}

function shouldRedactContentField(key: string): boolean {
  return CONTENT_FIELD_KEYS.has(normalizedKey(key))
}

export function redactStringForObservability(value: string): string {
  const redacted = value
    .replace(
      AUTH_HEADER_RE,
      (_match, prefix: string, scheme: string) => `${prefix}${scheme} ${REDACTED}`
    )
    .replace(BARE_BEARER_RE, `Bearer ${REDACTED}`)
    .replace(JWT_RE, REDACTED)
    .replace(DATA_URL_RE, 'data:image/[Filtered]')
    .replace(URL_SECRET_PARAM_RE, `$1${REDACTED}`)
    .replace(
      INLINE_SECRET_RE,
      (_match, prefix: string, quote: string) => `${prefix}${quote}${REDACTED}${quote}`
    )
    .replace(
      QUOTED_INLINE_CONTENT_RE,
      (_match, prefix: string, quote: string) => `${prefix}${quote}${CONTENT_REDACTED}${quote}`
    )
    .replace(UNQUOTED_INLINE_CONTENT_RE, (_match, prefix: string) => `${prefix}${CONTENT_REDACTED}`)
    .replace(LIKELY_API_KEY_RE, REDACTED)
    .replace(LONG_BASE64_RE, REDACTED)

  if (redacted.length <= MAX_STRING_LENGTH) return redacted
  return `${redacted.slice(0, MAX_STRING_LENGTH)}...[truncated]`
}

function sanitizeObject(
  value: Record<string, unknown>,
  depth: number,
  seen: WeakSet<object>
): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [key, entry] of Object.entries(value)) {
    if (shouldRedactSecretField(key)) {
      out[key] = REDACTED
      continue
    }
    if (shouldRedactContentField(key)) {
      out[key] = CONTENT_REDACTED
      continue
    }
    out[key] = sanitizeObservabilityValue(entry, depth + 1, seen)
  }
  return out
}

export function errorToObservabilityPayload(
  error: unknown,
  depth = 0,
  seen = new WeakSet<object>()
): Record<string, unknown> {
  if (error instanceof Error) {
    if (seen.has(error)) return { message: CIRCULAR_REDACTED }
    if (depth >= MAX_ERROR_CAUSE_DEPTH) return { message: '[MaxDepth]' }
    seen.add(error)
    const cause = (error as Error & { cause?: unknown }).cause
    return sanitizeObservabilityValue({
      name: error.name,
      message: error.message,
      stack: error.stack,
      cause: cause === undefined ? undefined : errorToObservabilityPayload(cause, depth + 1, seen)
    }) as Record<string, unknown>
  }
  return {
    message: redactStringForObservability(String(error))
  }
}

export function sanitizeObservabilityValue(
  value: unknown,
  depth = 0,
  seen = new WeakSet<object>()
): unknown {
  if (value === null || value === undefined) return value
  if (typeof value === 'string') return redactStringForObservability(value)
  if (typeof value === 'number' || typeof value === 'boolean') return value
  if (typeof value === 'bigint') return value.toString()
  if (typeof value === 'symbol' || typeof value === 'function') return `[${typeof value}]`
  if (value instanceof Error) return errorToObservabilityPayload(value, depth)
  if (depth >= MAX_DEPTH) return '[MaxDepth]'

  if (typeof value === 'object') {
    if (seen.has(value)) return CIRCULAR_REDACTED
    seen.add(value)
    if (Array.isArray(value)) {
      return value
        .slice(0, MAX_ARRAY_LENGTH)
        .map((entry) => sanitizeObservabilityValue(entry, depth + 1, seen))
    }
    return sanitizeObject(value as Record<string, unknown>, depth, seen)
  }

  return String(value)
}
