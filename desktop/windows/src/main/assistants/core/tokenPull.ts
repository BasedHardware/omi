// Main-side of the token PULL channel (see core/session.ts "Pull-based token
// freshness"). Builds the TokenRefresher that session.ts calls when a main-process
// REST request needs a fresh Firebase token: it sends `session:tokenRequest` to the
// renderer that owns the auth session (the main window) and awaits its correlated
// `session:tokenResponse`, bounded by a timeout so a gone/hung renderer can never
// wedge the caller.
//
// The renderer side lives in renderer/src/lib/aiProfileHost.ts (respondTokenPull).
import { ipcMain, type IpcMainEvent, type WebContents } from 'electron'
import type { BackendSession } from './session'

// A request is outstanding only between send and reply/timeout; keyed by a
// monotonic id so a late reply from a timed-out pull can't resolve a newer one.
let nextRequestId = 1
const pending = new Map<number, (session: BackendSession | null) => void>()

// Bound the wait so a throttled/destroyed renderer settles the pull as "no token"
// rather than hanging the request that triggered it.
const PULL_TIMEOUT_MS = 8_000

let registered = false

/** Register the renderer→main reply handler exactly once (idempotent). */
function ensureRegistered(): void {
  if (registered) return
  registered = true
  ipcMain.on(
    'session:tokenResponse',
    (_e: IpcMainEvent, requestId: unknown, session: unknown): void => {
      if (typeof requestId !== 'number') return
      const resolve = pending.get(requestId)
      if (!resolve) return
      resolve(isSession(session) ? session : null)
    }
  )
}

/** Same shape check the aiProfile IPC handler uses — a well-formed session or null. */
function isSession(v: unknown): v is BackendSession {
  if (typeof v !== 'object' || v === null) return false
  const s = v as Record<string, unknown>
  return (
    typeof s.apiBase === 'string' &&
    typeof s.desktopApiBase === 'string' &&
    typeof s.token === 'string'
  )
}

/** Build the TokenRefresher for setTokenRefresher(). `getWebContents` returns the
 *  window that owns the Firebase session (read lazily so a re-created main window is
 *  always the current target). Resolves null on no-window / timeout — session.ts
 *  treats null as "no refresh available" and keeps the cached session. */
export function makeRendererTokenRefresher(
  getWebContents: () => WebContents | null
): () => Promise<BackendSession | null> {
  ensureRegistered()
  return () =>
    new Promise<BackendSession | null>((resolve) => {
      const wc = getWebContents()
      if (!wc || wc.isDestroyed()) {
        resolve(null)
        return
      }
      const requestId = nextRequestId++
      let settled = false
      const done = (session: BackendSession | null): void => {
        if (settled) return
        settled = true
        pending.delete(requestId)
        clearTimeout(timer)
        resolve(session)
      }
      const timer = setTimeout(() => done(null), PULL_TIMEOUT_MS)
      pending.set(requestId, done)
      try {
        wc.send('session:tokenRequest', requestId)
      } catch {
        done(null)
      }
    })
}
