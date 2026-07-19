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
