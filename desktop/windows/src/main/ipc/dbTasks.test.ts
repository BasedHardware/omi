// Track 3 local task storage (action_items + staged_tasks) contract, proven
// against a REAL SQLite database via node:sqlite. Unlike dbTrack3.test.ts (which
// re-declares SQL and exercises a hand-copied replica — the SQL-drift trap this
// program has hit twice), this suite imports the SAME symbols production runs:
//   - the DDL comes from taskStore.ts's exported TASK_TABLES_SCHEMA (the exact
//     string db.ts execs), so the schema can't drift from prod, and
//   - every assertion calls the REAL exported *On(db, …) functions.
// db.ts itself still can't be imported here (it pulls in better-sqlite3/electron),
// but its logic lives in taskStore.ts, and the thin db.ts wrappers just bind get().
import { DatabaseSync } from 'node:sqlite'
import { beforeEach, describe, expect, it } from 'vitest'
import { bufferToVector } from './taskEmbeddingVector'
import type { TaskStoreDb } from './taskStore'
import {
  TASK_TABLES_SCHEMA,
  insertLocalActionItemOn,
  getLocalActionItemsOn,
  getFilteredActionItemsOn,
  updateCompletionStatusOn,
  updateActionItemFieldsOn,
  deleteActionItemByBackendIdOn,
  markSyncedActionItemOn,
  syncTaskActionItemsOn,
  hardDeleteAbsentTasksOn,
  getUnsyncedActionItemsOn,
  getAllActionItemEmbeddingsOn,
  updateActionItemEmbeddingOn,
  getActionItemsMissingEmbeddingsOn,
  insertActionItemWithScoreShiftOn,
  applyActionItemRerankingOn,
  getTopRelevanceActionItemsOn,
  searchActionItemsFTSOn,
  insertLocalStagedTaskOn,
  insertStagedTaskWithScoreShiftOn,
  markSyncedStagedTaskOn,
  deleteStagedTaskByIdOn,
  deleteStagedTaskByBackendIdOn,
  getUnsyncedStagedTasksOn,
  getAllStagedTasksOn,
  getAllScoredStagedTasksOn,
  getStagedTaskOn,
  getAllStagedTaskEmbeddingsOn,
  updateStagedTaskEmbeddingOn,
  getStagedTasksMissingEmbeddingsOn,
  applyStagedTaskRerankingOn,
  countActiveStagedTasksOn,
  searchStagedTasksFTSOn
} from './taskStore'
import type { ActionItemInput, StagedTaskInput, SyncActionItem } from '../../shared/types'

// node:sqlite's DatabaseSync satisfies TaskStoreDb structurally (exec + prepare
// with run/all/get). The cast documents that; it is the same shape better-sqlite3
// provides in production.
function makeDb(): TaskStoreDb {
  const db = new DatabaseSync(':memory:')
  db.exec(TASK_TABLES_SCHEMA)
  return db as unknown as TaskStoreDb
}

let db: TaskStoreDb
beforeEach(() => {
  db = makeDb()
})

// Minimal action-item input factory (createdAt/updatedAt default to a fixed epoch).
function ai(overrides: Partial<ActionItemInput> & { description: string }): ActionItemInput {
  return { createdAt: 1000, updatedAt: 1000, ...overrides }
}
function st(overrides: Partial<StagedTaskInput> & { description: string }): StagedTaskInput {
  return { createdAt: 1000, updatedAt: 1000, ...overrides }
}
// Incoming backend sync item factory.
function sync(
  overrides: Partial<SyncActionItem> & { backendId: string; description: string }
): SyncActionItem {
  return { completed: false, createdAt: 1000, updatedAt: 1000, ...overrides }
}

describe('schema', () => {
  it('creates both tables plus their FTS shadow tables', () => {
    const names = (
      db.prepare("SELECT name FROM sqlite_master WHERE type IN ('table') ORDER BY name").all() as {
        name: string
      }[]
    ).map((r) => r.name)
    expect(names).toContain('action_items')
    expect(names).toContain('staged_tasks')
    expect(names).toContain('action_items_fts')
    expect(names).toContain('staged_tasks_fts')
  })
})

