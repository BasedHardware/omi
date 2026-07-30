// Main-side session store for the pi-mono managed-cloud chat harness.
//
// pi-mono needs a Firebase ID token as OMI_API_KEY at subprocess spawn, but on
// Windows (unlike macOS) the Firebase session lives ONLY in the renderer — main
// never holds one. This module is the main-process end of the renderer→main
// token relay (`renderer/src/lib/piMonoAuthHost.ts`): it holds the relayed
// session INERT until the renderer pushes one, exposes it for the adapter to
// read at spawn, and — when a token refresh arrives while a pi subprocess is
// live — drives the adapter's restart.
//
// Same shape and same reason for existing as `rewind/embeddingService.ts`'s
// `configureRewindEmbedSession` and `aiUserProfile`'s session relay.
//
// DARK: nothing registers an adapter yet (that arrives in PR-D), so the refresh
// hand-off is a no-op until then; the store simply caches the latest session.
//
// SECURITY: the token is a live ~1h credential. It is kept in-memory only
// (never persisted to disk), and never logged.
import { byokEnvVars } from '../../shared/byok'
import { ByokKeyStore } from '../agentKernel/byokStore'

/** The relayed Firebase session the adapter reads at spawn. */
export interface PiMonoSession {
  /** Firebase ID token → the subprocess's OMI_API_KEY (raw, no `Bearer`). */
  token: string
  /** Omi API base the renderer resolved (VITE_OMI_DESKTOP_API_BASE). */
  desktopApiBase: string
}

/**
 * The narrow slice of the pi-mono adapter this store drives on a token refresh.
 * The PR-A `PiMonoAdapter` satisfies it; declaring the seam here (rather than
 * importing the adapter) keeps the store decoupled and lets PR-D decide which
 * instance to register.
 */
export interface PiMonoAuthTarget {
  /** Rotate the subprocess's auth token — restarts when idle, defers otherwise.
   *  Returns true if the restart happened immediately, false if deferred. */
  updateAuthToken(token: string): Promise<boolean>
}

let session: PiMonoSession | null = null
let adapter: PiMonoAuthTarget | null = null
// Lazily constructed so this module stays import-pure (ByokKeyStore's default
// constructor calls app.getPath, which isn't ready at import time). Injectable
// for tests via __setByokKeyStoreForTests.
let byokStore: ByokKeyStore | null = null

function getByokStore(): ByokKeyStore {
  if (!byokStore) byokStore = new ByokKeyStore()
  return byokStore
}

/** Coerce an untrusted IPC payload to a valid session, or null. Both fields must
 *  be non-empty strings; anything else clears the session. */
function coerce(next: unknown): PiMonoSession | null {
  if (!next || typeof next !== 'object') return null
  const { token, desktopApiBase } = next as Record<string, unknown>
  if (typeof token !== 'string' || !token) return null
  if (typeof desktopApiBase !== 'string' || !desktopApiBase) return null
  return { token, desktopApiBase }
}

/**
 * Store (or clear, on sign-out) the session relayed from the renderer. Called by
 * the `pimono:setSession` IPC handler on sign-in and on every id-token refresh
 * (~hourly).
 *
 * When a NEW token arrives (a refresh or a switch) and an adapter is currently
 * registered — i.e. a pi subprocess is live — hand the fresh token to the
 * adapter so it restarts (when idle) or defers the restart until the in-flight
 * prompt finishes. While dark (no adapter registered) this is a pure cache
 * update. Sign-out just clears the cache; tearing down a live subprocess is the
 * adapter lifecycle's job (PR-D), not this relay's.
 */
export function configurePiMonoSession(next: unknown): void {
  const valid = coerce(next)
  const prevToken = session?.token
  session = valid

  if (valid && adapter && valid.token !== prevToken) {
    const target = adapter
    // Fire-and-forget: the IPC caller must not block on a subprocess restart,
    // and a restart failure must not reject into the renderer. Never logs the token.
    void target.updateAuthToken(valid.token).catch((e) => {
      console.warn('[pi-mono-session] token refresh restart failed', (e as Error).message)
    })
  }
}

/** The current session, or null when signed out / never relayed. The adapter
 *  reads this at spawn; PR-D must refuse to start pi-mono when it is null. */
export function getPiMonoSession(): PiMonoSession | null {
  return session
}

/**
 * The managed-cloud OMI chat API base for the pi subprocess → its
 * `OMI_API_BASE_URL`. The relayed `desktopApiBase` is intentionally version-less
 * (siblings append their own version — `${desktopApiBase}/v2/chat/completions` in
 * aiUserProfile/service.ts, `${desktopApiBase}/v1/...` in rewind/embeddingClient.ts).
 * pi-mono's managed `openai-completions` provider needs the `/v2` segment baked in,
 * because the OpenAI SDK resolves `<base>/chat/completions` — without `/v2` every
 * request 404s at `.../chat/completions` instead of `.../v2/chat/completions`.
 * Trailing-slash safe. BYOK requests reuse this same base (they differ only by
 * added `X-BYOK-*` headers), so `/v2` is correct for managed and BYOK alike.
 */
export function piMonoManagedApiBaseUrl(session: PiMonoSession): string {
  return `${session.desktopApiBase.replace(/\/+$/, '')}/v2`
}

/**
 * The `OMI_BYOK_*` env set to inject into the pi subprocess, or `{}` when the
 * user does not have all four BYOK keys. All-or-nothing (see `byokEnvVars`).
 * Independent of the Firebase session: managed OMI_API_KEY is always the token.
 */
export function getPiMonoByokEnv(): Record<string, string> {
  return byokEnvVars(getByokStore().getAllKeys())
}

/** Register the live adapter instance so a subsequent token refresh can restart
 *  it. PR-D calls this when a pi-mono binding opens. Only one is tracked at a
 *  time (pi-mono pins a single worker). */
export function registerPiMonoAdapter(target: PiMonoAuthTarget): void {
  adapter = target
}

/** Drop the registered adapter (its subprocess is gone). Idempotent, and a
 *  no-op if a different instance is now registered. */
export function unregisterPiMonoAdapter(target: PiMonoAuthTarget): void {
  if (adapter === target) adapter = null
}

/** Test seam: reset all module state. */
export function __resetPiMonoSessionForTests(): void {
  session = null
  adapter = null
  byokStore = null
}

/** Test seam: inject a ByokKeyStore so BYOK-env tests need no Electron safeStorage. */
export function __setByokKeyStoreForTests(store: ByokKeyStore | null): void {
  byokStore = store
}
