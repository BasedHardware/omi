// X (Twitter) connector — main process. Backend-mediated OAuth2 + PKCE: the
// backend does the token exchange and kicks off the first ingest, so the desktop
// only opens the auth URL and POLLS connection-status. Living in main (like the
// Google integration) is what lets an import RUN OUTLIVE the Connect panel — the
// panel can be dismissed while main keeps polling and streaming progress (the
// direct analog of macOS's ConnectorImportRunner).
//
// Auth: the renderer holds the Firebase token, so it passes { apiBase, token }
// with each call (same token-relay convention as aiUserProfile/insight).
import { net, shell, BrowserWindow } from 'electron'
import type { XConnectorSession, XStatus, XSyncResult, XRunState } from '../../shared/types'

export type XSession = XConnectorSession

export const X_PROGRESS_CHANNEL = 'integrations:x:progress'

// Phase-1 (connect) and phase-2 (first-ingest) poll cadences — mirror macOS's
// ConnectorImportOperations: 2s × 60 (2 min) waiting for the account to connect,
// then 2s × 90 (3 min) watching the background sync drain.
const PHASE1 = { intervalMs: 2000, maxAttempts: 60 }
const PHASE2 = { intervalMs: 2000, maxAttempts: 90 }

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))
const X_OAUTH_HOSTS = new Set(['x.com', 'twitter.com'])

export function isAllowedXOAuthUrl(rawUrl: string): boolean {
  try {
    const url = new URL(rawUrl)
    return url.protocol === 'https:' && X_OAUTH_HOSTS.has(url.hostname.toLowerCase())
  } catch {
    return false
  }
}

// The single X run's live state, held in main so it survives panel unmount.
let runState: XRunState = { phase: 'idle', postCount: 0, memoryCount: 0 }

function configuredApiBase(): string {
  return (import.meta.env.VITE_OMI_API_BASE || 'https://api.omi.me').replace(/\/+$/, '')
}

function broadcast(): void {
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w.isDestroyed()) w.webContents.send(X_PROGRESS_CHANNEL, runState)
  }
}

function setRun(patch: Partial<XRunState>): void {
  runState = { ...runState, ...patch }
  broadcast()
}

export function xRunStateSnapshot(): XRunState {
  return runState
}

async function authedFetch<T>(session: XSession, path: string, method: 'GET' | 'POST'): Promise<T> {
  // The renderer relays the short-lived token, but it has no authority to pick
  // the host that receives it. The build/runtime configuration is the trust
  // anchor for the Omi API origin.
  const res = await net.fetch(`${configuredApiBase()}${path}`, {
    method,
    headers: { Authorization: `Bearer ${session.token}`, 'X-App-Platform': 'windows' }
  })
  if (!res.ok) throw new Error(`X ${path} → HTTP ${res.status}`)
  return (await res.json()) as T
}

export async function xStatus(session: XSession): Promise<XStatus> {
  const d = await authedFetch<{
    connected?: boolean
    handle?: string
    post_count?: number
    memory_count?: number
    syncing?: boolean
    last_synced_at?: string
  }>(session, '/v1/x/connection-status', 'GET')
  return {
    connected: !!d.connected,
    handle: d.handle,
    postCount: d.post_count ?? 0,
    memoryCount: d.memory_count ?? 0,
    syncing: !!d.syncing,
    lastSyncedAt: d.last_synced_at
  }
}

// No success_redirect_url is passed: Windows registers no URL scheme, so the
// backend's deep-link redirect is unreachable anyway — polling is the completion
// signal. The backend falls back to its default deep link, which just shows its
// "X connected" page in the browser.
export async function xOAuthUrl(session: XSession): Promise<{ authUrl?: string; error?: string }> {
  const d = await authedFetch<{ success?: boolean; auth_url?: string; error?: string }>(
    session,
    '/v1/x/oauth-url',
    'GET'
  )
  if (!d.success || !d.auth_url) return { error: d.error ?? 'unknown' }
  return { authUrl: d.auth_url }
}

