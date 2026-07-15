import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

// Mock analytics so we can assert the degraded-fallback telemetry without pulling
// in firebase.ts (which builds `auth` at import time).
const trackEvent = vi.fn()
vi.mock('./analytics', () => ({ trackEvent }))

// The internal Firebase persistence contract we implement (cast away the public
// `Persistence` type the module exports).
type PersistenceValue = Record<string, unknown> | string
type StorageEventListener = (value: PersistenceValue | null) => void
interface Internal {
  type: string
  _shouldAllowMigration: boolean
  _isAvailable(): Promise<boolean>
  _set(key: string, value: PersistenceValue): Promise<void>
  _get<T extends PersistenceValue>(key: string): Promise<T | null>
  _remove(key: string): Promise<void>
  _addListener(key: string, listener: StorageEventListener): void
  _removeListener(key: string, listener: StorageEventListener): void
}

// A fake main-process authStore bridge backed by an in-memory map, exposing a
// `fire(key)` hook so tests can simulate a cross-window authStore:changed event.
function makeFakeBridge() {
  const map = new Map<string, string>()
  const changeCbs = new Set<(key: string) => void>()
  let available = true
  const api = {
    isAvailable: vi.fn(async () => available),
    get: vi.fn(async (k: string) => (map.has(k) ? map.get(k)! : null)),
    set: vi.fn(async (k: string, v: string) => {
      map.set(k, v)
    }),
    remove: vi.fn(async (k: string) => {
      map.delete(k)
    }),
    onChanged: vi.fn((cb: (key: string) => void) => {
      changeCbs.add(cb)
      return () => changeCbs.delete(cb)
    })
  }
  return {
    map,
    api,
    setAvailable: (v: boolean) => {
      available = v
    },
    fire: (key: string) => {
      for (const cb of changeCbs) cb(key)
    }
  }
}

// A minimal localStorage stub (tests run in the `node` environment).
function makeFakeLocalStorage(initial: Record<string, string> = {}) {
  const map = new Map<string, string>(Object.entries(initial))
  return {
    get length(): number {
      return map.size
    },
    key: (i: number): string | null => [...map.keys()][i] ?? null,
    getItem: (k: string): string | null => (map.has(k) ? map.get(k)! : null),
    setItem: (k: string, v: string): void => {
      map.set(k, v)
    },
    removeItem: (k: string): void => {
      map.delete(k)
    },
    _map: map
  }
}

let fake: ReturnType<typeof makeFakeBridge>

async function load(): Promise<{
  persistence: Internal
  scrub: () => Promise<void>
}> {
  vi.resetModules()
  const mod = await import('./encryptedAuthPersistence')
  return {
    persistence: mod.encryptedAuthPersistence as unknown as Internal,
    scrub: mod.scrubLegacyPlaintextAuth
  }
}

beforeEach(() => {
  trackEvent.mockClear()
  fake = makeFakeBridge()
  ;(globalThis as unknown as { window: unknown }).window = { omi: { authStore: fake.api } }
})

afterEach(() => {
  delete (globalThis as unknown as { window?: unknown }).window
  delete (globalThis as unknown as { localStorage?: unknown }).localStorage
})

const KEY = 'firebase:authUser:AIzaTest:[DEFAULT]'

describe('encryptedAuthPersistence', () => {
  it('declares LOCAL type and opts into migration', async () => {
    const { persistence } = await load()
    expect(persistence.type).toBe('LOCAL')
    // Without this Firebase never migrates the plaintext session in / deletes it.
    expect(persistence._shouldAllowMigration).toBe(true)
  })

  it('_set → _get round-trips an object value (JSON over the bridge)', async () => {
    const { persistence } = await load()
    const value = { uid: 'u1', stsTokenManager: { accessToken: 'id-tok' } }
    await persistence._set(KEY, value)
    // Stored over the bridge as a JSON string, not the live object.
    expect(fake.api.set).toHaveBeenCalledWith(KEY, JSON.stringify(value))
    expect(await persistence._get(KEY)).toEqual(value)
  })

  it('_get returns null for an unset key', async () => {
    const { persistence } = await load()
    expect(await persistence._get('missing')).toBeNull()
  })

  it('_isAvailable false → returns false and emits degraded fallback once', async () => {
    fake.setAvailable(false)
    const { persistence } = await load()
    expect(await persistence._isAvailable()).toBe(false)
    // No throw; degraded telemetry emitted exactly once even across repeat calls.
    expect(await persistence._isAvailable()).toBe(false)
    expect(trackEvent).toHaveBeenCalledTimes(1)
    expect(trackEvent).toHaveBeenCalledWith('fallback_triggered', {
      component: 'auth_persistence',
      from: 'encrypted',
      to: 'plaintext',
      reason: 'safe_storage_unavailable',
      outcome: 'degraded'
    })
  })

  it('_isAvailable true → no fallback telemetry', async () => {
    const { persistence } = await load()
    expect(await persistence._isAvailable()).toBe(true)
    expect(trackEvent).not.toHaveBeenCalled()
  })

  it('_remove clears the entry', async () => {
    const { persistence } = await load()
    await persistence._set(KEY, { uid: 'u1' })
    await persistence._remove(KEY)
    expect(fake.api.remove).toHaveBeenCalledWith(KEY)
    expect(await persistence._get(KEY)).toBeNull()
  })

  it('_addListener fires with the new value on authStore:changed', async () => {
    const { persistence } = await load()
    const listener = vi.fn()
    persistence._addListener(KEY, listener)
    await persistence._set(KEY, { uid: 'u2' })
    fake.fire(KEY)
    // The change callback re-reads asynchronously; let microtasks flush.
    await Promise.resolve()
    await Promise.resolve()
    expect(listener).toHaveBeenCalledWith({ uid: 'u2' })
  })

  it('_removeListener stops delivery', async () => {
    const { persistence } = await load()
    const listener = vi.fn()
    persistence._addListener(KEY, listener)
    persistence._removeListener(KEY, listener)
    await persistence._set(KEY, { uid: 'u3' })
    fake.fire(KEY)
    await Promise.resolve()
    await Promise.resolve()
    expect(listener).not.toHaveBeenCalled()
  })

  describe('scrubLegacyPlaintextAuth', () => {
    it('removes a plaintext key ONLY when the encrypted store holds it', async () => {
      const ls = makeFakeLocalStorage({
        [KEY]: 'plaintext-user-blob',
        'unrelated:key': 'keep-me'
      })
      ;(globalThis as unknown as { localStorage: unknown }).localStorage = ls
      // Encrypted store already holds KEY → the plaintext copy is safe to drop.
      fake.map.set(KEY, JSON.stringify({ uid: 'u1' }))
      const { scrub } = await load()
      await scrub()
      expect(ls.getItem(KEY)).toBeNull()
      expect(ls.getItem('unrelated:key')).toBe('keep-me')
    })

    it('keeps a plaintext key that is NOT yet in the encrypted store', async () => {
      const ls = makeFakeLocalStorage({ [KEY]: 'plaintext-user-blob' })
      ;(globalThis as unknown as { localStorage: unknown }).localStorage = ls
      // Encrypted store empty (migration hasn't happened) → must NOT delete.
      const { scrub } = await load()
      await scrub()
      expect(ls.getItem(KEY)).toBe('plaintext-user-blob')
    })
  })
})
