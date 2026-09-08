// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import type { KnowledgeGraph } from '../../../shared/types'

// Regression for the "refresh removes the graph entirely" bug: the rebuild
// endpoint synchronously clears the stored graph before re-deriving it in a
// background job, so the old immediate re-fetch deterministically adopted the
// cleared EMPTY snapshot — blanking the brain map on both the Memories card and
// the full-screen page. The fixed flow keeps the on-screen graph and polls until
// the rebuilt one lands; on error or timeout the old graph stays and a toast
// explains.

const fetchMock = vi.fn<() => Promise<KnowledgeGraph>>()
const rebuildMock = vi.fn<() => Promise<unknown>>()
const toastMock = vi.fn()

vi.mock('../lib/knowledgeGraphClient', () => ({
  fetchKnowledgeGraph: (): Promise<KnowledgeGraph> => fetchMock(),
  rebuildKnowledgeGraph: (): Promise<unknown> => rebuildMock()
}))
vi.mock('../lib/toast', () => ({
  toast: (...args: unknown[]): unknown => toastMock(...args)
}))

const EMPTY: KnowledgeGraph = { nodes: [], edges: [] }
const node = (id: string): KnowledgeGraph['nodes'][number] => ({
  id,
  label: id,
  nodeType: 'concept',
  aliases: [],
  memoryIds: []
})
const G1: KnowledgeGraph = { nodes: [node('a')], edges: [] }
const G2: KnowledgeGraph = { nodes: [node('a'), node('b')], edges: [] }

// The hook keeps a module-scoped cache, so each test re-imports a fresh copy.
type HookModule = typeof import('./useKnowledgeGraph')
async function freshHook(): Promise<HookModule> {
  vi.resetModules()
  return import('./useKnowledgeGraph')
}

const flush = async (): Promise<void> => {
  await act(async () => {
    await Promise.resolve()
  })
}

describe('pollRebuiltGraph', () => {
  const instant = (): Promise<void> => Promise.resolve()

  it('adopts a non-empty graph once its node count is stable across two polls', async () => {
    const { pollRebuiltGraph } = await freshHook()
    const fetch = vi
      .fn<() => Promise<KnowledgeGraph>>()
      .mockResolvedValueOnce(EMPTY)
      .mockResolvedValueOnce(G2)
      .mockResolvedValueOnce(G2)
    const g = await pollRebuiltGraph(fetch, true, [1, 1, 1, 1], instant)
    expect(g).toEqual(G2)
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it('never adopts a still-growing partial snapshot (incremental server upserts)', async () => {
    const { pollRebuiltGraph } = await freshHook()
    const grow = (n: number): KnowledgeGraph => ({
      nodes: Array.from({ length: n }, (_, i) => node(`n${i}`)),
      edges: []
    })
    const fetch = vi
      .fn<() => Promise<KnowledgeGraph>>()
      .mockResolvedValueOnce(grow(2))
      .mockResolvedValueOnce(grow(5))
      .mockResolvedValueOnce(grow(9))
    // Count grew on every poll — the job is clearly still writing, so the caller
    // must keep its old graph rather than adopt a partial one.
    const g = await pollRebuiltGraph(fetch, true, [1, 1, 1], instant)
    expect(g).toBeNull()
  })

  it('returns null (keep the old graph) when every poll still sees the cleared snapshot', async () => {
    const { pollRebuiltGraph } = await freshHook()
    const fetch = vi.fn<() => Promise<KnowledgeGraph>>().mockResolvedValue(EMPTY)
    const g = await pollRebuiltGraph(fetch, true, [1, 1, 1], instant)
    expect(g).toBeNull()
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it('accepts the first response verbatim when there was no old graph to protect', async () => {
    const { pollRebuiltGraph } = await freshHook()
    const fetch = vi.fn<() => Promise<KnowledgeGraph>>().mockResolvedValue(EMPTY)
    const g = await pollRebuiltGraph(fetch, false, [1, 1, 1], instant)
    expect(g).toEqual(EMPTY)
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('propagates fetch errors to the caller', async () => {
    const { pollRebuiltGraph } = await freshHook()
    const fetch = vi.fn<() => Promise<KnowledgeGraph>>().mockRejectedValue(new Error('down'))
    await expect(pollRebuiltGraph(fetch, true, [1], instant)).rejects.toThrow('down')
  })
})

describe('useKnowledgeGraph rebuild state', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    rebuildMock.mockReset()
    toastMock.mockReset()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('keeps the old graph and toasts when the rebuild request fails', async () => {
    fetchMock.mockResolvedValue(G1)
    const { useKnowledgeGraph } = await freshHook()
    const { result } = renderHook(() => useKnowledgeGraph())
    await flush()
    expect(result.current.graph).toEqual(G1)

    rebuildMock.mockRejectedValue(new Error('boom'))
    await act(async () => {
      await result.current.rebuild()
    })

    expect(result.current.graph).toEqual(G1) // old graph untouched — never blank
    expect(result.current.error).toBe('boom')
    expect(result.current.rebuilding).toBe(false)
    expect(toastMock).toHaveBeenCalledWith(
      'Could not rebuild the brain map',
      expect.objectContaining({ tone: 'error' })
    )
  })

  it('keeps the old graph through the cleared snapshot and adopts the rebuilt one', async () => {
    vi.useFakeTimers()
    fetchMock.mockResolvedValue(G1)
    const { useKnowledgeGraph } = await freshHook()
    const { result } = renderHook(() => useKnowledgeGraph())
    await flush()
    expect(result.current.graph).toEqual(G1)

    rebuildMock.mockResolvedValue({ status: 'rebuilding' })
    // First poll sees the cleared (empty) snapshot; the rebuilt graph then lands
    // and holds stable across the next two polls.
    fetchMock.mockReset()
    fetchMock.mockResolvedValueOnce(EMPTY).mockResolvedValueOnce(G2).mockResolvedValue(G2)

    let done: Promise<void>
    act(() => {
      done = result.current.rebuild()
    })
    await flush()
    expect(result.current.rebuilding).toBe(true)

    // First poll (2s): cleared snapshot must NOT replace the on-screen graph.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(result.current.graph).toEqual(G1)
    expect(result.current.rebuilding).toBe(true)

    // Second + third polls (3s, 5s): rebuilt graph lands, holds stable, adopted.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(8000)
      await done!
    })
    expect(result.current.graph).toEqual(G2)
    expect(result.current.rebuilding).toBe(false)
  })

  it('keeps the old graph and toasts when the poll times out', async () => {
    vi.useFakeTimers()
    fetchMock.mockResolvedValue(G1)
    const { useKnowledgeGraph } = await freshHook()
    const { result } = renderHook(() => useKnowledgeGraph())
    await flush()

    rebuildMock.mockResolvedValue({ status: 'rebuilding' })
    fetchMock.mockReset()
    fetchMock.mockResolvedValue(EMPTY) // rebuild never lands within the poll window

    let done: Promise<void>
    act(() => {
      done = result.current.rebuild()
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(90_000)
      await done!
    })

    expect(result.current.graph).toEqual(G1) // still never blank
    expect(result.current.rebuilding).toBe(false)
    expect(toastMock).toHaveBeenCalledWith('Rebuild is still running', expect.anything())
  })
})
