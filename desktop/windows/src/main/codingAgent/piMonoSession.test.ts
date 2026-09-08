// The pi-mono session store is the main-process end of the renderer→main token
// relay: inert until pushed, exposes the session for the adapter to read at
// spawn, and drives the adapter's restart on a token refresh. These tests pin
// that contract, including the DARK case (no adapter registered → no-op) and the
// BYOK all-or-nothing env split.
import { describe, it, expect, beforeEach, afterAll, vi } from 'vitest'
import { mkdtempSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

const dir = mkdtempSync(join(tmpdir(), 'pimono-session-test-'))

// Identity-ish safeStorage + temp userData so ByokKeyStore round-trips without
// real DPAPI (mirrors byokStore.test.ts).
vi.mock('electron', () => ({
  app: { getPath: (): string => dir },
  safeStorage: {
    isEncryptionAvailable: (): boolean => true,
    encryptString: (s: string): Buffer => Buffer.from(s, 'utf8'),
    decryptString: (b: Buffer): string => b.toString('utf8')
  },
  BrowserWindow: { getAllWindows: (): unknown[] => [] },
  ipcMain: { on: (): void => {}, handle: (): void => {} },
  webContents: { getAllWebContents: (): unknown[] => [] }
}))

import { ByokKeyStore } from '../agentKernel/byokStore'
import {
  configurePiMonoSession,
  getPiMonoSession,
  getPiMonoByokEnv,
  piMonoManagedApiBaseUrl,
  registerPiMonoAdapter,
  unregisterPiMonoAdapter,
  ensureFreshPiMonoSession,
  notifyPiMonoByokChanged,
  resolvePiMonoSpawnCredentials,
  __resetPiMonoSessionForTests,
  __setByokKeyStoreForTests,
  type PiMonoAuthTarget
} from './piMonoSession'

afterAll(() => rmSync(dir, { recursive: true, force: true }))

/** A fake adapter recording credential-restart calls. */
function fakeAdapter(): PiMonoAuthTarget & {
  updateAuthToken: ReturnType<typeof vi.fn>
  updateByokEnv: ReturnType<typeof vi.fn>
  revokeAndStop: ReturnType<typeof vi.fn>
} {
  return {
    updateAuthToken: vi.fn(async () => true),
    updateByokEnv: vi.fn(async () => true),
    revokeAndStop: vi.fn(async () => {})
  }
}

const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0))

beforeEach(() => {
  __resetPiMonoSessionForTests()
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})

describe('configurePiMonoSession / getPiMonoSession', () => {
  it('is inert until pushed (null by default — PR-D must gate on this)', () => {
    expect(getPiMonoSession()).toBeNull()
  })

  it('stores a pushed session for the adapter to read at spawn', () => {
    configurePiMonoSession({ token: 'tok-1', desktopApiBase: 'https://api.example/v2' })
    expect(getPiMonoSession()).toEqual({ token: 'tok-1', desktopApiBase: 'https://api.example/v2' })
  })

  it('clears the session on sign-out (null push)', () => {
    configurePiMonoSession({ token: 'tok-1', desktopApiBase: 'https://api.example/v2' })
    configurePiMonoSession(null)
    expect(getPiMonoSession()).toBeNull()
  })

  it('stops the live adapter on sign-out so a later spawn cannot reuse the departed token', async () => {
    const adapter = fakeAdapter()
    registerPiMonoAdapter(adapter)
    configurePiMonoSession({ token: 'tok-1', desktopApiBase: 'https://api.example/v2' })
    adapter.updateAuthToken.mockClear()
    adapter.revokeAndStop.mockClear()

    configurePiMonoSession(null)
    await flush()

    expect(getPiMonoSession()).toBeNull()
    expect(adapter.revokeAndStop).toHaveBeenCalledTimes(1)
    expect(adapter.updateAuthToken).not.toHaveBeenCalled()
  })

  it('rejects a malformed payload (missing/blank fields → null)', () => {
    configurePiMonoSession({ token: '', desktopApiBase: 'https://api.example/v2' })
    expect(getPiMonoSession()).toBeNull()
    configurePiMonoSession({ token: 'tok', desktopApiBase: '' })
    expect(getPiMonoSession()).toBeNull()
    configurePiMonoSession({ token: 42, desktopApiBase: 'https://x' })
    expect(getPiMonoSession()).toBeNull()
    configurePiMonoSession('not-an-object')
    expect(getPiMonoSession()).toBeNull()
  })
})

