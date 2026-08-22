import { describe, it, expect, vi } from 'vitest'

// The module imports electron at top; the flow under test injects all I/O, so a
// minimal stub is enough to import it.
vi.mock('electron', () => ({
  net: { fetch: vi.fn() },
  shell: { openExternal: vi.fn() },
  BrowserWindow: { getAllWindows: () => [] }
}))

import { runXConnectFlow } from './xConnector'
import type { XRunState, XStatus } from '../../shared/types'

const noSleep = (): Promise<void> => Promise.resolve()
const okStatus = (over: Partial<XStatus> = {}): XStatus => ({
  connected: false,
  postCount: 0,
  memoryCount: 0,
  syncing: false,
  ...over
})

function collector(): {
  onState: (p: Partial<XRunState>) => void
  state: XRunState
  log: XRunState[]
} {
  const state: XRunState = { phase: 'idle', postCount: 0, memoryCount: 0 }
  const log: XRunState[] = []
  return {
    state,
    log,
    onState(patch) {
      Object.assign(state, patch)
      log.push({ ...state })
    }
  }
}

const fast = { intervalMs: 1, maxAttempts: 5 }

describe('runXConnectFlow', () => {
  it('drives connecting → syncing (with live counts) → succeeded', async () => {
    const c = collector()
    const getStatus = vi
      .fn()
      .mockResolvedValueOnce(okStatus({ connected: false })) // phase 1, not yet
      .mockResolvedValueOnce(okStatus({ connected: true, handle: 'ada', syncing: true })) // phase 1 connects
      .mockResolvedValueOnce(
        okStatus({ connected: true, handle: 'ada', syncing: true, postCount: 5, memoryCount: 2 })
      )
      .mockResolvedValueOnce(
        okStatus({ connected: true, handle: 'ada', syncing: false, postCount: 9, memoryCount: 4 })
      )

    const openExternal = vi.fn().mockResolvedValue(undefined)
    await runXConnectFlow({
      getOAuthUrl: async () => ({ authUrl: 'https://x.com/i/oauth2/authorize?state=test' }),
      getStatus,
      openExternal,
      sleep: noSleep,
      onState: c.onState,
      phase1: fast,
      phase2: fast
    })

    expect(openExternal).toHaveBeenCalledWith('https://x.com/i/oauth2/authorize?state=test')
    expect(c.state.phase).toBe('succeeded')
    expect(c.state.postCount).toBe(9)
    expect(c.state.memoryCount).toBe(4)
    expect(c.state.handle).toBe('ada')
    // It passed through 'connecting' and 'syncing' on the way.
    expect(c.log.map((s) => s.phase)).toContain('connecting')
    expect(c.log.map((s) => s.phase)).toContain('syncing')
  })

  it('fails when the OAuth URL is unavailable (not configured)', async () => {
    const c = collector()
    await runXConnectFlow({
      getOAuthUrl: async () => ({ error: 'x_oauth_not_configured' }),
      getStatus: vi.fn(),
      openExternal: vi.fn().mockResolvedValue(undefined),
      sleep: noSleep,
      onState: c.onState,
      phase1: fast,
      phase2: fast
    })
    expect(c.state.phase).toBe('failed')
    expect(c.state.error).toBe('x_oauth_not_configured')
  })

  it('refuses an OAuth URL outside the trusted X origins', async () => {
    const c = collector()
    const openExternal = vi.fn()
    await runXConnectFlow({
      getOAuthUrl: async () => ({ authUrl: 'https://attacker.example/oauth' }),
      getStatus: vi.fn(),
      openExternal,
      sleep: noSleep,
      onState: c.onState,
      phase1: fast,
      phase2: fast
    })
    expect(c.state.phase).toBe('failed')
    expect(c.state.error).toBe('invalid_auth_url')
    expect(openExternal).not.toHaveBeenCalled()
  })

  it('fails with timeout when the account never connects', async () => {
    const c = collector()
    const getStatus = vi.fn().mockResolvedValue(okStatus({ connected: false }))
    await runXConnectFlow({
      getOAuthUrl: async () => ({ authUrl: 'https://twitter.com/i/oauth2/authorize' }),
      getStatus,
      openExternal: vi.fn().mockResolvedValue(undefined),
      sleep: noSleep,
      onState: c.onState,
      phase1: { intervalMs: 1, maxAttempts: 3 },
      phase2: fast
    })
    expect(c.state.phase).toBe('failed')
    expect(c.state.error).toBe('timeout')
    expect(getStatus).toHaveBeenCalledTimes(3)
  })
})