describe('action_items insert + read round-trip', () => {
  it('inserts with backend_synced forced 0, round-trips every mapped column', () => {
    const rec = insertLocalActionItemOn(
      db,
      ai({
        description: 'buy milk',
        backendSynced: true, // must be ignored — insertLocal forces 0
        source: 'manual',
        priority: 'high',
        category: 'personal',
        tags: ['work', 'urgent'],
        dueAt: 5000,
        confidence: 0.9,
        relevanceScore: 3,
        sortOrder: 2,
        indentLevel: 1,
        createdAt: 1000,
        updatedAt: 1500
      })
    )
    expect(rec.id).toBeGreaterThan(0)
    expect(rec.backendSynced).toBe(false)
    expect(rec.description).toBe('buy milk')
    expect(rec.tags).toEqual(['work', 'urgent'])
    expect(rec.priority).toBe('high')
    expect(rec.dueAt).toBe(5000)
    expect(rec.completed).toBe(false)
    expect(rec.fromStaged).toBe(false)

    const list = getLocalActionItemsOn(db)
    expect(list).toHaveLength(1)
    expect(list[0].description).toBe('buy milk')
  })

  it('getLocalActionItems excludes deleted, filters completed, and orders by sortOrder→due→created', () => {
    insertLocalActionItemOn(
      db,
      ai({ description: 'no-sort late', createdAt: 3000, updatedAt: 3000 })
    )
    insertLocalActionItemOn(db, ai({ description: 'sorted first', sortOrder: 1 }))
    insertLocalActionItemOn(db, ai({ description: 'completed', completed: true }))
    insertLocalActionItemOn(db, ai({ description: 'deleted', deleted: true }))

    const active = getLocalActionItemsOn(db, { completed: false })
    // sortOrder=1 wins; the two unsorted fall back to created_at DESC.
    expect(active.map((r) => r.description)).toEqual(['sorted first', 'no-sort late'])
    expect(active.some((r) => r.description === 'deleted')).toBe(false)
    expect(active.some((r) => r.description === 'completed')).toBe(false)

    const done = getLocalActionItemsOn(db, { completed: true })
    expect(done.map((r) => r.description)).toEqual(['completed'])
  })

  it('updateCompletionStatus + updateActionItemFields bump updated_at and change fields', () => {
    insertLocalActionItemOn(db, ai({ description: 't', backendId: 'be-1', backendSynced: false }))
    // insertLocal forces synced=0 but keeps backendId; give it one via a direct insert path:
    const rec = insertLocalActionItemOn(db, ai({ description: 'task', backendId: 'be-2' }))
    updateCompletionStatusOn(db, 'be-2', true, 9000)
    updateActionItemFieldsOn(
      db,
      'be-2',
      { description: 'renamed', priority: 'low', tags: ['x'] },
      9500
    )
    const after = getLocalActionItemsOn(db, { completed: true }).find((r) => r.id === rec.id)!
    expect(after.description).toBe('renamed')
    expect(after.priority).toBe('low')
    expect(after.tags).toEqual(['x'])
    expect(after.updatedAt).toBe(9500)
  })

  it('getFilteredActionItems slices by due window / no-due', () => {
    insertLocalActionItemOn(db, ai({ description: 'overdue', backendId: 'o', dueAt: 100 }))
    insertLocalActionItemOn(db, ai({ description: 'future', backendId: 'f', dueAt: 10000 }))
    insertLocalActionItemOn(db, ai({ description: 'no-due', backendId: 'n' }))

    const overdue = getFilteredActionItemsOn(db, { dueBefore: 500 })
    expect(overdue.map((r) => r.description)).toEqual(['overdue'])
    const noDue = getFilteredActionItemsOn(db, { dueIsNull: true })
    expect(noDue.map((r) => r.description)).toEqual(['no-due'])
    const hasDue = getFilteredActionItemsOn(db, { dueIsNull: false })
    expect(hasDue.map((r) => r.description).sort()).toEqual(['future', 'overdue'])
  })
})

