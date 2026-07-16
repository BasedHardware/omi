// The ONE main-side client for the backend's platform-tool endpoints
// (`/v1/tools/*`, backend/routers/tools.py). Mac routes memories + conversations
// tools through `executeBackendTool`; Windows' agent executors (get_memories,
// search_memories, get_conversations, search_conversations) call this instead.
//
// WHY A DEDICATED WRAPPER. The generated OpenAPI client is renderer-only; the main
// process already has the session + fetch idiom (assistants/core/session +
// electron `net.fetch`, same as taskSyncEngine / insight/context), so this is a
// thin wrapper over that idiom, NOT new auth plumbing.
//
// RESPONSE CONTRACT. Every `/v1/tools/*` route returns the ToolResponse envelope
// `{ tool_name, result_text, is_error }`. `result_text` is ALREADY the model-facing
// string (the backend formats it), so an executor's job is just to relay it. This
// wrapper returns `result_text` on success and an `Error: …` string on any failure
// (no throw), matching the relay's tool_result contract.
//
// INV-AGENT. The call authenticates with the HOST session token (getBackendSession)
// — never a uid or token supplied in the tool input — so a model can only ever read
// the signed-in user's own data. The request is aborted when EITHER the caller's
// signal (relay socket disconnect) OR the session's own abort signal (sign-out /
// token refresh) fires.

import { net } from 'electron'
import { getAbortSignal, getBackendSession } from '../assistants/core/session'

/** Backend ToolResponse envelope (backend/routers/tools.py). */
interface ToolResponseEnvelope {
  tool_name?: string
  result_text?: string
  is_error?: boolean
}

export interface BackendToolRequest {
  method: 'GET' | 'POST'
  /** Path under the Python backend base, e.g. `/v1/tools/memories`. */
  path: string
  /** Query params (GET); undefined/null values are dropped. */
  query?: Record<string, string | number | boolean | null | undefined>
  /** JSON body (POST). */
  body?: Record<string, unknown>
  /** Caller abort (relay socket disconnect). Combined with the session signal. */
  signal?: AbortSignal
  /** Per-call timeout; defaults to 20s (these are fast reads/searches). */
  timeoutMs?: number
}

const DEFAULT_TIMEOUT_MS = 20_000

function buildQuery(query: BackendToolRequest['query']): string {
  if (!query) return ''
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null) continue
    params.set(k, String(v))
  }
  const s = params.toString()
  return s ? `?${s}` : ''
}

/**
 * Call one `/v1/tools/*` endpoint and return its `result_text`. Fail-open to an
 * `Error: …` string (never a throw) on no-session, timeout, abort, non-2xx, or a
 * malformed body, so the tool loop continues.
 */
export async function backendToolFetch(req: BackendToolRequest): Promise<string> {
  const session = getBackendSession()
  if (!session) return 'Error: not signed in to Omi. Ask the user to sign in, then retry.'

  const external = req.signal
  const sessionSignal = getAbortSignal()
  // Already gone (socket disconnected / signed out) — don't even open the request.
  if (external?.aborted || sessionSignal?.aborted) return 'Error: request was cancelled.'

  const ctrl = new AbortController()
  const onAbort = (): void => ctrl.abort()
  external?.addEventListener('abort', onAbort, { once: true })
  sessionSignal?.addEventListener('abort', onAbort, { once: true })
  const timer = setTimeout(() => ctrl.abort(), req.timeoutMs ?? DEFAULT_TIMEOUT_MS)

  try {
    const url = `${session.apiBase}${req.path}${buildQuery(req.query)}`
    const init: Parameters<typeof net.fetch>[1] = {
      method: req.method,
      headers: {
        Authorization: `Bearer ${session.token}`,
        ...(req.method === 'POST' ? { 'Content-Type': 'application/json' } : {})
      },
      signal: ctrl.signal
    }
    if (req.method === 'POST') init.body = JSON.stringify(req.body ?? {})

    const res = await net.fetch(url, init)
    if (!res.ok) return `Error: backend tool request failed (HTTP ${res.status})`
    const data = (await res.json()) as ToolResponseEnvelope
    const text = typeof data.result_text === 'string' ? data.result_text : ''
    if (!text) return 'No results.'
    return text
  } catch (e) {
    if (ctrl.signal.aborted) return 'Error: request was cancelled.'
    return `Error: ${e instanceof Error ? e.message : 'backend tool request failed'}`
  } finally {
    clearTimeout(timer)
    external?.removeEventListener('abort', onAbort)
    sessionSignal?.removeEventListener('abort', onAbort)
  }
}
