// pimono:setSession handler — the seam that wires the control-plane owner to the
// signed-in user, HOST-DERIVED from the relayed Firebase ID token.
//
// This is the regression suite for the cross-account data-sharing fix: the owner
// keys every kernel session/surface row (surfaceSession.ts), and before this
// wiring it stayed the shared DEFAULT_LOCAL_OWNER_ID constant for every account —
// so two accounts under one Windows profile collided on the same rows. The owner
// must now come from the token's uid claim (not a renderer-asserted field), switch
// per account, and reset to the default on sign-out.
//
// The kernel's heavy collaborators are mocked (same pattern as
// controlPlane.pimono.test.ts) so ensurePiMonoAdapterRegistered() is cheap; the
// owner functions under test are the REAL ones.

import { mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const dir = mkdtempSync(join(tmpdir(), 'omi-pimono-ipc-'))
const handlers = new Map<string, (event: unknown, ...args: unknown[]) => unknown>()

vi.mock('electron', () => ({
  app: { getPath: (): string => dir },
  ipcMain: {
    handle: (channel: string, fn: (event: unknown, ...args: unknown[]) => unknown): void => {
      handlers.set(channel, fn)
    }
  }
}))
vi.mock('../agentKernel/store', () => ({ SqliteAgentStore: class {} }))
vi.mock('../agentKernel/kernel', () => ({ AgentRuntimeKernel: class {} }))
vi.mock('../agentKernel/controlMcpBridge', () => ({
  AgentControlMcpBridge: class {
    start = vi.fn(() => Promise.resolve())
    close = vi.fn(() => Promise.resolve())
    register = vi.fn(() => ({ pipePath: 'p', token: 't' }))
  }
}))
vi.mock('../agentKernel/toolRelayBridge', () => ({
  AgentToolRelayBridge: class {
    start = vi.fn(() => Promise.resolve())
    close = vi.fn(() => Promise.resolve())
  }
}))
vi.mock('../codingAgent/piMono', () => ({
  PiMonoAdapter: vi.fn(function (this: Record<string, unknown>) {
    this.updateAuthToken = vi.fn(() => Promise.resolve(true))
  }),
  PiMonoRuntimeAdapter: vi.fn(function (this: Record<string, unknown>) {
    this.adapterId = 'pi-mono'
  })
}))

import { registerPiMonoHandlers } from './pimono'
import {
  controlPlaneOwnerId,
  hasKnownControlPlaneOwner,
  resetControlPlaneForTests
} from '../agentKernel/controlPlane'
import { DEFAULT_LOCAL_OWNER_ID } from '../agentKernel/controlTools'
import {
  __resetPiMonoSessionForTests,
  __setByokKeyStoreForTests
} from '../codingAgent/piMonoSession'
import type { ByokKeyStore } from '../agentKernel/byokStore'

const noByok = { getAllKeys: () => ({}) } as unknown as ByokKeyStore

/** A Firebase-shaped ID token carrying the given claims (unsigned; decode-only). */
function fakeToken(claims: Record<string, unknown>): string {
  const b64url = (o: unknown): string =>
    Buffer.from(JSON.stringify(o))
      .toString('base64')
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '')
  return `${b64url({ alg: 'RS256' })}.${b64url(claims)}.sig`
}

function setSession(payload: unknown): void {
  const handler = handlers.get('pimono:setSession')
  if (!handler) throw new Error('pimono:setSession was not registered')
  handler({}, payload)
}

const base = 'https://api.omi.me'

afterAll(() => rmSync(dir, { recursive: true, force: true }))

beforeEach(() => {
  handlers.clear()
  resetControlPlaneForTests()
  __resetPiMonoSessionForTests()
  __setByokKeyStoreForTests(noByok)
  registerPiMonoHandlers()
})

afterEach(() => {
  resetControlPlaneForTests()
  __resetPiMonoSessionForTests()
})

describe('pimono:setSession — control-plane owner wiring', () => {
  it('starts at the default constant with no known owner before any relay', () => {
    expect(controlPlaneOwnerId()).toBe(DEFAULT_LOCAL_OWNER_ID)
    expect(hasKnownControlPlaneOwner()).toBe(false)
  })

  it('sets the owner to the uid decoded from the relayed token', () => {
    setSession({ token: fakeToken({ user_id: 'uid-A' }), desktopApiBase: base })
    expect(controlPlaneOwnerId()).toBe('uid-A')
    expect(hasKnownControlPlaneOwner()).toBe(true)
  })

  it('resets the owner to the default on sign-out (null session)', () => {
    setSession({ token: fakeToken({ user_id: 'uid-A' }), desktopApiBase: base })
    setSession(null)
    expect(controlPlaneOwnerId()).toBe(DEFAULT_LOCAL_OWNER_ID)
    expect(hasKnownControlPlaneOwner()).toBe(false)
  })

  it('switches the owner when a second account signs in — no stale first-account owner', () => {
    // The account-switch case the fix exists for: signing out A then in as B must
    // scope subsequent kernel work to B, never A and never the shared constant.
    setSession({ token: fakeToken({ user_id: 'account-A' }), desktopApiBase: base })
    expect(controlPlaneOwnerId()).toBe('account-A')
    setSession(null)
    setSession({ token: fakeToken({ user_id: 'account-B' }), desktopApiBase: base })
    expect(controlPlaneOwnerId()).toBe('account-B')
  })

  it('is host-authoritative — an undecodable/forged token falls back to default, not a leaked owner', () => {
    // A valid session SHAPE with a non-JWT token: the uid cannot be derived, so the
    // owner stays the default constant. hasKnownControlPlaneOwner() is false, which
    // the cold-start gate uses to refuse — fail closed, never key rows under a
    // half-trusted owner.
    setSession({ token: 'not-a-real-jwt', desktopApiBase: base })
    expect(controlPlaneOwnerId()).toBe(DEFAULT_LOCAL_OWNER_ID)
    expect(hasKnownControlPlaneOwner()).toBe(false)
  })

  it('ignores an invalid session payload without changing a known owner-less state', () => {
    setSession({ token: '', desktopApiBase: base }) // coerces to null → cleared
    expect(controlPlaneOwnerId()).toBe(DEFAULT_LOCAL_OWNER_ID)
  })
})