describe('markSynced defensive dedup-merge (FIX iii)', () => {
  it('action_items: normal mark stamps backend_id + synced', () => {
    const rec = insertLocalActionItemOn(db, ai({ description: 'x' }))
    const res = markSyncedActionItemOn(db, rec.id, 'be-99', 2000)
    expect(res).toEqual({ merged: false, keptId: rec.id })
    const row = db
      .prepare(
        'SELECT backend_id AS b, backend_synced AS s, updated_at AS u FROM action_items WHERE id = ?'
      )
      .get(rec.id) as { b: string; s: number; u: number }
    expect(row).toEqual({ b: 'be-99', s: 1, u: 2000 })
  })

  it('action_items: a duplicate backend_id merges instead of throwing', () => {
    // canonical row already synced to be-dup
    const canonical = insertLocalActionItemOn(db, ai({ description: 'canonical' }))
    markSyncedActionItemOn(db, canonical.id, 'be-dup', 1000)
    // a second freshly-extracted duplicate for the same backend task
    const dupe = insertLocalActionItemOn(db, ai({ description: 'dupe' }))

    let res!: ReturnType<typeof markSyncedActionItemOn>
    expect(() => {
      res = markSyncedActionItemOn(db, dupe.id, 'be-dup', 3000)
    }).not.toThrow()
    expect(res.merged).toBe(true)
    expect(res.keptId).toBe(canonical.id)
    // the duplicate row is gone; exactly one row holds be-dup
    expect(db.prepare('SELECT COUNT(*) AS n FROM action_items WHERE id = ?').get(dupe.id)).toEqual({
      n: 0
    })
    expect(
      db.prepare("SELECT COUNT(*) AS n FROM action_items WHERE backend_id = 'be-dup'").get()
    ).toEqual({
      n: 1
    })
  })

  it('staged_tasks: a duplicate backend_id merges instead of throwing', () => {
    const canonical = insertLocalStagedTaskOn(db, st({ description: 'c' }))
    markSyncedStagedTaskOn(db, canonical.id, 'sbe-dup', 1000)
    const dupe = insertLocalStagedTaskOn(db, st({ description: 'd' }))

    let res!: ReturnType<typeof markSyncedStagedTaskOn>
    expect(() => {
      res = markSyncedStagedTaskOn(db, dupe.id, 'sbe-dup', 3000)
    }).not.toThrow()
    expect(res).toEqual({ merged: true, keptId: canonical.id })
    expect(
      db.prepare("SELECT COUNT(*) AS n FROM staged_tasks WHERE backend_id = 'sbe-dup'").get()
    ).toEqual({
      n: 1
    })
  })
})

describe('syncTaskActionItems conflict rule + orphan adoption', () => {
  it('inserts a fresh backend item and assigns max+1 relevance_score when scoreless', () => {
    // seed an existing scored active task so max is non-zero
    insertLocalActionItemOn(db, ai({ description: 'seed', relevanceScore: 4 }))
    const res = syncTaskActionItemsOn(db, [sync({ backendId: 'b1', description: 'new task' })], {
      now: 5000
    })
    expect(res.inserted).toBe(1)
    const row = db
      .prepare(
        "SELECT relevance_score AS s, backend_synced AS synced FROM action_items WHERE backend_id = 'b1'"
      )
      .get() as { s: number; synced: number }
    expect(row.s).toBe(5) // max(4)+1
    expect(row.synced).toBe(1)
  })

  it('60s rule: a RECENT local change newer than incoming is preserved (skipped)', () => {
    const rec = insertLocalActionItemOn(db, ai({ description: 'local', backendId: 'b1' }))
    markSyncedActionItemOn(db, rec.id, 'b1', 10_000) // local updated_at = 10000
    const res = syncTaskActionItemsOn(
      db,
      [sync({ backendId: 'b1', description: 'STALE backend', updatedAt: 9000 })],
      { now: 10_500 } // now - 10000 = 500ms < 60s, local(10000) > incoming(9000) → skip
    )
    expect(res.skipped).toBe(1)
    expect(res.updated).toBe(0)
    const row = db
      .prepare("SELECT description FROM action_items WHERE backend_id = 'b1'")
      .get() as {
      description: string
    }
    expect(row.description).toBe('local') // untouched
  })

  it('60s rule: an OLD local change loses to the backend (updated)', () => {
    const rec = insertLocalActionItemOn(db, ai({ description: 'local', backendId: 'b1' }))
    markSyncedActionItemOn(db, rec.id, 'b1', 10_000)
    const res = syncTaskActionItemsOn(
      db,
      [sync({ backendId: 'b1', description: 'backend wins', updatedAt: 20_000 })],
      { now: 10_000 + 61_000 } // > 60s since local change → trust backend
    )
    expect(res.updated).toBe(1)
    const row = db
      .prepare("SELECT description, updated_at AS u FROM action_items WHERE backend_id = 'b1'")
      .get() as {
      description: string
      u: number
    }
    expect(row.description).toBe('backend wins')
    expect(row.u).toBe(20_000) // monotonic max(10000, 20000)
  })

  it('60s rule: overrideStagedDeletions bypasses the skip for a staged-deleted local row', () => {
    const rec = insertLocalActionItemOn(
      db,
      ai({ description: 'local', backendId: 'b1', deletedBy: 'staged' })
    )
    markSyncedActionItemOn(db, rec.id, 'b1', 10_000)
    const res = syncTaskActionItemsOn(
      db,
      [sync({ backendId: 'b1', description: 'restored', updatedAt: 9000 })],
      { now: 10_100, overrideStagedDeletions: true } // recent+newer would normally skip, but staged-override applies
    )
    expect(res.updated).toBe(1)
    expect(res.skipped).toBe(0)
  })

  it('updateFrom adopts API score only when local has none, always overwrites sort/indent', () => {
    const scored = insertLocalActionItemOn(
      db,
      ai({ description: 's', backendId: 'b1', relevanceScore: 7, sortOrder: 1, indentLevel: 0 })
    )
    markSyncedActionItemOn(db, scored.id, 'b1', 1000)
    syncTaskActionItemsOn(
      db,
      [
        sync({
          backendId: 'b1',
          description: 's',
          relevanceScore: 99,
          sortOrder: 5,
          indentLevel: 2,
          updatedAt: 2000
        })
      ],
      { now: 5_000_000 }
    )
    const row = db
      .prepare(
        "SELECT relevance_score AS score, sort_order AS so, indent_level AS il FROM action_items WHERE backend_id = 'b1'"
      )
      .get() as { score: number; so: number; il: number }
    expect(row.score).toBe(7) // local had a score → API score NOT adopted
    expect(row.so).toBe(5) // sort always from API
    expect(row.il).toBe(2)
  })

  it('orphan adoption: an unsynced local row with the same description adopts the backend_id', () => {
    const orphan = insertLocalActionItemOn(db, ai({ description: 'same text' })) // backendId null, synced 0
    const res = syncTaskActionItemsOn(db, [sync({ backendId: 'b1', description: 'same text' })], {
      now: 5000
    })
    expect(res.adopted).toBe(1)
    expect(res.inserted).toBe(0)
    // no duplicate row — the orphan was linked, not a new insert
    expect(db.prepare('SELECT COUNT(*) AS n FROM action_items').get()).toEqual({ n: 1 })
    const row = db
      .prepare('SELECT backend_id AS b, backend_synced AS s FROM action_items WHERE id = ?')
      .get(orphan.id) as {
      b: string
      s: number
    }
    expect(row).toEqual({ b: 'b1', s: 1 })
  })
})

