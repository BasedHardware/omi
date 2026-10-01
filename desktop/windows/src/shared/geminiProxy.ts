import type { GeminiLane, GeminiWorkload } from './geminiAttribution'

export const GEMINI_PROXY_ACTIONS = [
  'generateContent',
  'streamGenerateContent',
  'embedContent',
  'batchEmbedContents'
] as const
export type GeminiProxyAction = (typeof GEMINI_PROXY_ACTIONS)[number]

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

export function geminiProxyFetch(
  fetchImpl: GeminiFetch,
  req: GeminiProxyRequest
): Promise<Response> {
  const url = `${req.baseURL}/v1/proxy/gemini/models/${req.model}:${req.action}`
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