describe('token refresh → adapter restart', () => {
  it('drives updateAuthToken when a new token arrives with an adapter registered', async () => {
    const adapter = fakeAdapter()
    registerPiMonoAdapter(adapter)

    configurePiMonoSession({ token: 'tok-1', desktopApiBase: 'https://api.example/v2' })
    configurePiMonoSession({ token: 'tok-2', desktopApiBase: 'https://api.example/v2' })
    await flush()

    // tok-1 arrives with no prior token → pushes; tok-2 is the refresh → pushes.
    expect(adapter.updateAuthToken).toHaveBeenCalledTimes(2)
    expect(adapter.updateAuthToken).toHaveBeenLastCalledWith('tok-2')
  })

  it('does NOT restart when the same token is re-pushed (avoid needless restarts)', async () => {
    const adapter = fakeAdapter()
    registerPiMonoAdapter(adapter)

    configurePiMonoSession({ token: 'tok-1', desktopApiBase: 'https://api.example/v2' })
    configurePiMonoSession({ token: 'tok-1', desktopApiBase: 'https://api.example/v2' })
    await flush()

    expect(adapter.updateAuthToken).toHaveBeenCalledTimes(1)
  })

  it('is DARK — no adapter registered means no restart, just a cache update', async () => {
    // No registerPiMonoAdapter call.
    configurePiMonoSession({ token: 'tok-1', desktopApiBase: 'https://api.example/v2' })
    configurePiMonoSession({ token: 'tok-2', desktopApiBase: 'https://api.example/v2' })
    await flush()
    // Nothing to assert on the adapter (none exists); the session is simply cached.
    expect(getPiMonoSession()).toMatchObject({ token: 'tok-2' })
  })

  it('does not push to an unregistered adapter', async () => {
    const adapter = fakeAdapter()
    registerPiMonoAdapter(adapter)
    unregisterPiMonoAdapter(adapter)

    configurePiMonoSession({ token: 'tok-1', desktopApiBase: 'https://api.example/v2' })
    await flush()
    expect(adapter.updateAuthToken).not.toHaveBeenCalled()
  })

  it('unregister is scoped — a newer adapter is not dropped by an older one', async () => {
    const a = fakeAdapter()
    const b = fakeAdapter()
    registerPiMonoAdapter(a)
    registerPiMonoAdapter(b)
    unregisterPiMonoAdapter(a) // stale unregister must not detach b

    configurePiMonoSession({ token: 'tok-1', desktopApiBase: 'https://api.example/v2' })
    await flush()
    expect(b.updateAuthToken).toHaveBeenCalledWith('tok-1')
    expect(a.updateAuthToken).not.toHaveBeenCalled()
  })

  it('swallows a restart failure (must never reject into the IPC caller)', async () => {
    const adapter: PiMonoAuthTarget = {
      updateAuthToken: vi.fn(async () => {
        throw new Error('spawn failed')
      }),
      updateByokEnv: vi.fn(async () => true),
      revokeAndStop: vi.fn(async () => {})
    }
    registerPiMonoAdapter(adapter)

    expect(() =>
      configurePiMonoSession({ token: 'tok-1', desktopApiBase: 'https://api.example/v2' })
    ).not.toThrow()
    await flush()
    expect(console.warn).toHaveBeenCalled()
  })
})

