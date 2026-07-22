// @vitest-environment jsdom
//
// Regression coverage for the "dismissed pill comes back every time" bug: the
// bar polls list_agent_sessions every 2s and mergeProjectedPills re-creates a
// pill for any projected row without a matching in-memory pill. Before the fix,
// dismiss() only spliced the in-memory array, so the very next poll — whose
// snapshot still carried the run — resurrected the pill. The fix writes the
// durable kernel attention-override (set_desktop_attention_override) AND seeds an
// in-memory guard so an in-flight poll can't re-add it before that write lands.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useAgentPills } from './useAgentPills'
import type { PillProjectionRow } from '../components/bar/agentPills'

type OverrideCall = { subjectKind: string; subjectId: string; dismissed: boolean }

const finishedRow = (): PillProjectionRow => ({
  id: 'pill-1',
  runId: 'run_1',
  sessionId: 'session-1',
  title: 'Build simple snake game',
  status: 'completed', // → display 'done' (finished)
  latestActivity: 'Done',
  query: 'build a snake game',
  createdAtMs: 1_000,
  completedAtMs: 2_000,
  provider: null,
  errorCode: null,
  errorMessage: null
})

let listRows: PillProjectionRow[]
let overrideCalls: OverrideCall[]
let agentControlCall: ReturnType<typeof vi.fn>

beforeEach(() => {
  vi.useFakeTimers()
  listRows = [finishedRow()]
  overrideCalls = []
  agentControlCall = vi.fn(async (name: string, input: Record<string, unknown>) => {
    if (name === 'list_agent_sessions') {
      return JSON.stringify({ floating_agent_pills: listRows })
    }
    if (name === 'set_desktop_attention_override') {
      overrideCalls.push(input as unknown as OverrideCall)
      return JSON.stringify({ ok: true, override: { ...input, dismissedAtMs: Date.now() } })
    }
    if (name === 'get_agent_run') {
      return JSON.stringify({ ok: false })
    }
    return JSON.stringify({ ok: false })
  })
  ;(window as unknown as { omi: unknown }).omi = { agentControlCall }
})

afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
  delete (window as unknown as { omi?: unknown }).omi
})

const flush = async (ms: number): Promise<void> => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

describe('useAgentPills — dismiss persistence (the resurrection bug)', () => {
  it('does not resurrect a dismissed pill even when the next poll still carries its run', async () => {
    const { result } = renderHook(() => useAgentPills(null))
    await flush(1) // flush the immediate mount poll
    expect(result.current.pills).toHaveLength(1)
    expect(result.current.pills[0].id).toBe('pill-1')

    act(() => {
      result.current.dismiss('pill-1')
    })
    expect(result.current.pills).toHaveLength(0)

    // The kernel snapshot has NOT been re-filtered yet (override write may not
    // have committed) — the list still returns the dismissed run. A poll here is
    // exactly the resurrection the user saw.
    await flush(2000)
    expect(result.current.pills).toHaveLength(0)
    await flush(2000)
    expect(result.current.pills).toHaveLength(0)
  })

  it('writes the durable kernel attention-override for both the run and the session', async () => {
    const { result } = renderHook(() => useAgentPills(null))
    await flush(1)
    act(() => {
      result.current.dismiss('pill-1')
    })

    expect(overrideCalls).toContainEqual({
      subjectKind: 'run',
      subjectId: 'run_1',
      dismissed: true
    })
    expect(overrideCalls).toContainEqual({
      subjectKind: 'session',
      subjectId: 'session-1',
      dismissed: true
    })
  })

  it('stays dismissed once the kernel actually filters the run out (steady state)', async () => {
    const { result } = renderHook(() => useAgentPills(null))
    await flush(1)
    act(() => {
      result.current.dismiss('pill-1')
    })
    // Kernel override has now taken effect: the run drops out of the snapshot.
    listRows = []
    await flush(2000)
    expect(result.current.pills).toHaveLength(0)
  })

  it('a fail-open override door (rejects) still hides the pill for this session', async () => {
    agentControlCall.mockImplementation(async (name: string) => {
      if (name === 'list_agent_sessions') {
        return JSON.stringify({ floating_agent_pills: listRows })
      }
      if (name === 'set_desktop_attention_override') {
        throw new Error('door unavailable')
      }
      return JSON.stringify({ ok: false })
    })
    const { result } = renderHook(() => useAgentPills(null))
    await flush(1)
    act(() => {
      result.current.dismiss('pill-1')
    })
    // Even though the durable write failed, the in-memory guard keeps the still-
    // present row from re-creating the pill this session.
    await flush(2000)
    expect(result.current.pills).toHaveLength(0)
  })
})

// Idle-burn fix: with no pills on the bar (the common steady state), the list poll
// drops from every 2s to a slow 30s heartbeat and re-arms instantly on the kernel's
// agent-card push, so a spawned agent is never missed.
describe('useAgentPills — idle cadence + card-push re-arm', () => {
  const activeRow = (): PillProjectionRow => ({
    id: 'pill-2',
    runId: 'run_2',
    sessionId: 'session-2',
    title: 'Refactor the parser',
    status: 'running', // → display 'running' (NOT finished)
    latestActivity: 'Working…',
    query: 'refactor the parser',
    createdAtMs: 1_000,
    completedAtMs: null,
    provider: null,
    errorCode: null,
    errorMessage: null
  })

  let cardCb: (() => void) | null
  beforeEach(() => {
    cardCb = null
    listRows = [] // no pills → idle state
    ;(window as unknown as { omi: { onAgentCardEvent: unknown } }).omi.onAgentCardEvent = (
      cb: () => void
    ) => {
      cardCb = cb
      return () => {
        cardCb = null
      }
    }
  })

  const listCount = (): number =>
    agentControlCall.mock.calls.filter((c) => c[0] === 'list_agent_sessions').length

  it('polls the list on a 30s heartbeat (not every 2s) while there are no pills', async () => {
    renderHook(() => useAgentPills(null))
    await flush(0) // mount immediate poll
    expect(listCount()).toBe(1)

    // The old 2s cadence would have polled several times here — idle must not.
    await flush(2000)
    await flush(2000)
    await flush(2000)
    expect(listCount()).toBe(1)

    // The slow heartbeat still backstops (never permanently silent).
    await flush(30_000)
    expect(listCount()).toBe(2)
  })

  it('re-arms to the fast 2s cadence the moment an agent appears (card push)', async () => {
    renderHook(() => useAgentPills(null))
    await flush(0)
    expect(listCount()).toBe(1)

    // A background run spawns: the kernel broadcasts an agent card and the next
    // list snapshot carries the new session.
    listRows = [activeRow()]
    await act(async () => {
      cardCb?.()
      await vi.advanceTimersByTimeAsync(0)
    })
    // The push polled immediately (didn't wait for the 30s heartbeat), discovering
    // the session — so the count moved off 1 right away. (Discovering the pill also
    // flips the hook to the fast cadence, which does one extra catch-up poll; the
    // point is only that the push did NOT wait for the slow heartbeat.)
    expect(listCount()).toBeGreaterThanOrEqual(2)

    // With a pill present the fast cadence is armed again: a 2s tick polls.
    const before = listCount()
    await flush(2000)
    expect(listCount()).toBeGreaterThan(before)
  })
})
