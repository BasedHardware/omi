// The task-title embedding service: the in-memory cosine index (cap + action-item
// priority + lowest-id eviction), brute-force ranking, the epoch-guarded persist,
// and the paged backfill's stop conditions. The embedding client, the storage
// getters, and the session are mocked; `dot`/`EMBED_DIM` from embedVector are the
// real pure implementations so the ranking assertions exercise actual cosine math.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { EMBED_DIM } from '../rewind/embedVector'

const h = vi.hoisted(() => ({
  epoch: 1,
  session: { apiBase: 'a', desktopApiBase: 'd', token: 't' } as {
    apiBase: string
    desktopApiBase: string
    token: string
  } | null,
  getSessionEpoch: vi.fn<() => number>(),
  getBackendSession: vi.fn(),
  embedOne: vi.fn(),
  embedBatch: vi.fn(),
  getAllActionItemEmbeddings: vi.fn(),
  getAllStagedTaskEmbeddings: vi.fn(),
  getActionItemsMissingEmbeddings: vi.fn(),
  getStagedTasksMissingEmbeddings: vi.fn(),
  updateActionItemEmbedding: vi.fn(),
  updateStagedTaskEmbedding: vi.fn()
}))

vi.mock('../assistants/core/session', () => ({
  getSessionEpoch: h.getSessionEpoch,
  getBackendSession: h.getBackendSession
}))
vi.mock('../rewind/embeddingClient', () => ({
  embedOne: h.embedOne,
  embedBatch: h.embedBatch
}))
vi.mock('../ipc/db', () => ({
  getAllActionItemEmbeddings: h.getAllActionItemEmbeddings,
  getAllStagedTaskEmbeddings: h.getAllStagedTaskEmbeddings,
  getActionItemsMissingEmbeddings: h.getActionItemsMissingEmbeddings,
  getStagedTasksMissingEmbeddings: h.getStagedTasksMissingEmbeddings,
  updateActionItemEmbedding: h.updateActionItemEmbedding,
  updateStagedTaskEmbedding: h.updateStagedTaskEmbedding
}))

import {
  loadIndex,
  addToIndex,
  removeFromIndex,
  searchSimilar,
  embedQuery,
  generateEmbeddingForTask,
  backfillMissing,
  MAX_INDEX_SIZE
} from './taskEmbeddingService'

/** A full-dimension vector (only the leading slots set) — passes the EMBED_DIM
 *  length guards in embedQuery / generateEmbeddingForTask / backfill. */
function fullVec(...vals: number[]): Float32Array {
  const v = new Float32Array(EMBED_DIM)
  vals.forEach((x, i) => (v[i] = x))
  return v
}

/** A short vector for index/ranking tests (dot() only requires equal lengths). */
const short = (...vals: number[]): Float32Array => Float32Array.from(vals)

beforeEach(() => {
  vi.clearAllMocks()
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  h.epoch = 1
  h.session = { apiBase: 'a', desktopApiBase: 'd', token: 't' }
  h.getSessionEpoch.mockImplementation(() => h.epoch)
  h.getBackendSession.mockImplementation(() => h.session)
  h.getAllActionItemEmbeddings.mockReturnValue([])
  h.getAllStagedTaskEmbeddings.mockReturnValue([])
  h.getActionItemsMissingEmbeddings.mockReturnValue([])
  h.getStagedTasksMissingEmbeddings.mockReturnValue([])
  // Reset the module-level index to a clean, loaded state for every test.
  loadIndex()
})

afterEach(() => vi.restoreAllMocks())

describe('loadIndex — cap + action-item priority + lowest-id eviction', () => {
  it('fills from action_items first, drops the lowest ids at the cap, and leaves no room for staged', () => {
    // One more action item than the cap, plus a staged task that must not fit.
    const actions = Array.from({ length: MAX_INDEX_SIZE + 1 }, (_, i) => ({
      id: i + 1,
      embedding: short(1)
    }))
    h.getAllActionItemEmbeddings.mockReturnValue(actions)
    h.getAllStagedTaskEmbeddings.mockReturnValue([{ id: 9000, embedding: short(1) }])

    loadIndex()

    const keys = new Set(
      searchSimilar(short(1), MAX_INDEX_SIZE + 10).map((r) => `${r.source}:${r.id}`)
    )
    expect(keys.size).toBe(MAX_INDEX_SIZE)
    // Highest action ids kept; the single lowest (id 1) evicted to honor the cap.
    expect(keys.has(`action_item:${MAX_INDEX_SIZE + 1}`)).toBe(true)
    expect(keys.has('action_item:1')).toBe(false)
    // Action items filled the whole cap, so the staged task never made it in.
    expect(keys.has('staged_task:9000')).toBe(false)
  })
})