describe('piMonoManagedApiBaseUrl (adds the /v2 segment the OpenAI SDK needs)', () => {
  // Regression: VITE_OMI_DESKTOP_API_BASE is a BARE host (no /v2), unlike the
  // already-/v2 base macOS passes. Without this the pi extension's
  // openai-completions provider requests `<host>/chat/completions` (404) instead
  // of `<host>/v2/chat/completions`. Sibling consumers (aiUserProfile, rewind)
  // append their own version to the same bare base, so this must stay version-less
  // at the source and only pi-mono's managed base gets /v2.
  it('appends /v2 to a bare host', () => {
    expect(
      piMonoManagedApiBaseUrl({
        token: 't',
        desktopApiBase: 'https://desktop-backend-hhibjajaja-uc.a.run.app'
      })
    ).toBe('https://desktop-backend-hhibjajaja-uc.a.run.app/v2')
  })

  it('collapses a trailing slash rather than producing //v2', () => {
    expect(piMonoManagedApiBaseUrl({ token: 't', desktopApiBase: 'https://api.omi.me/' })).toBe(
      'https://api.omi.me/v2'
    )
  })
})

describe('getPiMonoByokEnv (capability-scoped, separate from the Firebase session)', () => {
  it('injects the complete OMI_BYOK_* set when all four keys are stored', () => {
    const store = new ByokKeyStore(
      join(dir, `byok-full-${Math.random().toString(36).slice(2)}.json`)
    )
    store.setKey('openai', 'sk-openai')
    store.setKey('anthropic', 'sk-ant')
    store.setKey('gemini', 'gm-key')
    store.setKey('deepgram', 'dg-key')
    __setByokKeyStoreForTests(store)

    expect(getPiMonoByokEnv()).toEqual({
      OMI_BYOK_OPENAI: 'sk-openai',
      OMI_BYOK_ANTHROPIC: 'sk-ant',
      OMI_BYOK_GEMINI: 'gm-key',
      OMI_BYOK_DEEPGRAM: 'dg-key'
    })
  })

  it('returns configured keys without requiring an unrelated Deepgram key', () => {
    const store = new ByokKeyStore(
      join(dir, `byok-partial-${Math.random().toString(36).slice(2)}.json`)
    )
    store.setKey('openai', 'sk-openai')
    store.setKey('anthropic', 'sk-ant')
    store.setKey('gemini', 'gm-key')
    __setByokKeyStoreForTests(store)

    expect(getPiMonoByokEnv()).toEqual({
      OMI_BYOK_OPENAI: 'sk-openai',
      OMI_BYOK_ANTHROPIC: 'sk-ant',
      OMI_BYOK_GEMINI: 'gm-key'
    })
  })

  it('is independent of the Firebase session (empty even with a live session)', () => {
    const store = new ByokKeyStore(
      join(dir, `byok-none-${Math.random().toString(36).slice(2)}.json`)
    )
    __setByokKeyStoreForTests(store)
    configurePiMonoSession({ token: 'tok-1', desktopApiBase: 'https://api.example/v2' })
    expect(getPiMonoByokEnv()).toEqual({})
  })
})

