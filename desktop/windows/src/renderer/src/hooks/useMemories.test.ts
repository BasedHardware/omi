// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, cleanup } from '@testing-library/react'

// C9: the backend binds PATCH /v3/memories/{id} and /v3/memories/{id}/visibility
// `value` as a QUERY param (a plain `value: str` function arg — see edit_memory /
// update_memory_visibility in backend/routers/memories.py), not a JSON body. Mac
// sends `{value}` as a body and may 422 in production; these tests pin the
// query-param form so a future edit can't silently regress to Mac's shape.
const omiApiGet = vi.fn()
const omiApiPost = vi.fn()
const omiApiPatch = vi.fn()
const omiApiDelete = vi.fn()

vi.mock('../lib/apiClient', () => ({
  omiApi: {
    get: (...args: unknown[]) => omiApiGet(...args),
    post: (...args: unknown[]) => omiApiPost(...args),
    patch: (...args: unknown[]) => omiApiPatch(...args),
    delete: (...args: unknown[]) => omiApiDelete(...args)
  }
}))

import { useMemories, type Memory } from './useMemories'

const memory = (id: string, content: string, visibility?: string): unknown => ({
  id,
  uid: 'u',
  content,
  visibility,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z'
})

beforeEach(() => {
  omiApiGet.mockReset().mockResolvedValue({ data: [memory('m1', 'Original content', 'private')] })
  omiApiPost.mockReset()
  omiApiPatch.mockReset().mockResolvedValue({ data: { status: 'ok' } })
  omiApiDelete.mockReset().mockResolvedValue({ data: { status: 'ok' } })
})

// Fakes GET /v3/memories pagination: hard page cap 500, no first-page expansion.
function fakeBackend(total: number, header?: string) {
  return async (
    _path: string,
    config: { params: { limit: number; offset: number } }
  ): Promise<{ data: Partial<Memory>[]; headers?: Record<string, string> }> => {
    const { limit, offset } = config.params
    const effectiveLimit = Math.min(limit, 500)
    const end = Math.min(offset + effectiveLimit, total)
    const data = (
      offset >= total
        ? []
        : Array.from({ length: end - offset }, (_, i) => memory(`m${offset + i}`, `c${offset + i}`))
    ) as Partial<Memory>[]
    return {
      data,
      ...(header ? { headers: { 'x-omi-memory-canonical-lifecycle-exposed': header } } : {})
    }
  }
}

afterEach(cleanup)

// useMemories keeps a module-level singleton cache (shared across every mount,
// by design — see cache/subscribers in useMemories.ts) so it survives between
// tests in this file. Force a fresh fetch via refresh() at the start of each
// test instead of relying on the mount-time effect, which only fires once
// per module lifetime (`if (cache.loaded) return`) — that keeps tests
// order-independent regardless of what a prior test left in the cache.
describe('useMemories — edit/visibility query-param contract (C9)', () => {
  it('createMemory sends the requested manual category', async () => {
    omiApiPost.mockResolvedValue({ data: memory('m2', 'Added memory', 'private') })
    const { result } = renderHook(() => useMemories())
    await act(async () => {
      await result.current.createMemory('Added memory', { category: 'manual' })
    })
    expect(omiApiPost).toHaveBeenCalledWith('/v3/memories', {
      content: 'Added memory',
      category: 'manual'
    })
  })

  it('editMemory sends the new content as a query param, not a JSON body', async () => {
    const { result } = renderHook(() => useMemories())
    await act(async () => {
      await result.current.refresh()
    })

    await act(async () => {
      await result.current.editMemory('m1', 'Updated content')
    })

    expect(omiApiPatch).toHaveBeenCalledTimes(1)
    const [path, body, config] = omiApiPatch.mock.calls[0]
    expect(path).toBe('/v3/memories/m1')
    expect(body).toBeNull() // never a {value} JSON body — that's Mac's 422-prone shape
    expect(config).toEqual({ params: { value: 'Updated content' } })
  })

  it('setMemoryVisibility sends the new value as a query param on the /visibility route', async () => {
    const { result } = renderHook(() => useMemories())
    await act(async () => {
      await result.current.refresh()
    })

    await act(async () => {
      await result.current.setMemoryVisibility('m1', 'public')
    })

    expect(omiApiPatch).toHaveBeenCalledTimes(1)
    const [path, body, config] = omiApiPatch.mock.calls[0]
    expect(path).toBe('/v3/memories/m1/visibility')
    expect(body).toBeNull()
    expect(config).toEqual({ params: { value: 'public' } })
  })

  it('reverts the local cache and rethrows when the edit request fails', async () => {
    const { result } = renderHook(() => useMemories())
    await act(async () => {
      await result.current.refresh()
    })
    omiApiPatch.mockRejectedValueOnce(new Error('network down'))

    await expect(
      act(async () => {
        await result.current.editMemory('m1', 'This will not stick')
      })
    ).rejects.toThrow('network down')

    expect(result.current.memories.find((m) => m.id === 'm1')?.content).toBe('Original content')
  })
})