describe('hardDeleteAbsentTasks (empty-guard + returns ids)', () => {
  it('empty apiIds is a NO-OP (never wipes local data)', () => {
    const rec = insertLocalActionItemOn(db, ai({ description: 'keep', backendId: 'b1' }))
    markSyncedActionItemOn(db, rec.id, 'b1', 1000)
    const deleted = hardDeleteAbsentTasksOn(db, [])
    expect(deleted).toEqual([])
    expect(db.prepare('SELECT COUNT(*) AS n FROM action_items').get()).toEqual({ n: 1 })
  })

  it('deletes synced active rows absent from apiIds, returns their ids, keeps present + unsynced', () => {
    const present = insertLocalActionItemOn(
      db,
      ai({ description: 'present', backendId: 'present' })
    )
    markSyncedActionItemOn(db, present.id, 'present', 1000)
    const absent = insertLocalActionItemOn(db, ai({ description: 'absent', backendId: 'absent' }))
    markSyncedActionItemOn(db, absent.id, 'absent', 1000)
    const unsynced = insertLocalActionItemOn(db, ai({ description: 'unsynced' })) // no backend_id

    const deleted = hardDeleteAbsentTasksOn(db, ['present'])
    expect(deleted).toEqual([absent.id])
    const remaining = (
      db.prepare('SELECT id FROM action_items ORDER BY id').all() as { id: number }[]
    ).map((r) => r.id)
    expect(remaining).toEqual([present.id, unsynced.id])
  })
})

