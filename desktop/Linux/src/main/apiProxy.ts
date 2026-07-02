import { ipcMain } from 'electron'
import { getValidToken, forceRefreshToken } from './auth'
import { pythonBaseURL, rustBaseURL } from './env'
import { getByokKeys } from './secrets'
import type { ApiRequest, ApiResponse } from '../shared/types'

// All HTTP goes through the main process (no CORS, Node fetch), mirroring APIClient.swift:
// Bearer auth, platform header, BYOK headers, one forced refresh + retry on 401.

// Security: the renderer only ever supplies a relative path + a `base` selector.
// The final URL is built from the compile-time backend constants (overridable by
// env vars at launch only, never from renderer-writable settings), so a compromised
// renderer cannot redirect the Firebase Bearer token / BYOK keys to a foreign host.
// Absolute URLs are only honored if their origin matches one of those backends.
function allowedOrigins(): Set<string> {
  const origins = new Set<string>()
  for (const url of [pythonBaseURL(), rustBaseURL()]) {
    try {
      origins.add(new URL(url).origin)
    } catch {
      // ignore malformed override
    }
  }
  return origins
}

function resolveUrl(req: ApiRequest): string {
  const base = req.base === 'rust' ? rustBaseURL() : pythonBaseURL()
  if (/^https?:\/\//i.test(req.url)) {
    let origin: string
    try {
      origin = new URL(req.url).origin
    } catch {
      throw new Error('apiProxy: malformed absolute URL rejected')
    }
    if (!allowedOrigins().has(origin)) {
      throw new Error(`apiProxy: refusing to send credentials to non-backend host ${origin}`)
    }
    return req.url
  }
  return base + req.url.replace(/^\//, '')
}

async function buildHeaders(req: ApiRequest, token: string | null): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    'Content-Type': req.contentType || 'application/json',
    'X-App-Platform': 'linux',
    'X-Request-Start-Time': String(Math.floor(Date.now() / 1000))
  }
  if (token && !req.anonymous) headers['Authorization'] = `Bearer ${token}`
  // Gate BYOK secrets behind a valid session, like the Bearer token: a credential-free
  // (anonymous) or signed-out request must not carry the user's provider keys.
  if (token && !req.anonymous) {
    const k = getByokKeys()
    if (k.openai) headers['X-BYOK-OpenAI'] = k.openai
    if (k.anthropic) headers['X-BYOK-Anthropic'] = k.anthropic
    if (k.gemini) headers['X-BYOK-Gemini'] = k.gemini
    if (k.deepgram) headers['X-BYOK-Deepgram'] = k.deepgram
  }
  return headers
}

async function doFetch(req: ApiRequest, token: string | null, signal?: AbortSignal): Promise<Response> {
  return fetch(resolveUrl(req), {
    method: req.method,
    headers: await buildHeaders(req, token),
    body: req.body ?? undefined,
    signal
  })
}

export async function apiRequest(req: ApiRequest): Promise<ApiResponse> {
  let token = req.anonymous ? null : await getValidToken()
  let res = await doFetch(req, token)
  if (res.status === 401 && !req.anonymous) {
    token = await forceRefreshToken()
    if (token) res = await doFetch(req, token)
  }
  return { status: res.status, body: await res.text() }
}

/** Binary variant for endpoints that return audio (TTS). Returns base64 body. */
export async function apiRequestBinary(req: ApiRequest): Promise<{ status: number; base64: string; contentType: string }> {
  let token = req.anonymous ? null : await getValidToken()
  let res = await doFetch(req, token)
  if (res.status === 401 && !req.anonymous) {
    token = await forceRefreshToken()
    if (token) res = await doFetch(req, token)
  }
  const buf = Buffer.from(await res.arrayBuffer())
  return { status: res.status, base64: buf.toString('base64'), contentType: res.headers.get('content-type') || '' }
}

const ALLOWED_METHODS = new Set(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
const streamControllers = new Map<string, AbortController>()

// Validate the shape of a renderer-supplied request before it is sent with the user's
// credentials attached. Host pinning is in resolveUrl; this rejects malformed input
// and unexpected methods.
function sanitizeRequest(req: ApiRequest): ApiRequest {
  if (!req || typeof req !== 'object') throw new Error('apiProxy: invalid request')
  const method = String(req.method || '').toUpperCase()
  if (!ALLOWED_METHODS.has(method)) throw new Error('apiProxy: invalid method')
  if (typeof req.url !== 'string') throw new Error('apiProxy: invalid url')
  if (req.base !== 'python' && req.base !== 'rust') throw new Error('apiProxy: invalid base')
  return { ...req, method }
}

export function registerApiIpc(): void {
  ipcMain.handle('api:request', async (_e, req: ApiRequest) => apiRequest(sanitizeRequest(req)))
  ipcMain.handle('api:request-binary', async (_e, req: ApiRequest) => apiRequestBinary(sanitizeRequest(req)))

  ipcMain.on('api:stream:cancel', (_e, id: string) => {
    streamControllers.get(id)?.abort()
  })

  // Streaming (SSE) variant: emits api:stream:<id> events {type:'chunk'|'done'|'error'} to the caller.
  ipcMain.handle('api:stream', async (e, id: string, reqRaw: ApiRequest) => {
    const req = sanitizeRequest(reqRaw)
    const sender = e.sender
    const controller = new AbortController()
    streamControllers.set(id, controller)
    const emit = (payload: Record<string, unknown>) => {
      if (!sender.isDestroyed()) sender.send(`api:stream:${id}`, payload)
    }
    try {
      let token = req.anonymous ? null : await getValidToken()
      let res = await doFetch(req, token, controller.signal)
      if (res.status === 401 && !req.anonymous) {
        token = await forceRefreshToken()
        if (token) res = await doFetch(req, token, controller.signal)
      }
      if (!res.ok || !res.body) {
        emit({ type: 'error', status: res.status, body: await res.text() })
        return
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        emit({ type: 'chunk', data: decoder.decode(value, { stream: true }) })
      }
      emit({ type: 'done' })
    } catch (err) {
      // An abort (renderer cancelled the stream) is expected, not an error.
      if (!controller.signal.aborted) emit({ type: 'error', status: 0, body: String(err) })
    } finally {
      streamControllers.delete(id)
    }
  })
}
