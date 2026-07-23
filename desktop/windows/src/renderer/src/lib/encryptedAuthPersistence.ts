// A custom Firebase Auth Persistence that stores the session (ID + refresh
// tokens) ENCRYPTED at rest via the main process (safeStorage/DPAPI), instead of
// Firebase's default plaintext localStorage.
//
// How it plugs in: firebase.ts passes `[EncryptedAuthPersistence,
// inMemoryPersistence]` to initializeAuth. Existing legacy plaintext sessions
// are scrubbed during startup; new sessions never persist without DPAPI.
//
// CRITICAL — this MUST be a CLASS, not a plain object. Firebase's `_getInstance`
// asserts `cls instanceof Function` ("Expected a class definition") and constructs
// ONE cached instance via `new`. A plain object throws an INTERNAL ASSERTION at
// init and Firebase silently falls back to getAuth's default (IndexedDB) — the
// encrypted store is never used. Mirror the shape of Firebase's own
// BrowserLocalPersistence: a class with a static `type` plus instance fields.
//
// CRITICAL: `_shouldAllowMigration = true`. Firebase only migrates INTO a
// persistence that opts in (see persistence_user_manager: migrationHierarchy =
// availablePersistences.filter(p => p._shouldAllowMigration)); without it the
// plaintext copy is never moved or deleted and this whole feature is inert.
//
// DEGRADATION: on a machine with no OS encryption, `_isAvailable()` returns false
// and Firebase falls through to memory-only persistence. The current session
// works, but the user signs in again after restart. We emit telemetry once.

import type { Persistence } from 'firebase/auth'
import { trackEvent } from './analytics'

// The internal contract Firebase actually calls (not exported publicly, but
// stable — verified against @firebase/auth v12 core/persistence). We implement it
// and cast to the public `Persistence` type when handing it to initializeAuth.
type PersistenceValue = Record<string, unknown> | string
type StorageEventListener = (value: PersistenceValue | null) => void

interface PersistenceInternal {
  type: 'LOCAL'
  _shouldAllowMigration: boolean
  _isAvailable(): Promise<boolean>
  _set(key: string, value: PersistenceValue): Promise<void>
  _get<T extends PersistenceValue>(key: string): Promise<T | null>
  _remove(key: string): Promise<void>
  _addListener(key: string, listener: StorageEventListener): void
  _removeListener(key: string, listener: StorageEventListener): void
}

// Access the bridge lazily per-call so tests can inject a fake `window.omi`.
function bridge(): NonNullable<typeof window.omi>['authStore'] | null {
  if (typeof window === 'undefined') return null
  return window.omi?.authStore ?? null
}

let fallbackEmitted = false
function emitDegradedFallbackOnce(reason: string): void {
  if (fallbackEmitted) return
  fallbackEmitted = true
  // Established Windows idiom (no renderer recordFallback wrapper): a
  // trackEvent('fallback_triggered', …) with the shared fallback field shape.
  trackEvent('fallback_triggered', {
    component: 'auth_persistence',
    from: 'encrypted',
    to: 'plaintext',
    reason,
    outcome: 'degraded'
  })
}

// Firebase constructs ONE instance of this class (cached by `_getInstance`) and
// calls its methods. Mirrors BrowserLocalPersistence: static `type` for the
// pre-instantiation type check, instance `type` + `_shouldAllowMigration`, and the
// PersistenceInternal method surface.
class EncryptedAuthPersistence implements PersistenceInternal {
  static type = 'LOCAL' as const
  readonly type = 'LOCAL' as const
  readonly _shouldAllowMigration = true

  // Per-key listener sets. A single bridge subscription fans authStore:changed out
  // to them, re-reading the (decrypted) value so listeners see the new state —
  // mirroring how browserLocalPersistence reacts to cross-tab storage events.
  private readonly listeners = new Map<string, Set<StorageEventListener>>()
  private unsubscribeChanged: (() => void) | null = null

  private ensureChangeSubscription(): void {
    if (this.unsubscribeChanged) return
    const api = bridge()
    if (!api) return
    this.unsubscribeChanged = api.onChanged((key) => {
      const set = this.listeners.get(key)
      if (!set || set.size === 0) return
      void (async () => {
        let value: PersistenceValue | null = null
        try {
          const raw = await api.get(key)
          value = raw != null ? (JSON.parse(raw) as PersistenceValue) : null
        } catch {
          value = null
        }
        for (const listener of set) listener(value)
      })()
    })
  }

  async _isAvailable(): Promise<boolean> {
    const api = bridge()
    if (!api) return false
    try {
      const ok = await api.isAvailable()
      if (!ok) emitDegradedFallbackOnce('safe_storage_unavailable')
      return ok
    } catch {
      emitDegradedFallbackOnce('bridge_error')
      return false
    }
  }

  async _set(key: string, value: PersistenceValue): Promise<void> {
    const api = bridge()
    if (!api) throw new Error('authStore bridge unavailable')
    await api.set(key, JSON.stringify(value))
  }

  async _get<T extends PersistenceValue>(key: string): Promise<T | null> {
    const api = bridge()
    if (!api) return null
    const raw = await api.get(key)
    if (raw == null) return null
    try {
      return JSON.parse(raw) as T
    } catch {
      return null
    }
  }

  async _remove(key: string): Promise<void> {
    const api = bridge()
    if (!api) return
    await api.remove(key)
  }

  _addListener(key: string, listener: StorageEventListener): void {
    this.ensureChangeSubscription()
    let set = this.listeners.get(key)
    if (!set) {
      set = new Set()
      this.listeners.set(key, set)
    }
    set.add(listener)
  }

  _removeListener(key: string, listener: StorageEventListener): void {
    const set = this.listeners.get(key)
    if (!set) return
    set.delete(listener)
    if (set.size === 0) this.listeners.delete(key)
  }
}

/**
 * The persistence to pass to initializeAuth. This is the CLASS itself (not an
 * instance) — Firebase's `_getInstance` requires a constructor and news it once.
 * Cast to the public `Persistence` type the SDK expects in its config.
 */
export const encryptedAuthPersistence = EncryptedAuthPersistence as unknown as Persistence

/**
 * Belt-and-suspenders plaintext scrub. Firebase's persistence array already
 * migrates the session into the encrypted store and removes the plaintext copy on
 * init, but a window that loaded pre-migration (or a partial write) could leave a
 * lingering `firebase:authUser:*` localStorage key. Delete any such key ONLY when
 * the encrypted store already holds that exact key — so a session that hasn't been
 * migrated yet is never destroyed. Best-effort; never throws.
 */
export async function scrubLegacyPlaintextAuth(): Promise<void> {
  const api = bridge()
  if (!api || typeof localStorage === 'undefined') return
  try {
    const candidates: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key && key.startsWith('firebase:authUser:')) candidates.push(key)
    }
    for (const key of candidates) {
      // Only clear the plaintext copy once the encrypted store demonstrably holds
      // the same key — otherwise we'd be deleting a not-yet-migrated session.
      const encrypted = await api.get(key)
      if (encrypted != null) localStorage.removeItem(key)
    }
  } catch {
    /* best-effort — never block boot on a scrub failure */
  }
}
