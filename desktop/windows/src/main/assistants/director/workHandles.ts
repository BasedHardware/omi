/**
 * Port of macOS WorkHistoryHandle (WorkHistoryHandle.swift).
 *
 * A handle is a durable identity a visit can carry beyond its window title:
 * a canonical URL or file path survives title churn, so bucket resolution
 * prefers it over the title hash. Windows has no accessibility URL scrape
 * (mac's WorkHistoryHandleExtractor reads browser address bars via AX), so
 * url/file handles only appear when a future producer supplies them; the
 * model and canonicalization port now so the store speaks the same language.
 */

export type WorkHandleKind = 'url' | 'file' | 'app_window'

export interface WorkHandle {
  kind: WorkHandleKind
  value: string
}

export function isDurable(handle: WorkHandle): boolean {
  return handle.kind === 'url' || handle.kind === 'file'
}

export function handleIdentityKey(handle: WorkHandle): string {
  return `${handle.kind}::${handle.value}`
}

/** First durable handle, else the first handle. */
export function primaryHandle(handles: readonly WorkHandle[]): WorkHandle | null {
  for (const h of handles) {
    if (isDurable(h)) return h
  }
  return handles.length > 0 ? handles[0] : null
}

const DROPPED_QUERY_NAMES = new Set([
  'usp',
  'sid',
  'authuser',
  'tab',
  'pli',
  'hl',
  'gclid',
  'fbclid',
  'igshid',
  'code',
  'state',
  'access_token',
  'refresh_token',
  'id_token',
  'oauth_token',
  'api_key',
  'apikey',
  'authorization',
  'bearer',
  'jwt',
  'client_secret'
])

function shouldDropQueryParam(name: string): boolean {
  const lowered = name.toLowerCase()
  if (DROPPED_QUERY_NAMES.has(lowered)) return true
  if (lowered.startsWith('utm_')) return true
  if (
    lowered.includes('token') ||
    lowered.includes('secret') ||
    lowered.includes('password') ||
    lowered.includes('passwd') ||
    lowered.includes('session')
  ) {
    return true
  }
  return lowered.endsWith('sig')
}

/** Canonicalize a URL for durable identity; null when it cannot serve as one.
 *  http/https only, lowercased host, default ports stripped, trailing slash
 *  stripped (path longer than "/"), tracking/secret query params dropped. */
export function canonicalizeUrl(raw: string): string | null {
  let url: URL
  try {
    url = new URL(raw.trim())
  } catch {
    return null
  }
  const scheme = url.protocol.replace(':', '').toLowerCase()
  if (scheme !== 'http' && scheme !== 'https') return null
  if (url.hostname.length === 0) return null

  const host = url.hostname.toLowerCase()
  const port =
    url.port === '' ||
    (scheme === 'http' && url.port === '80') ||
    (scheme === 'https' && url.port === '443')
      ? ''
      : `:${url.port}`

  let path = url.pathname
  if (path.length > 1 && path.endsWith('/')) path = path.slice(0, -1)

  const keptParams: string[] = []
  for (const [name, value] of url.searchParams.entries()) {
    if (shouldDropQueryParam(name)) continue
    keptParams.push(value === '' ? name : `${name}=${value}`)
  }
  const query = keptParams.length > 0 ? `?${keptParams.join('&')}` : ''

  return `${scheme}://${host}${port}${path}${query}`
}

/** Canonicalize a file path; rejects empty and filesystem roots. */
export function canonicalizeFile(raw: string): string | null {
  const trimmed = raw.trim()
  if (trimmed.length === 0) return null
  const normalized = trimmed.replace(/[\\/]+/g, '\\').replace(/\\$/, '')
  if (normalized.length === 0) return null
  if (normalized === '\\' || /^[A-Za-z]:$/.test(normalized)) return null
  return normalized
}

/** The app_window handle value mirrors mac: `app\ntitle`. */
export function appWindowHandleValue(appName: string, windowTitle: string): string {
  return `${appName}\n${windowTitle}`
}
