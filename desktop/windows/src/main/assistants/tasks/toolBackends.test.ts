// Hermetic tests for the two TaskAssistant search backends. The pure cores take
// their impure edges by injection, so `executeVectorSearchWith` runs against fake
// index/storage and `executeKeywordSearchWith` runs against BOTH fully-injected
// fakes (to pin the FTS query string + merge) AND a real node:sqlite DB seeded via
// the SAME PR-A insert functions production uses (to prove real FTS + includeCompleted
// + no cross-table dedupe). No SQL is re-declared here — the DDL is taskStore.ts's
// exported TASK_TABLES_SCHEMA, avoiding the SQL-drift trap.
import { DatabaseSync } from 'node:sqlite'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { TaskStoreDb } from '../../ipc/taskStore'
import {
  TASK_TABLES_SCHEMA,
  insertLocalActionItemOn,
  insertLocalStagedTaskOn,
  searchActionItemsFTSOn,
  searchStagedTasksFTSOn
} from '../../ipc/taskStore'
import type { ActionItemInput, StagedTaskInput } from '../../../shared/types'
import type { TaskSimilarity } from '../../tasks/taskEmbeddingService'
import {
  buildFtsQuery,
  encodeSearchResults,
  executeKeywordSearchWith,
  executeVectorSearchWith,
  type KeywordSearchDeps,
  type ResolvedTask,
  type TaskSearchResult,
  type VectorSearchDeps
} from './toolBackends'

// --- buildFtsQuery (the pure tokenizer) ---
describe('buildFtsQuery', () => {
  it('OR-joins prefix terms, stripping non-alphanumerics and dropping <3-char tokens', () => {
    // "Q3" strips to "q3" (2 chars) → dropped; "the" (3 chars) is kept, as on Mac.
    expect(buildFtsQuery('review the Q3 budget report')).toBe(
      'review* OR the* OR budget* OR report*'
    )
  })

  it('strips FTS5 operator characters from inside tokens', () => {
    // "send-me" → "sendme", "deck!" → "deck" — no stray `-`/`!`/`*`/`:` reaches FTS5.
    expect(buildFtsQuery('send-me the deck!')).toBe('sendme* OR the* OR deck*')
  })

  it('keeps Unicode letters/digits', () => {
    expect(buildFtsQuery('café report')).toBe('café* OR report*')
  })

  it('returns "" when no token survives (all <3 chars, or blank)', () => {
    expect(buildFtsQuery('a b c')).toBe('')
    expect(buildFtsQuery('   ')).toBe('')
    expect(buildFtsQuery('')).toBe('')
  })
})

// --- executeVectorSearchWith (fully-injected fakes) ---
function resolved(over: Partial<ResolvedTask> & { description: string }): ResolvedTask {
  return { completed: false, deleted: false, relevanceScore: null, ...over }
}
function sim(source: TaskSimilarity['source'], id: number, similarity: number): TaskSimilarity {
  return { source, id, similarity }
}