describe('hard deletes return deleted ids (FIX ii)', () => {
  it('deleteActionItemByBackendId returns the deleted id and removes the row', () => {
    const rec = insertLocalActionItemOn(db, ai({ description: 'x', backendId: 'b1' }))
    expect(deleteActionItemByBackendIdOn(db, 'b1')).toEqual([rec.id])
    expect(deleteActionItemByBackendIdOn(db, 'b1')).toEqual([]) // already gone
    expect(db.prepare('SELECT COUNT(*) AS n FROM action_items').get()).toEqual({ n: 0 })
  })

  it('staged deleteById / deleteByBackendId return ids (FIX i + ii)', () => {
    const a = insertLocalStagedTaskOn(db, st({ description: 'a' }))
    expect(deleteStagedTaskByIdOn(db, a.id)).toEqual([a.id])
    expect(deleteStagedTaskByIdOn(db, a.id)).toEqual([])

    const b = insertLocalStagedTaskOn(db, st({ description: 'b', backendId: 'sbe' }))
    expect(deleteStagedTaskByBackendIdOn(db, 'sbe')).toEqual([b.id])
    expect(deleteStagedTaskByBackendIdOn(db, 'sbe')).toEqual([])
  })
})

describe('score-shift dense ranking', () => {
  it('action_items: inserting at a score shifts existing active tasks down by 1', () => {
    insertLocalActionItemOn(db, ai({ description: 's1', relevanceScore: 1 }))
    insertLocalActionItemOn(db, ai({ description: 's2', relevanceScore: 2 }))
    insertActionItemWithScoreShiftOn(db, ai({ description: 'inserted', relevanceScore: 1 }))
    const rows = db
      .prepare(
        'SELECT description, relevance_score AS s FROM action_items ORDER BY relevance_score ASC'
      )
      .all() as { description: string; s: number }[]
    expect(rows).toEqual([
      { description: 'inserted', s: 1 },
      { description: 's1', s: 2 },
      { description: 's2', s: 3 }
    ])
  })

  it('staged_tasks: score shift keeps ranks dense', () => {
    insertLocalStagedTaskOn(db, st({ description: 's1', relevanceScore: 1 }))
    insertStagedTaskWithScoreShiftOn(db, st({ description: 'top', relevanceScore: 1 }))
    const rows = db
      .prepare(
        'SELECT description, relevance_score AS s FROM staged_tasks ORDER BY relevance_score ASC'
      )
      .all() as { description: string; s: number }[]
    expect(rows).toEqual([
      { description: 'top', s: 1 },
      { description: 's1', s: 2 }
    ])
  })

  it('applyActionItemReranking moves a task to a new position and renumbers 1..N', () => {
    for (let i = 1; i <= 3; i++) {
      const r = insertLocalActionItemOn(
        db,
        ai({ description: `t${i}`, backendId: `b${i}`, relevanceScore: i })
      )
      markSyncedActionItemOn(db, r.id, `b${i}`, 1000)
    }
    // move b3 (currently score 3) to position 1
    applyActionItemRerankingOn(db, [{ backendId: 'b3', newPosition: 1 }], 9000)
    const rows = db
      .prepare(
        'SELECT backend_id AS b, relevance_score AS s FROM action_items ORDER BY relevance_score ASC'
      )
      .all() as { b: string; s: number }[]
    expect(rows).toEqual([
      { b: 'b3', s: 1 },
      { b: 'b1', s: 2 },
      { b: 'b2', s: 3 }
    ])
  })

  it('getTopRelevanceActionItems returns active scored tasks lowest-first', () => {
    insertLocalActionItemOn(db, ai({ description: 'low-pri', relevanceScore: 5 }))
    insertLocalActionItemOn(db, ai({ description: 'top', relevanceScore: 1 }))
    insertLocalActionItemOn(db, ai({ description: 'unscored' }))
    const top = getTopRelevanceActionItemsOn(db, 10)
    expect(top.map((r) => r.description)).toEqual(['top', 'low-pri'])
  })
})

describe('FTS search', () => {
  it('action_items: matches active descriptions, misses completed/deleted, and no-match returns []', () => {
    insertLocalActionItemOn(db, ai({ description: 'review the quarterly budget' }))
    insertLocalActionItemOn(db, ai({ description: 'budget meeting', completed: true }))
    const hits = searchActionItemsFTSOn(db, 'budget')
    expect(hits.map((h) => h.description)).toEqual(['review the quarterly budget'])
    expect(searchActionItemsFTSOn(db, 'nonexistentterm')).toEqual([])
    expect(searchActionItemsFTSOn(db, '   ')).toEqual([]) // sanitized to empty → no query
  })

  it('FTS stays in sync after a hard delete (AFTER DELETE trigger)', () => {
    const rec = insertLocalActionItemOn(db, ai({ description: 'ephemeral note', backendId: 'b1' }))
    expect(searchActionItemsFTSOn(db, 'ephemeral')).toHaveLength(1)
    deleteActionItemByBackendIdOn(db, 'b1')
    void rec
    expect(searchActionItemsFTSOn(db, 'ephemeral')).toEqual([])
  })

  it('staged_tasks: FTS matches active staged descriptions', () => {
    insertLocalStagedTaskOn(db, st({ description: 'draft the launch email' }))
    const hits = searchStagedTasksFTSOn(db, 'launch')
    expect(hits.map((h) => h.description)).toEqual(['draft the launch email'])
  })
})

