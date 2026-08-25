// PR-D1: ensurePiMonoAdapterRegistered() — the kernel-side registration of the
// managed-cloud pi-mono adapter, gated on a relayed Firebase session.
//
// The kernel's heavy collaborators (SQLite store, the two socket bridges, the
// kernel itself) are mocked so getAgentRuntimeKernel() is cheap and yields a REAL
// AdapterRegistry — the actual object whose `.has`/`.register` behavior we assert.
// The pi-mono adapter classes are mocked so we can observe which auth token the
// factory constructs with WITHOUT spawning a real subprocess.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./store', () => ({ SqliteAgentStore: class {} }))
vi.mock('./kernel', () => ({
  // Bare stub — `new AgentRuntimeKernel({…})` ignores the extra ctor arg at runtime.
  AgentRuntimeKernel: class {}
}))
vi.mock('./controlMcpBridge', () => ({
  AgentControlMcpBridge: class {
    start = vi.fn(() => Promise.resolve())
    close = vi.fn(() => Promise.resolve())
    register = vi.fn(() => ({ pipePath: 'p', token: 't' }))
  }
}))
vi.mock('./toolRelayBridge', () => ({
  AgentToolRelayBridge: class {
    start = vi.fn(() => Promise.resolve())
    close = vi.fn(() => Promise.resolve())
  }
}))
vi.mock('../codingAgent/piMono', () => ({
  PiMonoAdapter: vi.fn(function (this: Record<string, unknown>, config: unknown) {
    this.config = config
    this.updateAuthToken = vi.fn(() => Promise.resolve(true))
  }),
  PiMonoRuntimeAdapter: vi.fn(function (this: Record<string, unknown>, harness: unknown) {
    this.harness = harness
    this.adapterId = 'pi-mono'
  })
}))

import { PiMonoAdapter } from '../codingAgent/piMono'
import {
  buildPiMonoRuntimeAdapter,
  callAgentControlTool,
  ensurePiMonoAdapterRegistered,
  getAgentAdapterRegistry,
  hasKnownControlPlaneOwner,
  resetControlPlaneForTests,
  setControlPlaneOwner
} from './controlPlane'
import {
  __resetPiMonoSessionForTests,
  __setByokKeyStoreForTests,
  configurePiMonoSession
} from '../codingAgent/piMonoSession'
import type { ByokKeyStore } from './byokStore'

// A stub BYOK store so getPiMonoByokEnv() never touches Electron safeStorage.
const noByok = { getAllKeys: () => ({}) } as unknown as ByokKeyStore

function lastPiMonoAuthToken(): unknown {
  const calls = vi.mocked(PiMonoAdapter).mock.calls
  return (calls.at(-1)?.[0] as { authToken?: unknown } | undefined)?.authToken
}

function lastPiMonoBaseUrl(): unknown {
  const calls = vi.mocked(PiMonoAdapter).mock.calls
  return (calls.at(-1)?.[0] as { omiApiBaseUrl?: unknown } | undefined)?.omiApiBaseUrl
}