describe('executeVectorSearchWith', () => {
  it('keeps only hits strictly above 0.3, resolves by source, and sorts by similarity desc', async () => {
    const getStagedTask = vi.fn((id: number) =>
      id === 10 ? resolved({ description: 'staged: launch email', relevanceScore: 7 }) : null
    )
    const getActionItem = vi.fn((id: number) =>
      id === 20 ? resolved({ description: 'action: quarterly budget' }) : null
    )
    const deps: VectorSearchDeps = {
      embedQuery: vi.fn(async () => new Float32Array([1])),
      // Return out of order + one exactly-0.3 (must be dropped) + one below.
      searchSimilar: vi.fn(() => [
        sim('action_item', 20, 0.5),
        sim('staged_task', 10, 0.9),
        sim('action_item', 30, 0.3), // exactly at threshold → excluded (strict >)
        sim('staged_task', 40, 0.1) // below → excluded
      ]),
      getStagedTask,
      getActionItem
    }

    const results = await executeVectorSearchWith(deps, 'send me the deck')

    expect(results).toEqual<TaskSearchResult[]>([
      {
        id: 10,
        description: 'staged: launch email',
        status: 'active',
        similarity: 0.9,
        match_type: 'vector',
        relevance_score: 7
      },
      {
        id: 20,
        description: 'action: quarterly budget',
        status: 'active',
        similarity: 0.5,
        match_type: 'vector',
        relevance_score: null
      }
    ])
    // Source-aware resolution: staged ids never hit the action resolver and vice versa.
    expect(getStagedTask).toHaveBeenCalledWith(10)
    expect(getActionItem).toHaveBeenCalledWith(20)
    expect(getActionItem).not.toHaveBeenCalledWith(10)
    // topK forwarded as 10.
    expect(deps.searchSimilar).toHaveBeenCalledWith(expect.any(Float32Array), 10)
  })

  it('derives status: deleted > completed > active', async () => {
    const deps: VectorSearchDeps = {
      embedQuery: vi.fn(async () => new Float32Array([1])),
      searchSimilar: vi.fn(() => [sim('action_item', 1, 0.8), sim('action_item', 2, 0.7)]),
      getStagedTask: vi.fn(() => null),
      getActionItem: vi.fn((id: number) =>
        id === 1
          ? resolved({ description: 'done', completed: true })
          : resolved({ description: 'gone', deleted: true, completed: true })
      )
    }
    const results = await executeVectorSearchWith(deps, 'x')
    expect(results.map((r) => [r.id, r.status])).toEqual([
      [1, 'completed'],
      [2, 'deleted'] // deleted takes precedence over completed
    ])
  })

  it('skips hits whose row cannot be resolved (hard-deleted / index drift)', async () => {
    const deps: VectorSearchDeps = {
      embedQuery: vi.fn(async () => new Float32Array([1])),
      searchSimilar: vi.fn(() => [sim('action_item', 99, 0.9)]),
      getStagedTask: vi.fn(() => null),
      getActionItem: vi.fn(() => null) // resolver finds nothing
    }
    expect(await executeVectorSearchWith(deps, 'x')).toEqual([])
  })

  it('returns [] when embedding is unavailable (no session / empty text)', async () => {
    const searchSimilar = vi.fn(() => [])
    const deps: VectorSearchDeps = {
      embedQuery: vi.fn(async () => null),
      searchSimilar,
      getStagedTask: vi.fn(() => null),
      getActionItem: vi.fn(() => null)
    }
    expect(await executeVectorSearchWith(deps, 'x')).toEqual([])
    expect(searchSimilar).not.toHaveBeenCalled() // no vector → no index scan
  })
})

// --- executeKeywordSearchWith (injected fakes: query string + merge) ---
describe('executeKeywordSearchWith (injected)', () => {
  it('passes the built FTS query with includeCompleted=true and merges BOTH tables without dedupe', async () => {
    const searchActionItemsFTS = vi.fn(() => [
      {
        id: 1,
        description: 'ship the budget deck',
        completed: false,
        deleted: false,
        relevanceScore: 3
      },
      {
        id: 2,
        description: 'budget recap call',
        completed: true,
        deleted: false,
        relevanceScore: null
      }
    ])
    // Same id (1) as an action row — different table, so it MUST NOT be deduped away.
    const searchStagedTasksFTS = vi.fn(() => [
      { id: 1, description: 'draft the budget email', relevanceScore: null }
    ])
    const deps: KeywordSearchDeps = { searchActionItemsFTS, searchStagedTasksFTS }

    const results = await executeKeywordSearchWith(deps, 'budget report')

    // Both FTS readers get the identical prefix-OR query; action reader gets includeCompleted=true.
    expect(searchActionItemsFTS).toHaveBeenCalledWith('budget* OR report*', 10, true)
    expect(searchStagedTasksFTS).toHaveBeenCalledWith('budget* OR report*', 10)

    expect(results).toEqual<TaskSearchResult[]>([
      {
        id: 1,
        description: 'ship the budget deck',
        status: 'active',
        similarity: null,
        match_type: 'fts',
        relevance_score: 3
      },
      {
        id: 2,
        description: 'budget recap call',
        status: 'completed',
        similarity: null,
        match_type: 'fts',
        relevance_score: null
      },
      {
        id: 1,
        description: 'draft the budget email',
        status: 'active',
        similarity: null,
        match_type: 'fts',
        relevance_score: null
      }
    ])
  })

  it('short-circuits to [] without touching FTS when no token survives tokenization', async () => {
    const searchActionItemsFTS = vi.fn(() => [])
    const searchStagedTasksFTS = vi.fn(() => [])
    const deps: KeywordSearchDeps = { searchActionItemsFTS, searchStagedTasksFTS }
    expect(await executeKeywordSearchWith(deps, 'a b c')).toEqual([])
    expect(searchActionItemsFTS).not.toHaveBeenCalled()
    expect(searchStagedTasksFTS).not.toHaveBeenCalled()
  })
})