describe('embeddings + unsynced + counts', () => {
  it('getAllActionItemEmbeddings round-trips vectors; missing-embeddings backfill lists the rest', () => {
    const withVec = insertLocalActionItemOn(db, ai({ description: 'has vec' }))
    updateActionItemEmbeddingOn(db, withVec.id, new Float32Array([0.5, -0.25, 1.0]))
    insertLocalActionItemOn(db, ai({ description: 'no vec' }))

    const all = getAllActionItemEmbeddingsOn(db)
    expect(all).toHaveLength(1)
    expect(all[0].id).toBe(withVec.id)
    expect(Array.from(all[0].embedding)).toEqual([0.5, -0.25, 1.0])
    // sanity on the codec via the same helper
    expect(bufferToVector(Buffer.from(new Float32Array([1]).buffer))).toEqual(new Float32Array([1]))

    const missing = getActionItemsMissingEmbeddingsOn(db, 10)
    expect(missing.map((m) => m.description)).toEqual(['no vec'])
  })

  it('getAllStagedTaskEmbeddings excludes completed/deleted (active-only per spec)', () => {
    const active = insertLocalStagedTaskOn(db, st({ description: 'active' }))
    updateStagedTaskEmbeddingOn(db, active.id, new Float32Array([1, 2]))
    const done = insertLocalStagedTaskOn(db, st({ description: 'done', completed: true }))
    updateStagedTaskEmbeddingOn(db, done.id, new Float32Array([3, 4]))

    const all = getAllStagedTaskEmbeddingsOn(db)
    expect(all.map((e) => e.id)).toEqual([active.id])
    expect(getStagedTasksMissingEmbeddingsOn(db, 10)).toEqual([]) // both have vectors (only active listed as active)
  })

  it('getUnsyncedActionItems excludes recent rows by default, includes with includeRecent', () => {
    // created_at 1000, now 100000 → older than 30s → included by default
    insertLocalActionItemOn(db, ai({ description: 'old', createdAt: 1000, updatedAt: 1000 }))
    // created just now → excluded unless includeRecent
    insertLocalActionItemOn(db, ai({ description: 'fresh', createdAt: 99_000, updatedAt: 99_000 }))
    const def = getUnsyncedActionItemsOn(db, { now: 100_000 })
    expect(def.map((r) => r.description)).toEqual(['old'])
    const all = getUnsyncedActionItemsOn(db, { now: 100_000, includeRecent: true })
    expect(all.map((r) => r.description).sort()).toEqual(['fresh', 'old'])
  })

  it('staged reads: getAllStagedTasks, getStagedTask null-if-inactive, counts, scored list', () => {
    const a = insertLocalStagedTaskOn(
      db,
      st({ description: 'active', backendId: 'sa', relevanceScore: 2 })
    )
    markSyncedStagedTaskOn(db, a.id, 'sa', 1000)
    const done = insertLocalStagedTaskOn(db, st({ description: 'done', completed: true }))

    expect(getAllStagedTasksOn(db).map((r) => r.description)).toEqual(['active'])
    expect(countActiveStagedTasksOn(db)).toBe(1)
    expect(getStagedTaskOn(db, a.id)?.description).toBe('active')
    expect(getStagedTaskOn(db, done.id)).toBeNull() // completed → null
    expect(getAllScoredStagedTasksOn(db)).toEqual([{ backendId: 'sa', relevanceScore: 2 }])
    // getUnsyncedStagedTasks filters only deleted=0 (not completed) — faithful to Mac:
    // an unsynced completed task is still returned for a retry push.
    expect(
      getUnsyncedStagedTasksOn(db)
        .map((r) => r.description)
        .sort()
    ).toEqual(['done'])
    expect(
      applyStagedTaskRerankingOn(db, [{ backendId: 'sa', newPosition: 1 }], 2000)
    ).toBeUndefined()
    expect(getAllScoredStagedTasksOn(db)).toEqual([{ backendId: 'sa', relevanceScore: 1 }])
  })
})
