import axios, {
  type AxiosInstance,
  type AxiosResponse,
  type InternalAxiosRequestConfig
} from 'axios'
import { auth } from './firebase'
import { forceReauth, refreshIdToken } from './authSession'
import { withByokHeadersIfActive } from './byokKeys'

// Retried statuses: 429 (rate limited) and 503 (transient). Anything else fails
// fast as before. 401 is handled separately (refresh → retry → reauth).
const RETRY_STATUSES = new Set([429, 503])
const MAX_RETRIES = 5

// __noRetry lets a caller (e.g. the paced bulk-delete loop) own 429 handling
// itself, so the interceptor's short backoff doesn't fight a longer rate window.
// __reauthTried marks that a 401 already triggered one forced-refresh retry, so a
// still-401 response after that goes straight to reauth instead of looping.
// __sessionPreserving is the macOS RequestAuthPolicy.sessionPreserving knob: a
// background poller sets it so a dead-session 401 rejects as unauthorized WITHOUT
// kicking the user to the sign-in screen (it still gets the refresh+retry).
type RetryConfig = InternalAxiosRequestConfig & {
  __retryCount?: number
  __noRetry?: boolean
  __reauthTried?: boolean
  __sessionPreserving?: boolean
}

/**
 * Shared axios response-error handler for the Firebase-authed clients. Extracted
 * (rather than inlined in the interceptor) so the 401 refresh→retry→reauth path
 * is unit-testable with a fake client. `client` is the axios instance used to
 * re-issue a retried request.
 */
export async function responseErrorHandler(
  client: AxiosInstance,
  error: { config?: RetryConfig; response?: { status?: number; headers?: Record<string, unknown> } }
): Promise<AxiosResponse> {
  const config = error.config
  const status = error.response?.status

  // 401: the backend rejected our Firebase token. Force-refresh once and retry.
  // Mirrors macOS refresh→retry→classify: a DEFINITIVE death (no user, permanent
  // refresh failure, or a still-401 after a fresh token) routes to sign-in; a
  // TRANSIENT refresh failure (network blip) keeps the session and just rejects,
  // so we never kick the user to Login on a blip. __noRetry opts a caller out
  // entirely; __sessionPreserving (background pollers) still refreshes+retries but
  // never forces reauth on death.
  if (status === 401 && config && !config.__noRetry) {
    const preserving = config.__sessionPreserving === true
    if (!config.__reauthTried) {
      const outcome = await refreshIdToken()
      if (outcome.status === 'ok') {
        config.__reauthTried = true // consumed our one retry
        config.headers.Authorization = `Bearer ${outcome.token}`
        return client(config)
      }
      if (outcome.status === 'transient') return Promise.reject(error) // keep session, retry later
      // outcome.status === 'dead' → fall through to reauth
    }
    // Definitive death (dead refresh on the first pass, or a post-refresh 401 with
    // __reauthTried already set). Surface reauth (light: routes to Login, no data
    // wipe) unless this request opted to preserve the session.
    if (!preserving) await forceReauth()
    return Promise.reject(error)
  }

  // Back off and retry on rate limits / transient errors. Bulk operations (e.g.
  // paging or deleting thousands of memories) otherwise trip the server's request
  // cap and surface a raw 429. Respects Retry-After when present, else exponential
  // backoff with jitter.
  if (!config || config.__noRetry || status === undefined || !RETRY_STATUSES.has(status))
    return Promise.reject(error)
  config.__retryCount = (config.__retryCount ?? 0) + 1
  if (config.__retryCount > MAX_RETRIES) return Promise.reject(error)
  const retryAfter = Number(error.response?.headers?.['retry-after'])
  const waitMs =
    Number.isFinite(retryAfter) && retryAfter > 0
      ? retryAfter * 1000
      : Math.min(1000 * 2 ** (config.__retryCount - 1), 16_000) + Math.random() * 400
  await new Promise((resolve) => setTimeout(resolve, waitMs))
  return client(config)
}

// Real app version, resolved once at startup from the main process (app:get-version
// IPC). apiClient is imported at module load — long before that async call lands —
// so the interceptor reads this lazily and simply omits X-App-Version until it's
// known, never blocking a request on it. The backend version-gates features on the
// (platform, version) pair, so an absent version is treated as an unknown one.
let appVersion: string | undefined

/** Record the resolved app version so the interceptor stamps X-App-Version.
 *  Exported as the startup hook and the test seam. */
export function setAppVersion(version: string | undefined): void {
  appVersion = version
}

/**
 * Stamp the platform-identity headers the backend version-gates features on.
 * Both are applied here (not just as axios `create` defaults) so every outgoing
 * request carries the pair and a single unit test can pin them. X-App-Version is
 * omitted until the async version lookup lands — never blocks a request.
 */
export function applyPlatformHeaders<T extends InternalAxiosRequestConfig>(config: T): T {
  config.headers['X-App-Platform'] = 'windows'
  if (appVersion) config.headers['X-App-Version'] = appVersion
  return config
}

// Fire the one-time version lookup. Fire-and-forget: any request issued before it
// resolves just goes out without X-App-Version (see applyPlatformHeaders). Guarded
// on `window` so importing this module in a non-renderer context (tests) is inert.
if (typeof window !== 'undefined') {
  void window.omi
    ?.getAppVersion?.()
    .then((v) => setAppVersion(v?.version))
    .catch(() => {})
}

function makeClient(baseURL: string): AxiosInstance {
  // 12s is enough for normal Omi responses and short enough that a stuck
  // request doesn't lock the UI in a perpetual loading state.
  const client = axios.create({ baseURL, timeout: 12_000 })

  client.interceptors.request.use(async (config) => {
    // Platform + version tag on every request — same convention as the macOS/
    // Flutter clients (their shared header builders), so the backend can give
    // Windows-appropriate answers, version-gate features, and attribute quota.
    applyPlatformHeaders(config)
    const user = auth.currentUser
    if (user) {
      const token = await user.getIdToken()
      config.headers.Authorization = `Bearer ${token}`
    }
    // BYOK: when the user has a full key set, attach X-BYOK-* (all-or-none) so
    // Omi-managed lanes run on their own provider keys. No-op when inactive.
    const byokHeaders = withByokHeadersIfActive<Record<string, string>>({})
    for (const [name, value] of Object.entries(byokHeaders)) {
      config.headers[name] = value
    }
    return config
  })

  client.interceptors.response.use(undefined, (error) => responseErrorHandler(client, error))

  return client
}

export const omiApi = makeClient(import.meta.env.VITE_OMI_API_BASE as string)
export const desktopApi = makeClient(import.meta.env.VITE_OMI_DESKTOP_API_BASE as string)
