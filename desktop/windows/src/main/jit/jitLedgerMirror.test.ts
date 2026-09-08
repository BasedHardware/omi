import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import {
  initializeJitTriggerMirror,
  JitMirrorError,
  listPendingJitKeyframeCleanup,
  pinJitConversationKeyframe,
  reconcileJitLedgerMirror,
  type JitLedgerMirrorPage,
  type JitMirrorDb
} from './jitTriggerMirror'

const page = (overrides: Partial<JitLedgerMirrorPage> = {}): JitLedgerMirrorPage => ({
  schemaVersion: 'knowledge_ledger_mirror.v1',
  ownerId: 'user-1',
  accountGeneration: 3,
  sourceGeneration: 4,
  writerEpoch: 5,
  headCommitId: 'head-1',
  commitSequence: 6,
  epochId: 'epoch-1',
  pageRevision: 'page-1',
  chainRevision: 'chain-1',
  scannedCount: 3,
  projectedCount: 3,
  terminalCount: 1,
  rows: [
    {
      memoryId: 'fact-1',
      itemRevision: 2,
      status: 'active',
      sourceState: 'active',
      canonicalMemoryId: null,
      contentPurged: false,
      memory: { kind: 'fact', content: 'a fact' }
    },
    {
      memoryId: 'playbook-1',
      itemRevision: 1,
      status: 'active',
      sourceState: 'active',
      canonicalMemoryId: null,
      contentPurged: false,
      memory: { kind: 'document', body: 'step one' }
    },
    {
      memoryId: 'history-1',
      itemRevision: 3,
      status: 'superseded',
      sourceState: 'active',
      canonicalMemoryId: 'fact-1',
      contentPurged: false,
      memory: { kind: 'fact', content: 'old fact' }
    }
  ],
  aliases: [
    {
      aliasMemoryId: 'history-1',
      canonicalMemoryId: 'fact-1',
      sourceMemoryId: 'history-1',
      reason: 'canonical_memory_id'
    }
  ],
  nextCursor: null,
  finalPage: true,
  failureReason: null,
  ...overrides
})

function makeDb(): DatabaseSync {
  const db = new DatabaseSync(':memory:')
  initializeJitTriggerMirror(db as unknown as JitMirrorDb)
  db.exec('CREATE TABLE legacy_memories (id TEXT PRIMARY KEY, body TEXT)')
  db.prepare('INSERT INTO legacy_memories VALUES (?, ?)').run('legacy', 'must remain')
  return db
}

const reconcile = (db: DatabaseSync, value: JitLedgerMirrorPage) =>
  reconcileJitLedgerMirror(
    db as unknown as JitMirrorDb,
    {
      fence: {
        ownerId: value.ownerId,
        accountGeneration: value.accountGeneration,
        sourceGeneration: value.sourceGeneration,
        writerEpoch: value.writerEpoch,
        headCommitId: value.headCommitId,
        commitSequence: value.commitSequence,
        epochId: value.epochId,
        pageRevision: value.pageRevision,
        schemaVersion: value.schemaVersion,
        chainRevision: value.chainRevision,
        scannedCount: value.scannedCount,
        projectedCount: value.projectedCount,
        terminalCount: value.terminalCount
      },
      rows: value.rows,
      aliases: value.aliases
    },
    value.ownerId,
    100
  )

describe('Windows JIT ledger mirror', () => {
  it('classifies current facts/playbooks and historical handles transactionally', () => {
    const db = makeDb()
    const receipt = reconcile(db, page())
    expect(receipt.rowCount).toBe(3)
    expect(db.prepare('SELECT COUNT(*) AS n FROM jit_fact_mirror').get()).toEqual({ n: 1 })
    expect(db.prepare('SELECT COUNT(*) AS n FROM jit_playbook_mirror').get()).toEqual({ n: 1 })
    expect(db.prepare('SELECT COUNT(*) AS n FROM jit_history_mirror').get()).toEqual({ n: 1 })
    expect(db.prepare('SELECT COUNT(*) AS n FROM jit_alias_mirror').get()).toEqual({ n: 1 })
    expect(db.prepare('SELECT body FROM legacy_memories WHERE id=?').get('legacy')).toEqual({
      body: 'must remain'
    })
  })

  it('rejects torn or conflicting generations before replacing the mirror', () => {
    const db = makeDb()
    reconcile(db, page())
    expect(() => reconcile(db, page({ accountGeneration: 2 }))).toThrowError(
      new JitMirrorError('stale_generation')
    )
    expect(() => reconcile(db, page({ epochId: 'different' }))).toThrowError(
      new JitMirrorError('conflicting_revision')
    )
    expect(db.prepare('SELECT COUNT(*) AS n FROM jit_fact_mirror').get()).toEqual({ n: 1 })
  })

  it('retains keyframe cleanup authority across an account-generation transition', () => {
    const db = makeDb()
    reconcile(db, page())
    pinJitConversationKeyframe(db as unknown as JitMirrorDb, {
      frameId: 88,
      ownerId: 'user-1',
      conversationId: 'jit:prior-account',
      imagePath: 'C:/rewind/88.jpg',
      pinnedAt: 101
    })

    reconcile(
      db,
      page({ ownerId: 'user-2', accountGeneration: 4, commitSequence: 7, pageRevision: 'page-2' })
    )

    expect(db.prepare('SELECT COUNT(*) AS n FROM jit_keyframe_pin').get()).toEqual({ n: 1 })
    expect(listPendingJitKeyframeCleanup(db as unknown as JitMirrorDb, 100)).toEqual([
      expect.objectContaining({ frameId: 88, imagePath: 'C:/rewind/88.jpg' })
    ])
  })

  it('never accepts purged content or replaces a legacy table', () => {
    const db = makeDb()
    expect(() =>
      reconcile(
        db,
        page({
          rows: [
            {
              ...page().rows[0],
              contentPurged: true,
              memory: { kind: 'fact', content: 'should reject' }
            }
          ]
        })
      )
    ).toThrowError(new JitMirrorError('malformed_row'))
    expect(db.prepare('SELECT body FROM legacy_memories WHERE id=?').get('legacy')).toEqual({
      body: 'must remain'
    })
  })

  it('rejects impossible status/source-state combinations', () => {
    const db = makeDb()
    for (const row of [
      { ...page().rows[0], sourceState: 'purged' },
      { ...page().rows[0], status: 'tombstoned', sourceState: 'active' },
      { ...page().rows[0], status: 'tombstoned', sourceState: 'purged', contentPurged: false }
    ]) {
      expect(() => reconcile(db, page({ rows: [row] }))).toThrowError(
        new JitMirrorError('malformed_row')
      )
    }
  })
})