// --- executeKeywordSearchWith over a REAL node:sqlite DB (PR-A inserts + FTS) ---
function makeDb(): TaskStoreDb {
  const db = new DatabaseSync(':memory:')
  db.exec(TASK_TABLES_SCHEMA)
  return db as unknown as TaskStoreDb
}
function ai(over: Partial<ActionItemInput> & { description: string }): ActionItemInput {
  return { createdAt: 1000, updatedAt: 1000, ...over }
}
function st(over: Partial<StagedTaskInput> & { description: string }): StagedTaskInput {
  return { createdAt: 1000, updatedAt: 1000, ...over }
}

describe('executeKeywordSearchWith (real FTS)', () => {
  let db: TaskStoreDb
  beforeEach(() => {
    db = makeDb()
  })

  it('surfaces completed action items, staged tasks, and does not collapse colliding ids', async () => {
    // action_items ids start at 1; the first insert is id 1.
    insertLocalActionItemOn(db, ai({ description: 'review the Falcon budget' }))
    insertLocalActionItemOn(db, ai({ description: 'Falcon budget recap', completed: true }))
    // staged_tasks ids ALSO start at 1 → this staged row shares id 1 with the action row.
    insertLocalStagedTaskOn(db, st({ description: 'draft the Falcon launch email' }))

    const deps: KeywordSearchDeps = {
      searchActionItemsFTS: (q, limit, includeCompleted) =>
        searchActionItemsFTSOn(db, q, limit, includeCompleted),
      searchStagedTasksFTS: (q, limit) => searchStagedTasksFTSOn(db, q, limit)
    }

    const results = await executeKeywordSearchWith(deps, 'Falcon budget')
    const byDesc = results.map((r) => r.description).sort()
    // The completed action row appears (includeCompleted), plus the active one; the
    // staged "Falcon" row appears too (matched on the falcon* prefix).
    expect(byDesc).toEqual([
      'Falcon budget recap',
      'draft the Falcon launch email',
      'review the Falcon budget'
    ])
    // The completed row carries its completed status through.
    expect(results.find((r) => r.description === 'Falcon budget recap')?.status).toBe('completed')
    // Two results share id 1 (one action, one staged) — proof there is no id-dedupe.
    expect(results.filter((r) => r.id === 1)).toHaveLength(2)
  })
})

// --- encodeSearchResults ---
describe('encodeSearchResults', () => {
  it('emits the Mac snake_case JSON keys and preserves null similarity', () => {
    const encoded = encodeSearchResults([
      {
        id: 5,
        description: 'x',
        status: 'active',
        similarity: null,
        match_type: 'fts',
        relevance_score: 2
      }
    ])
    expect(JSON.parse(encoded)).toEqual([
      {
        id: 5,
        description: 'x',
        status: 'active',
        similarity: null,
        match_type: 'fts',
        relevance_score: 2
      }
    ])
    expect(encoded).toContain('"match_type"')
    expect(encoded).toContain('"relevance_score"')
  })

  it('encodes an empty result set as "[]"', () => {
    expect(encodeSearchResults([])).toBe('[]')
  })
})
