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

  // Preserve each kept pair's RAW encoded bytes: decoding and re-encoding
  // would change durable identity. Only the decoded name drives the drop.
  const rawQuery = url.search.startsWith('?') ? url.search.slice(1) : url.search
  const keptParams: string[] = []
  for (const pair of rawQuery.length > 0 ? rawQuery.split('&') : []) {
    if (pair.length === 0) continue
    const eq = pair.indexOf('=')
    const rawName = eq >= 0 ? pair.slice(0, eq) : pair
    let name: string
    try {
      name = decodeURIComponent(rawName.replace(/\+/g, ' '))
    } catch {
      name = rawName
    }
    if (shouldDropQueryParam(name)) continue
    keptParams.push(pair)
  }
  const query = keptParams.length > 0 ? `?${keptParams.join('&')}` : ''

  return `${scheme}://${host}${port}${path}${query}`
}

/** Canonicalize a file path for durable identity: separator runs collapse
 *  (preserving a UNC root), dot segments resolve, and empty paths, filesystem
 *  roots, drive-relative paths, and bare UNC servers are rejected. */
export function canonicalizeFile(raw: string): string | null {
  const trimmed = raw.trim()
  if (trimmed.length === 0) return null
  const isUnc = /^[\\/]{2}[^\\/]/.test(trimmed)
  let normalized = trimmed.replace(/[\\/]+/g, '\\').replace(/\\+$/, '')
  if (isUnc) normalized = '\\' + normalized
  if (normalized.length === 0 || normalized === '\\' || normalized === '\\\\') return null
  // Drive-relative (C:foo) has no stable absolute identity.
  if (/^[A-Za-z]:$/.test(normalized)) return null
  if (/^[A-Za-z]:[^\\]/.test(normalized)) return null

  // Resolve . and .. segments so aliases share one identity; never pop past
  // the root (drive or \\server\share).
  const prefixMatch = isUnc ? '\\\\' : ''
  const body = isUnc ? normalized.slice(2) : normalized
  const segments = body.split('\\')
  const rootCount = isUnc ? 2 : /^[A-Za-z]:$/.test(segments[0] ?? '') ? 1 : 0
  const resolved: string[] = []
  for (const segment of segments) {
    if (segment === '.') continue
    if (segment === '..') {
      if (resolved.length > rootCount) resolved.pop()
      continue
    }
    resolved.push(segment)
  }
  const result = prefixMatch + resolved.join('\\')
  if (isUnc && resolved.length < 2) return null // bare \\server has no share
  if (/^[A-Za-z]:$/.test(result)) return null
  return result
}

/** Producer factories: the ONLY sanctioned way to mint durable handles — they
 *  guarantee canonicalization (credential/tracking query stripping, UNC-safe
 *  paths) before a value can enter bucket identity. */
export function makeUrlWorkHandle(rawUrl: string): WorkHandle | null {
  const canonical = canonicalizeUrl(rawUrl)
  return canonical === null ? null : { kind: 'url', value: canonical }
}

export function makeFileWorkHandle(rawPath: string): WorkHandle | null {
  const canonical = canonicalizeFile(rawPath)
  return canonical === null ? null : { kind: 'file', value: canonical }
}

/** The app_window handle value mirrors mac: `app\ntitle`. */
export function appWindowHandleValue(appName: string, windowTitle: string): string {
  return `${appName}\n${windowTitle}`
}