describe('ensureFreshPiMonoSession (renderer pull, in-place, no restart)', () => {
  it('is a no-op when no session is cached', async () => {
    expect(await ensureFreshPiMonoSession()).toBeNull()
  })

  it('keeps the cached session when no refresher is wired', async () => {
    configurePiMonoSession({ token: 'stale', desktopApiBase: 'https://desktop.example' })
    expect(await ensureFreshPiMonoSession()).toMatchObject({ token: 'stale' })
  })

  it('swaps in a pulled token without restarting the adapter', async () => {
    const { setTokenRefresher } = await import('../assistants/core/session')
    configurePiMonoSession({ token: 'stale', desktopApiBase: 'https://desktop.example' })
    const adapter = fakeAdapter()
    registerPiMonoAdapter(adapter)
    adapter.updateAuthToken.mockClear()

    setTokenRefresher(async () => ({
      apiBase: 'https://api.example',
      desktopApiBase: 'https://desktop.example',
      token: 'fresh'
    }))
    try {
      const next = await ensureFreshPiMonoSession()
      expect(next?.token).toBe('fresh')
      expect(getPiMonoSession()?.token).toBe('fresh')
      expect(adapter.updateAuthToken).not.toHaveBeenCalled()
    } finally {
      setTokenRefresher(null)
    }
  })

  it('resolvePiMonoSpawnCredentials force-refreshes and re-reads BYOK', async () => {
    const { setTokenRefresher } = await import('../assistants/core/session')
    const store = new ByokKeyStore(
      join(dir, `byok-resolve-${Math.random().toString(36).slice(2)}.json`)
    )
    store.setKey('openai', 'sk-openai')
    store.setKey('anthropic', 'sk-ant')
    store.setKey('gemini', 'gm-key')
    store.setKey('deepgram', 'dg-key')
    __setByokKeyStoreForTests(store)
    configurePiMonoSession({ token: 'stale', desktopApiBase: 'https://desktop.example' })
    setTokenRefresher(async () => ({
      apiBase: 'https://api.example',
      desktopApiBase: 'https://desktop.example',
      token: 'fresh'
    }))
    try {
      const creds = await resolvePiMonoSpawnCredentials()
      expect(creds).toMatchObject({
        authToken: 'fresh',
        omiApiBaseUrl: 'https://desktop.example/v2',
        byokEnv: {
          OMI_BYOK_OPENAI: 'sk-openai',
          OMI_BYOK_ANTHROPIC: 'sk-ant',
          OMI_BYOK_GEMINI: 'gm-key',
          OMI_BYOK_DEEPGRAM: 'dg-key'
        }
      })
    } finally {
      setTokenRefresher(null)
    }
  })

  it('does not resurrect a session that was cleared during the pull', async () => {
    const { setTokenRefresher } = await import('../assistants/core/session')
    configurePiMonoSession({ token: 'stale', desktopApiBase: 'https://desktop.example' })
    let resolvePull!: (
      v: {
        apiBase: string
        desktopApiBase: string
        token: string
      } | null
    ) => void
    setTokenRefresher(
      () =>
        new Promise((r) => {
          resolvePull = r
        })
    )
    try {
      const pending = ensureFreshPiMonoSession()
      configurePiMonoSession(null)
      resolvePull({
        apiBase: 'https://api.example',
        desktopApiBase: 'https://desktop.example',
        token: 'late'
      })
      expect(await pending).toBeNull()
      expect(getPiMonoSession()).toBeNull()
    } finally {
      setTokenRefresher(null)
    }
  })
})

describe('notifyPiMonoByokChanged', () => {
  it('is a no-op when no adapter is registered', () => {
    expect(() => notifyPiMonoByokChanged()).not.toThrow()
  })

  it('hands the current BYOK env to the live adapter', async () => {
    const store = new ByokKeyStore(
      join(dir, `byok-notify-${Math.random().toString(36).slice(2)}.json`)
    )
    store.setKey('openai', 'sk-openai')
    store.setKey('anthropic', 'sk-ant')
    store.setKey('gemini', 'gm-key')
    store.setKey('deepgram', 'dg-key')
    __setByokKeyStoreForTests(store)
    const adapter = fakeAdapter()
    registerPiMonoAdapter(adapter)
    configurePiMonoSession({ token: 'tok-1', desktopApiBase: 'https://api.example/v2' })
    adapter.updateByokEnv.mockClear()
    notifyPiMonoByokChanged()
    await flush()
    expect(adapter.updateByokEnv).toHaveBeenCalledWith({
      OMI_BYOK_OPENAI: 'sk-openai',
      OMI_BYOK_ANTHROPIC: 'sk-ant',
      OMI_BYOK_GEMINI: 'gm-key',
      OMI_BYOK_DEEPGRAM: 'dg-key'
    })
  })

  it('does not restart the adapter from BYOK after sign-out', async () => {
    const store = new ByokKeyStore(
      join(dir, `byok-notify-signout-${Math.random().toString(36).slice(2)}.json`)
    )
    store.setKey('openai', 'sk-openai')
    store.setKey('anthropic', 'sk-ant')
    store.setKey('gemini', 'gm-key')
    store.setKey('deepgram', 'dg-key')
    __setByokKeyStoreForTests(store)
    const adapter = fakeAdapter()
    registerPiMonoAdapter(adapter)
    configurePiMonoSession({ token: 'tok-1', desktopApiBase: 'https://api.example/v2' })
    configurePiMonoSession(null)
    adapter.updateByokEnv.mockClear()

    notifyPiMonoByokChanged()
    await flush()
    expect(adapter.updateByokEnv).not.toHaveBeenCalled()
  })
})