export async function xSync(session: XSession): Promise<XSyncResult> {
  const d = await authedFetch<{
    success?: boolean
    new_posts?: number
    memories_created?: number
    error?: string
  }>(session, '/v1/x/sync', 'POST')
  return {
    success: !!d.success,
    newPosts: d.new_posts ?? 0,
    memoriesCreated: d.memories_created ?? 0,
    error: d.error
  }
}

export async function xDisconnect(session: XSession): Promise<void> {
  await authedFetch<{ success?: boolean }>(session, '/v1/x/disconnect', 'POST')
  setRun({ phase: 'idle', postCount: 0, memoryCount: 0, handle: undefined, error: undefined })
}

// The pure connect flow — all I/O injected so it unit-tests without net/timers.
// Reports state through onState; the real xConnect wires it to setRun/broadcast.
export async function runXConnectFlow(deps: {
  getOAuthUrl: () => Promise<{ authUrl?: string; error?: string }>
  getStatus: () => Promise<XStatus>
  openExternal: (url: string) => Promise<void>
  sleep: (ms: number) => Promise<void>
  onState: (patch: Partial<XRunState>) => void
  phase1?: { intervalMs: number; maxAttempts: number }
  phase2?: { intervalMs: number; maxAttempts: number }
}): Promise<void> {
  const p1 = deps.phase1 ?? PHASE1
  const p2 = deps.phase2 ?? PHASE2
  deps.onState({
    phase: 'connecting',
    postCount: 0,
    memoryCount: 0,
    handle: undefined,
    error: undefined
  })

  const { authUrl, error } = await deps.getOAuthUrl()
  if (error || !authUrl) {
    deps.onState({ phase: 'failed', error: error || 'no_auth_url' })
    return
  }
  if (!isAllowedXOAuthUrl(authUrl)) {
    deps.onState({ phase: 'failed', error: 'invalid_auth_url' })
    return
  }
  await deps.openExternal(authUrl)

  // Phase 1: sleep-first, poll until the account connects.
  let connected = false
  for (let i = 0; i < p1.maxAttempts; i++) {
    await deps.sleep(p1.intervalMs)
    try {
      const s = await deps.getStatus()
      if (s.connected) {
        connected = true
        deps.onState({ handle: s.handle, postCount: s.postCount, memoryCount: s.memoryCount })
        break
      }
    } catch {
      /* transient — keep polling */
    }
  }
  if (!connected) {
    deps.onState({ phase: 'failed', error: 'timeout' })
    return
  }

  // Phase 2: poll-first, watch the backend's first ingest drain (syncing → false),
  // surfacing the live post/memory counts.
  deps.onState({ phase: 'syncing' })
  for (let i = 0; i < p2.maxAttempts; i++) {
    try {
      const s = await deps.getStatus()
      deps.onState({ postCount: s.postCount, memoryCount: s.memoryCount, handle: s.handle })
      if (!s.syncing) {
        deps.onState({ phase: 'succeeded' })
        return
      }
    } catch {
      /* transient — keep polling */
    }
    await deps.sleep(p2.intervalMs)
  }
  // Connected but the sync flag never cleared within the window — still a success
  // from the user's view (the backend keeps ingesting server-side).
  deps.onState({ phase: 'succeeded' })
}

/**
 * Start an X connect run. Deduped: a call while a run is already connecting/syncing
 * is ignored (matches the runner's per-connector dedupe). Fire-and-forget — it
 * streams progress via the X_PROGRESS_CHANNEL and outlives the caller's panel.
 */
export function xConnect(session: XSession): void {
  if (runState.phase === 'connecting' || runState.phase === 'syncing') return
  void runXConnectFlow({
    getOAuthUrl: () => xOAuthUrl(session),
    getStatus: () => xStatus(session),
    openExternal: (url) => shell.openExternal(url),
    sleep,
    onState: setRun
  })
}
