import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'
import { auth } from './firebase'

// Retried statuses: 429 (rate limited) and 503 (transient). Anything else fails
// fast as before.
const RETRY_STATUSES = new Set([429, 503])
const MAX_RETRIES = 5

// __noRetry lets a caller (e.g. the paced bulk-delete loop) own 429 handling
// itself, so the interceptor's short backoff doesn't fight a longer rate window.
type RetryConfig = InternalAxiosRequestConfig & { __retryCount?: number; __noRetry?: boolean }

function makeClient(baseURL: string): AxiosInstance {
  // 12s is enough for normal Omi responses and short enough that a stuck
  // request doesn't lock the UI in a perpetual loading state.
  const client = axios.create({ baseURL, timeout: 12_000 })

  client.interceptors.request.use(async (config) => {
    const user = auth.currentUser
    if (user) {
      const token = await user.getIdToken()
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  // Back off and retry on rate limits. Bulk operations (e.g. paging or deleting
  // thousands of memories) otherwise trip the server's request cap and surface a
  // raw 429 to the user. Respects a Retry-After header when present, else uses
  // exponential backoff with jitter.
  client.interceptors.response.use(undefined, async (error) => {
    const config = error.config as RetryConfig | undefined
    const status = error.response?.status as number | undefined
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
  })

  return client
}

export const omiApi = makeClient(import.meta.env.VITE_OMI_API_BASE as string)
export const desktopApi = makeClient(import.meta.env.VITE_OMI_DESKTOP_API_BASE as string)
