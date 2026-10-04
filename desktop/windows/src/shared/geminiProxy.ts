import type { GeminiLane, GeminiWorkload } from './geminiAttribution'

export const GEMINI_PROXY_ACTIONS = [
  'generateContent',
  'streamGenerateContent',
  'embedContent',
  'batchEmbedContents'
] as const
export type GeminiProxyAction = (typeof GEMINI_PROXY_ACTIONS)[number]

// Telemetry-only platform identity. The proxy maps Linux to the generated
// 'other' value. This header must not activate auth's platform persistence.
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
      'X-Omi-Client-Platform': req.platform
    },
    body: req.body,
    signal: req.signal
  })
}
