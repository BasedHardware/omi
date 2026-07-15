// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  beginClaudeSignIn,
  dismissClaudeSignIn,
  onClaudeSignIn,
  __resetClaudeSignIn,
  OMI_PRICING_URL,
  CLAUDE_SIGN_IN_FAILED
} from './claudeSignIn'
import type { CodingAgentStartAuthResult } from '../../../shared/types'

const codingAgentStartAuth = vi.fn<() => Promise<CodingAgentStartAuthResult>>()

function deferred<T>(): {
  promise: Promise<T>
  resolve: (v: T) => void
  reject: (e: unknown) => void
} {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

/** Latest sheet-open value from the store. */
function openState(): boolean {
  let open = false
  const unsub = onClaudeSignIn((s) => (open = s.open))
  unsub()
  return open
}

beforeEach(() => {
  codingAgentStartAuth.mockReset()
  ;(globalThis as unknown as { window: { omi: unknown } }).window.omi = { codingAgentStartAuth }
  __resetClaudeSignIn()
})

afterEach(() => __resetClaudeSignIn())

describe('beginClaudeSignIn', () => {
  it('opens the sheet AND launches the OAuth in parallel', () => {
    codingAgentStartAuth.mockReturnValue(deferred<CodingAgentStartAuthResult>().promise)
    beginClaudeSignIn()
    expect(openState()).toBe(true)
    expect(codingAgentStartAuth).toHaveBeenCalledTimes(1)
  })

  it('is idempotent — a second trigger joins the in-flight flow (one browser launch)', () => {
    codingAgentStartAuth.mockReturnValue(deferred<CodingAgentStartAuthResult>().promise)
    beginClaudeSignIn()
    beginClaudeSignIn()
    expect(codingAgentStartAuth).toHaveBeenCalledTimes(1)
    expect(openState()).toBe(true)
  })

  it('auto-closes and reports granted when the parallel OAuth completes (bypass, no purchase)', async () => {
    const d = deferred<CodingAgentStartAuthResult>()
    codingAgentStartAuth.mockReturnValue(d.promise)
    const onResult = vi.fn()
    beginClaudeSignIn(onResult)
    expect(openState()).toBe(true)

    d.resolve({ ok: true, status: { connected: true, expiresAt: 123 } })
    await d.promise

    expect(openState()).toBe(false)
    expect(onResult).toHaveBeenCalledWith({ ok: true, status: { connected: true, expiresAt: 123 } })
  })

  it('fail-closed: closes the sheet and reports the error when the flow fails', async () => {
    const d = deferred<CodingAgentStartAuthResult>()
    codingAgentStartAuth.mockReturnValue(d.promise)
    const onResult = vi.fn()
    beginClaudeSignIn(onResult)

    const failure: CodingAgentStartAuthResult = {
      ok: false,
      error: 'Could not start Claude sign-in (invalid authorization URL).',
      status: { connected: false, expiresAt: null }
    }
    d.resolve(failure)
    await d.promise

    expect(openState()).toBe(false)
    expect(onResult).toHaveBeenCalledWith(failure)
  })

  it('reports a generic failure when the IPC itself rejects', async () => {
    codingAgentStartAuth.mockRejectedValue(new Error('ipc down'))
    const onResult = vi.fn()
    beginClaudeSignIn(onResult)
    // Let the rejection microtask settle.
    await Promise.resolve()
    await Promise.resolve()
    expect(openState()).toBe(false)
    expect(onResult).toHaveBeenCalledWith(
      expect.objectContaining({ ok: false, error: CLAUDE_SIGN_IN_FAILED })
    )
  })

  it('dismiss (Cancel/Upgrade) closes the sheet and suppresses a late result callback', async () => {
    const d = deferred<CodingAgentStartAuthResult>()
    codingAgentStartAuth.mockReturnValue(d.promise)
    const onResult = vi.fn()
    beginClaudeSignIn(onResult)

    dismissClaudeSignIn()
    expect(openState()).toBe(false)

    // OAuth completes AFTER dismissal — no stale callback, sheet stays closed.
    d.resolve({ ok: true, status: { connected: true, expiresAt: 1 } })
    await d.promise
    expect(onResult).not.toHaveBeenCalled()
    expect(openState()).toBe(false)
  })
})

describe('constants', () => {
  it('exposes the omi.me pricing URL for the Upgrade CTA', () => {
    expect(OMI_PRICING_URL).toBe('https://omi.me/pricing')
  })
})