describe('searchSimilar — cosine ranking (real dot product)', () => {
  it('returns the top-K entries strongest-first, across both sources', () => {
    h.getAllActionItemEmbeddings.mockReturnValue([
      { id: 1, embedding: short(1, 0, 0) }, // dot 1.0 with the query
      { id: 2, embedding: short(0, 1, 0) } // dot 0.0
    ])
    h.getAllStagedTaskEmbeddings.mockReturnValue([
      { id: 1, embedding: short(0.7, 0.7, 0) } // dot 0.7
    ])
    loadIndex()

    const top = searchSimilar(short(1, 0, 0), 2)
    expect(top.map((r) => `${r.source}:${r.id}`)).toEqual(['action_item:1', 'staged_task:1'])
    expect(top[0].similarity).toBeCloseTo(1.0)
    expect(top[1].similarity).toBeCloseTo(0.7)
  })
})

describe('addToIndex / removeFromIndex', () => {
  it('inserts a vector that then ranks, and removes it on hard-delete', () => {
    addToIndex('staged_task', 42, short(1, 0))
    expect(searchSimilar(short(1, 0), 5).map((r) => `${r.source}:${r.id}`)).toContain(
      'staged_task:42'
    )

    removeFromIndex('staged_task', 42)
    expect(searchSimilar(short(1, 0), 5)).toHaveLength(0)
  })
})

describe('embedQuery', () => {
  it('embeds the text as a RETRIEVAL_QUERY and returns the vector', async () => {
    const vec = fullVec(0.3)
    h.embedOne.mockResolvedValue(vec)
    const out = await embedQuery('where did I put the keys')
    expect(out).toBe(vec)
    expect(h.embedOne).toHaveBeenCalledWith(
      { desktopApiBase: 'd', token: 't' },
      'where did I put the keys',
      'RETRIEVAL_QUERY'
    )
  })

  it('returns null (no client call) for empty text or no session', async () => {
    expect(await embedQuery('   ')).toBeNull()
    h.session = null
    expect(await embedQuery('real text')).toBeNull()
    expect(h.embedOne).not.toHaveBeenCalled()
  })
})

describe('generateEmbeddingForTask', () => {
  it('embeds as RETRIEVAL_DOCUMENT, persists to the right table, and indexes it', async () => {
    const vec = fullVec(0.5)
    h.embedOne.mockResolvedValue(vec)

    await generateEmbeddingForTask('action_item', 7, 'buy milk')

    expect(h.embedOne).toHaveBeenCalledWith(
      { desktopApiBase: 'd', token: 't' },
      'buy milk',
      'RETRIEVAL_DOCUMENT'
    )
    expect(h.updateActionItemEmbedding).toHaveBeenCalledWith(7, vec)
    expect(h.updateStagedTaskEmbedding).not.toHaveBeenCalled()
    expect(searchSimilar(vec, 5).map((r) => `${r.source}:${r.id}`)).toContain('action_item:7')
  })

  it('drops the write when the session epoch advanced during the embed (guard)', async () => {
    // The session changes (sign-out/switch) while the embed request is in flight.
    h.embedOne.mockImplementation(async () => {
      h.epoch = 2
      return fullVec(0.5)
    })

    await generateEmbeddingForTask('staged_task', 3, 'stale task')

    expect(h.updateStagedTaskEmbedding).not.toHaveBeenCalled()
    expect(searchSimilar(fullVec(0.5), 5)).toHaveLength(0)
  })
})

describe('backfillMissing', () => {
  it('embeds each missing page in a batch and persists 1:1', async () => {
    h.getActionItemsMissingEmbeddings
      .mockReturnValueOnce([
        { id: 1, description: 'a' },
        { id: 2, description: 'b' }
      ])
      .mockReturnValue([])
    h.embedBatch.mockResolvedValue([fullVec(1), fullVec(2)])

    await backfillMissing()

    expect(h.embedBatch).toHaveBeenCalledWith(
      { desktopApiBase: 'd', token: 't' },
      ['a', 'b'],
      'RETRIEVAL_DOCUMENT'
    )
    expect(h.updateActionItemEmbedding).toHaveBeenCalledTimes(2)
    expect(h.updateActionItemEmbedding).toHaveBeenCalledWith(1, expect.any(Float32Array))
    expect(h.updateActionItemEmbedding).toHaveBeenCalledWith(2, expect.any(Float32Array))
  })

  it('stops immediately with no API call when there is no session', async () => {
    h.session = null
    await backfillMissing()
    expect(h.embedBatch).not.toHaveBeenCalled()
    expect(h.updateActionItemEmbedding).not.toHaveBeenCalled()
  })

  it('stops quietly (no throw) on an expected 402/429 backend condition', async () => {
    h.getActionItemsMissingEmbeddings.mockReturnValue([{ id: 1, description: 'a' }])
    h.embedBatch.mockRejectedValue(new Error('embedding proxy request failed (status 402)'))

    await expect(backfillMissing()).resolves.toBeUndefined()
    expect(h.updateActionItemEmbedding).not.toHaveBeenCalled()
  })
})