describe('ensurePiMonoAdapterRegistered', () => {
  beforeEach(() => {
    resetControlPlaneForTests()
    __resetPiMonoSessionForTests()
    __setByokKeyStoreForTests(noByok)
    vi.mocked(PiMonoAdapter).mockClear()
  })

  afterEach(() => {
    resetControlPlaneForTests()
    __resetPiMonoSessionForTests()
  })

  it('is a no-op (false) when no session has been relayed', () => {
    expect(ensurePiMonoAdapterRegistered()).toBe(false)
  })

  it('registers pi-mono exactly once with a session and is idempotent', () => {
    configurePiMonoSession({ token: 'tok1', desktopApiBase: 'https://api.omi.me' })

    expect(ensurePiMonoAdapterRegistered()).toBe(true)
    const registry = getAgentAdapterRegistry()
    expect(registry.has('pi-mono')).toBe(true)

    // A second call (e.g. a token refresh re-invoking the IPC handler) must not
    // throw "already registered" — it is guarded by registry.has.
    expect(ensurePiMonoAdapterRegistered()).toBe(true)
    expect(registry.has('pi-mono')).toBe(true)
    expect(registry.adapterIds()).toEqual(['pi-mono'])

    // Registration alone never constructs the adapter — the worker pool calls the
    // factory lazily on first use.
    expect(vi.mocked(PiMonoAdapter)).not.toHaveBeenCalled()
  })

  it('the factory re-reads the session: a token pushed after register wins at build time', () => {
    configurePiMonoSession({ token: 'tok1', desktopApiBase: 'https://api.omi.me' })
    expect(ensurePiMonoAdapterRegistered()).toBe(true)

    // Refresh the token AFTER registration but BEFORE the factory's first call.
    configurePiMonoSession({ token: 'tok2', desktopApiBase: 'https://api.omi.me' })

    // buildPiMonoRuntimeAdapter IS the registered factory — invoking it mirrors the
    // pool's first lazy call. It must spawn with the freshest token (tok2), proving
    // it re-reads getPiMonoSession() rather than closing over the register-time one.
    buildPiMonoRuntimeAdapter()
    expect(lastPiMonoAuthToken()).toBe('tok2')
  })

  it('the factory reads current session state, not a captured one: cleared → throws', () => {
    configurePiMonoSession({ token: 'tok1', desktopApiBase: 'https://api.omi.me' })
    expect(() => buildPiMonoRuntimeAdapter()).not.toThrow()

    // Sign out between register and the lazy factory call: the factory must observe
    // the cleared session and refuse, not spawn with a stale captured token.
    configurePiMonoSession(null)
    expect(() => buildPiMonoRuntimeAdapter()).toThrow(/cleared/)
  })

  // Regression: the relayed `desktopApiBase` is version-less (VITE_OMI_DESKTOP_API_BASE
  // is a BARE host — no `/v2`). The factory must bake `/v2` into the adapter's
  // OMI_API_BASE_URL, or pi's openai-completions SDK hits `<host>/chat/completions`
  // (404) instead of `<host>/v2/chat/completions`. The previous fixtures used a base
  // that already had `/v2`, so they never caught the missing segment.
  it('appends /v2 to the bare relayed base so the adapter targets /v2/chat/completions', () => {
    configurePiMonoSession({
      token: 'tok1',
      desktopApiBase: 'https://desktop-backend-hhibjajaja-uc.a.run.app'
    })
    buildPiMonoRuntimeAdapter()
    expect(lastPiMonoBaseUrl()).toBe('https://desktop-backend-hhibjajaja-uc.a.run.app/v2')
  })

  it('does not double up the slash when the relayed base has a trailing slash', () => {
    configurePiMonoSession({ token: 'tok1', desktopApiBase: 'https://api.omi.me/' })
    buildPiMonoRuntimeAdapter()
    expect(lastPiMonoBaseUrl()).toBe('https://api.omi.me/v2')
  })
})

describe('callAgentControlTool — cold-start owner gate', () => {
  beforeEach(() => {
    resetControlPlaneForTests()
    __resetPiMonoSessionForTests()
    __setByokKeyStoreForTests(noByok)
  })

  afterEach(() => {
    resetControlPlaneForTests()
    __resetPiMonoSessionForTests()
  })

  it('refuses with owner_not_ready while the owner is the default constant', async () => {
    expect(hasKnownControlPlaneOwner()).toBe(false)
    const parsed = JSON.parse(await callAgentControlTool('list_agent_sessions', {})) as {
      ok: boolean
      error?: { code?: string }
    }
    expect(parsed.ok).toBe(false)
    expect(parsed.error?.code).toBe('owner_not_ready')
  })

  it('passes the gate once a real owner is wired (no owner_not_ready)', async () => {
    setControlPlaneOwner('uid-A')
    expect(hasKnownControlPlaneOwner()).toBe(true)
    // The tool may still succeed or fail on the mocked kernel — the assertion is
    // only that the owner gate no longer short-circuits it.
    const parsed = JSON.parse(await callAgentControlTool('list_agent_sessions', {})) as {
      error?: { code?: string }
    }
    expect(parsed.error?.code).not.toBe('owner_not_ready')
  })
})
