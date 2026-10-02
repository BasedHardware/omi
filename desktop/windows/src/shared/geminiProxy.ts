import type { GeminiLane, GeminiWorkload } from './geminiAttribution'

export const GEMINI_PROXY_ACTIONS = [
  'generateContent',
  'streamGenerateContent',
  'embedContent',
  'batchEmbedContents'
] as const
export type GeminiProxyAction = (typeof GEMINI_PROXY_ACTIONS)[number]

// Wire values for X-App-Platform. These are client identities the backend
// resolver (journey_metrics_contract._PLATFORM_CLIENT_KIND) normalizes: the
// terminal event's client_platform enum — {macos, windows, other, unknown} —
// is the generated server-side contract, and 'linux' on the wire maps to
// 'other' there via desktop_linux. Do not send 'other' from a client; the
// resolver does not recognize it and would record client_platform: unknown.
export type GeminiClientPlatform = 'windows' | 'macos' | 'linux' | 'unknown'

export function geminiClientPlatform(platform: string | undefined | null): GeminiClientPlatform {
  switch (platform) {
    case 'win32':
      return 'windows'
    case 'darwin':
      return 'macos'
    case 'linux':
      return 'linux'
    default:
      return 'unknown'
  }
}

export type GeminiProxyRequest = {
  baseURL: string
  model: string
  action: GeminiProxyAction
  token: string
  body: string
  lane: GeminiLane
  workload: GeminiWorkload
  platform: GeminiClientPlatform
  signal?: AbortSignal
}

export type GeminiFetch = (input: string, init?: RequestInit) => Promise<Response>

// The backend exposes two routes: `gemini-stream` marks the request as a
// stream for gateway routing and cancellation telemetry; a streaming action
// sent to the plain route would silently lose both.
export function geminiProxyFetch(
  fetchImpl: GeminiFetch,
  req: GeminiProxyRequest
): Promise<Response> {
  const route = req.action === 'streamGenerateContent' ? 'gemini-stream' : 'gemini'
  const url = `${req.baseURL}/v1/proxy/${route}/models/${req.model}:${req.action}`
  return fetchImpl(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${req.token}`,
      'X-Omi-Lane': req.lane,
      'X-Omi-Workload': req.workload,
      'X-App-Platform': req.platform
    },
    body: req.body,
    signal: req.signal
  })
}
