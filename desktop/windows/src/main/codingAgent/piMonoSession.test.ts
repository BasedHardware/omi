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
  }
}))

import { ByokKeyStore } from '../agentKernel/byokStore'
import {
  configurePiMonoSession,
  getPiMonoSession,
  getPiMonoByokEnv,
  piMonoManagedApiBaseUrl,
  registerPiMonoAdapter,
  unregisterPiMonoAdapter,
  __resetPiMonoSessionForTests,
  __setByokKeyStoreForTests,
  type PiMonoAuthTarget
} from './piMonoSession'

afterAll(() => rmSync(dir, { recursive: true, force: true }))

/** A fake adapter recording updateAuthToken calls. */
function fakeAdapter(): PiMonoAuthTarget & { updateAuthToken: ReturnType<typeof vi.fn> } {
  return { updateAuthToken: vi.fn(async () => true) }
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
      })
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

describe('getPiMonoByokEnv (all-or-nothing, separate from the Firebase session)', () => {
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

  it('returns {} at 3/4 keys (never a partial injection)', () => {
    const store = new ByokKeyStore(
      join(dir, `byok-partial-${Math.random().toString(36).slice(2)}.json`)
    )
    store.setKey('openai', 'sk-openai')
    store.setKey('anthropic', 'sk-ant')
    store.setKey('gemini', 'gm-key')
    __setByokKeyStoreForTests(store)

    expect(getPiMonoByokEnv()).toEqual({})
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
