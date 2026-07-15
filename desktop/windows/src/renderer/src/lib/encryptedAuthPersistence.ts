// A custom Firebase Auth Persistence that stores the session (ID + refresh
// tokens) ENCRYPTED at rest via the main process (safeStorage/DPAPI), instead of
// Firebase's default plaintext localStorage.
//
// How it plugs in: firebase.ts passes `[encryptedAuthPersistence,
// browserLocalPersistence]` to initializeAuth. Firebase's PersistenceUserManager
// auto-migrates on init — it finds an existing plaintext user in browserLocal,
// re-`_set`s it into THIS (encrypted) persistence, and `_remove`s the plaintext
// copy. Readers (auth.currentUser.getIdToken()) are untouched.
//
// CRITICAL: `_shouldAllowMigration = true`. Firebase only migrates INTO a
// persistence that opts in (see persistence_user_manager: migrationHierarchy =
// availablePersistences.filter(p => p._shouldAllowMigration)); without it the
// plaintext copy is never moved or deleted and this whole feature is inert.
//
// DEGRADATION: on a machine with no OS encryption, `_isAvailable()` returns false,
// Firebase drops this persistence from the hierarchy, and the session falls
// through to browserLocalPersistence (plaintext) — the user is never locked out.
// We emit fallback telemetry once when that happens.

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

// Per-key listener sets. A single bridge subscription fans authStore:changed out
// to them, re-reading the (decrypted) value so listeners see the new state —
// mirroring how browserLocalPersistence reacts to cross-tab storage events.
const listeners = new Map<string, Set<StorageEventListener>>()
let unsubscribeChanged: (() => void) | null = null

function ensureChangeSubscription(): void {
  if (unsubscribeChanged) return
  const api = bridge()
  if (!api) return
  unsubscribeChanged = api.onChanged((key) => {
    const set = listeners.get(key)
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

const impl: PersistenceInternal = {
  type: 'LOCAL',
  _shouldAllowMigration: true,

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
  },

  async _set(key: string, value: PersistenceValue): Promise<void> {
    const api = bridge()
    if (!api) throw new Error('authStore bridge unavailable')
    await api.set(key, JSON.stringify(value))
  },

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
  },

  async _remove(key: string): Promise<void> {
    const api = bridge()
    if (!api) return
    await api.remove(key)
  },

  _addListener(key: string, listener: StorageEventListener): void {
    ensureChangeSubscription()
    let set = listeners.get(key)
    if (!set) {
      set = new Set()
      listeners.set(key, set)
    }
    set.add(listener)
  },

  _removeListener(key: string, listener: StorageEventListener): void {
    const set = listeners.get(key)
    if (!set) return
    set.delete(listener)
    if (set.size === 0) listeners.delete(key)
  }
}

/** The persistence to pass to initializeAuth. Cast to the public type. */
export const encryptedAuthPersistence = impl as unknown as Persistence

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