describe('useMemories — pagination, capability header, delete', () => {
  it('keeps legacy/v1/future text rows readable while evidence stays optional and inert', async () => {
    omiApiGet.mockResolvedValue({
      data: [
        memory('legacy', 'Legacy text'),
        {
          ...(memory('current', 'Current text') as Record<string, unknown>),
          ledger_schema_version: 'knowledge_ledger.v1',
          kind: 'fact',
          status: 'active',
          subject_scope: 'primary_user',
          slot: 'home_city',
          body: 'wrong-kind-body',
          trigger_condition: { wrong: true },
          intent_backed: 'true',
          curation_weight: '3',
          write_reason: 'bad-reason',
          valid_at: 42,
          subject_entity_id: 42,
          evidence: [
            null,
            'malformed',
            { evidence_id: 'missing-group' },
            { evidence_id: 'current-evidence', independence_group: 'current-group' }
          ]
        },
        {
          ...(memory('future', 'Future text') as Record<string, unknown>),
          ledger_schema_version: 'knowledge_ledger.v2',
          kind: 'fact',
          status: 'active',
          subject_scope: 'primary_user',
          body: 'Future body must stay inert',
          slot: 'future-slot',
          trigger_condition: { unsupported: true },
          intent_backed: true,
          curation_weight: 3,
          write_reason: 'direct_user_statement',
          valid_at: '2026-08-23T00:00:00Z',
          subject_entity_id: 'user-1',
          evidence: [null, 'malformed']
        },
        { id: 'malformed', uid: 'u', content: '   ' }
      ]
    })
    const { result } = renderHook(() => useMemories())

    await act(async () => {
      await result.current.refresh()
    })

    expect(result.current.memories.map((item) => item.content)).toEqual([
      'Legacy text',
      'Current text',
      'Future text'
    ])
    expect(result.current.memories[0]).not.toHaveProperty('kind')
    expect(result.current.memories[1]).toMatchObject({ kind: 'fact', status: 'active' })
    expect(result.current.memories[1]).toMatchObject({ slot: 'home_city' })
    expect(result.current.memories[1].evidence).toEqual([
      { evidence_id: 'current-evidence', independence_group: 'current-group' }
    ])
    for (const field of [
      'body',
      'trigger_condition',
      'intent_backed',
      'curation_weight',
      'write_reason',
      'valid_at',
      'subject_entity_id'
    ]) {
      expect(result.current.memories[1]).not.toHaveProperty(field)
    }
    expect(result.current.memories[2]).not.toHaveProperty('kind')
    expect(result.current.memories[2]).not.toHaveProperty('status')
    expect(result.current.memories[2]).not.toHaveProperty('body')
    expect(result.current.memories[2]).not.toHaveProperty('slot')
    expect(result.current.memories[2]).not.toHaveProperty('trigger_condition')
    expect(result.current.memories[2]).not.toHaveProperty('intent_backed')
    expect(result.current.memories[2]).not.toHaveProperty('curation_weight')
    expect(result.current.memories[2]).not.toHaveProperty('write_reason')
    expect(result.current.memories[2]).not.toHaveProperty('valid_at')
    expect(result.current.memories[2]).not.toHaveProperty('subject_entity_id')
    expect(result.current.memories[2].evidence).toEqual([])
  })

  it('pages past the first server page instead of stopping at it', async () => {
    // Backend hard-caps pages at 500. Display path must page the whole set.
    omiApiGet.mockImplementation(fakeBackend(1200))
    const { result } = renderHook(() => useMemories())

    await act(async () => {
      await result.current.refresh()
    })

    expect(result.current.memories).toHaveLength(1200)
    expect(result.current.memories.some((m) => m.id === 'm1199')).toBe(true)
    expect(omiApiGet).toHaveBeenCalledWith('/v3/memories', {
      params: { limit: 500, offset: 500 }
    })
  })

  it('sets canonicalLifecycleExposed from the response header', async () => {
    omiApiGet.mockImplementation(fakeBackend(2, 'true'))
    const { result } = renderHook(() => useMemories())
    await act(async () => {
      await result.current.refresh()
    })
    expect(result.current.canonicalLifecycleExposed).toBe(true)

    // A subsequent fetch that reports the flag off must flip it back — the tier
    // filters must not linger visible against a backend that stopped exposing them.
    omiApiGet.mockImplementation(fakeBackend(2, 'false'))
    await act(async () => {
      await result.current.refresh()
    })
    expect(result.current.canonicalLifecycleExposed).toBe(false)
  })

  it('deleteMemory drops the row optimistically and reverts on failure', async () => {
    omiApiGet.mockImplementation(fakeBackend(3))
    const { result } = renderHook(() => useMemories())
    await act(async () => {
      await result.current.refresh()
    })
    expect(result.current.memories).toHaveLength(3)

    await act(async () => {
      await result.current.deleteMemory('m1')
    })
    expect(omiApiDelete).toHaveBeenCalledWith('/v3/memories/m1')
    expect(result.current.memories.some((m) => m.id === 'm1')).toBe(false)

    omiApiDelete.mockRejectedValueOnce(new Error('offline'))
    await expect(
      act(async () => {
        await result.current.deleteMemory('m0')
      })
    ).rejects.toThrow('offline')
    // The failed delete is walked back — the row is still present.
    expect(result.current.memories.some((m) => m.id === 'm0')).toBe(true)
  })
})
