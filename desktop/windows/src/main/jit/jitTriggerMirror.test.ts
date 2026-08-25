import { DatabaseSync } from 'node:sqlite'
import { createHash } from 'node:crypto'
import { describe, expect, it } from 'vitest'
import type { JitTriggerSnapshot } from '../../shared/jitTriggerRuntime'
import {
  beginJitWakeup,
  cancelJitWakeup,
  claimJitWakeup,
  completeJitWakeup,
  enqueueJitFeedback,
  initializeJitTriggerMirror,
  deriveJitOpaqueId,
  getOrCreateJitInstallationId,
  listAllJitKeyframePinDetails,
  listPendingJitKeyframeCleanup,
  isJitConversationKeyframePinned,
  jitInstallationDeviceId,
  claimJitAmbientContext,
  markJitTemporaryFrame,
  pruneJitTemporaryFrames,
  pinJitConversationKeyframe,
  takeJitConversationKeyframePins,
  listPendingJitFeedback,
  markJitFeedbackResult,
  markJitFeedbackSending,
  readCompiledJitTriggers,
  queryJitHistoryPage,
  reconcileJitTriggerSnapshot,
  JitMirrorError,
  type JitMirrorDb
} from './jitTriggerMirror'

const db = (): DatabaseSync => {
  const value = new DatabaseSync(':memory:')
  initializeJitTriggerMirror(value as unknown as JitMirrorDb)
  value.exec('CREATE TABLE legacy_memories (id TEXT PRIMARY KEY, content TEXT)')
  value.prepare('INSERT INTO legacy_memories VALUES (?, ?)').run('legacy', 'must survive')
  return value
}

const snapshot = (revision = 'rev-1', rows = 1): JitTriggerSnapshot => ({
  ownerId: 'user-1',
  accountGeneration: 3,
  headCommitId: 'head-1',
  commitSequence: 4,
  snapshotRevision: revision,
  complete: true,
  rows: Array.from({ length: rows }, (_, index) => ({
    memoryId: `trigger-${index + 1}`,
    itemRevision: 1,
    updatedAt: '2026-08-24T12:00:00.000Z',
    triggerConditionJson: JSON.stringify({
      schema_version: 'jit_trigger.v1',
      match_mode: 'all',
      apps: ['Code'],
      action: { type: 'agent_prompt', prompt: 'Do the next step.' }
    }),
    action: { type: 'agent_prompt' as const, prompt: 'Do the next step.' },
    wakeupBudgetPerDay: 1
  })),
  policy: {
    schemaVersion: 'jit_trigger_policy.v1',
    plannedNotificationsPerTriggerPerDay: 1,
    totalProactiveNotificationsPerDay: 3,
    ambiguousNanoTriagesPerDay: 8,
    fullAgentTurnsPerCandidate: 1,
    maxCalendarEvents: 32,
    embedding: {
      enabled: false,
      matchSimilarity: 0.82,
      triageSimilarity: 0.74,
      modelId: null,
      modelVersion: null,
      language: null
    }
  }
})

describe('Windows JIT durable mirror', () => {
  it('uses a persisted random installation secret for opaque retained IDs', () => {
    const value = db() as unknown as JitMirrorDb
    const installationId = getOrCreateJitInstallationId(value, () => 'a'.repeat(64))
    expect(installationId).toBe('a'.repeat(64))
    expect(getOrCreateJitInstallationId(value, () => 'b'.repeat(64))).toBe(installationId)

    const retainedContextId = deriveJitOpaqueId(value, 'context', 'Code:editor')
    const retainedDeviceId = jitInstallationDeviceId(value)
    expect(retainedContextId).toMatch(/^[a-f0-9]{64}$/)
    expect(retainedDeviceId).toMatch(/^[a-f0-9]{64}$/)
    expect(retainedContextId).not.toBe('Code:editor')
    expect(retainedContextId).not.toBe('a'.repeat(64))
    expect(retainedContextId).not.toBe(createHash('sha256').update('Code:editor').digest('hex'))
    expect(retainedDeviceId).not.toBe(
      createHash('sha256').update('known-windows-hostname').digest('hex')
    )

    const other = db() as unknown as JitMirrorDb
    getOrCreateJitInstallationId(other, () => 'b'.repeat(64))
    expect(deriveJitOpaqueId(other, 'context', 'Code:editor')).not.toBe(retainedContextId)
  })

  it('suppresses unchanged ambient contexts until cooldown and permits semantic change', () => {
    const value = db() as unknown as JitMirrorDb
    expect(
      claimJitAmbientContext(value, {
        contextId: 'Code:editor',
        semanticFingerprint: 'a'.repeat(64),
        now: 100,
        cooldownMs: 1_000
      })
    ).toBe(true)
    expect(
      claimJitAmbientContext(value, {
        contextId: 'Code:editor',
        semanticFingerprint: 'a'.repeat(64),
        now: 500,
        cooldownMs: 1_000
      })
    ).toBe(false)
    expect(
      claimJitAmbientContext(value, {
        contextId: 'Code:editor',
        semanticFingerprint: 'b'.repeat(64),
        now: 500,
        cooldownMs: 1_000
      })
    ).toBe(true)
  })

  it('keeps ambient frames temporary and prunes only expired temporary rows', () => {
    const value = db() as unknown as JitMirrorDb
    markJitTemporaryFrame(value, { frameId: 1, ownerId: 'user-1', createdAt: 100, expiresAt: 200 })
    markJitTemporaryFrame(value, { frameId: 2, ownerId: 'user-1', createdAt: 100, expiresAt: 500 })
    expect(pruneJitTemporaryFrames(value, 200)).toBe(1)
    expect(value.prepare('SELECT frame_id FROM jit_temporary_frame').all()).toEqual([
      { frame_id: 2 }
    ])
    expect(isJitConversationKeyframePinned(value, 2)).toBe(false)
  })

  it('converges exhaustively, deletes only JIT rows, and preserves legacy data', () => {
    const value = db()
    const first = reconcileJitTriggerSnapshot(
      value as unknown as JitMirrorDb,
      snapshot(),
      'user-1',
      100
    )
    expect(first.rowCount).toBe(1)
    expect(readCompiledJitTriggers(value as unknown as JitMirrorDb, first)).toHaveLength(1)
    const second = reconcileJitTriggerSnapshot(
      value as unknown as JitMirrorDb,
      { ...snapshot('rev-2', 0), commitSequence: 5 },
      'user-1',
      200
    )
    expect(second.rowCount).toBe(0)
    expect(readCompiledJitTriggers(value as unknown as JitMirrorDb, second)).toEqual([])
    expect(value.prepare('SELECT content FROM legacy_memories WHERE id=?').get('legacy')).toEqual({
      content: 'must survive'
    })
  })

  it('rejects stale and conflicting receipts before changing the mirror', () => {
    const value = db()
    reconcileJitTriggerSnapshot(value as unknown as JitMirrorDb, snapshot('rev-1'), 'user-1')
    expect(() =>
      reconcileJitTriggerSnapshot(
        value as unknown as JitMirrorDb,
        { ...snapshot('rev-0'), commitSequence: 3 },
        'user-1'
      )
    ).toThrowError(new JitMirrorError('stale_revision'))
    expect(() =>
      reconcileJitTriggerSnapshot(
        value as unknown as JitMirrorDb,
        { ...snapshot('different'), commitSequence: 4 },
        'user-1'
      )
    ).toThrowError(new JitMirrorError('conflicting_revision'))
    expect(value.prepare('SELECT COUNT(*) AS n FROM jit_trigger_mirror').get()).toEqual({ n: 1 })
  })

  it('preserves install-scoped keyframe cleanup authority across generation transitions', () => {
    const value = db()
    reconcileJitTriggerSnapshot(value as unknown as JitMirrorDb, snapshot('rev-1'), 'user-1', 100)
    pinJitConversationKeyframe(value as unknown as JitMirrorDb, {
      frameId: 77,
      ownerId: 'user-1',
      conversationId: 'jit:old-account',
      imagePath: 'C:/rewind/77.jpg',
      pinnedAt: 101
    })

    const next = {
      ...snapshot('rev-2', 0),
      ownerId: 'user-2',
      accountGeneration: 4,
      commitSequence: 5
    }
    reconcileJitTriggerSnapshot(value as unknown as JitMirrorDb, next, 'user-2', 200)

    expect(listAllJitKeyframePinDetails(value as unknown as JitMirrorDb)).toEqual([
      {
        frameId: 77,
        ownerId: 'user-1',
        conversationId: 'jit:old-account',
        imagePath: 'C:/rewind/77.jpg'
      }
    ])
    expect(listPendingJitKeyframeCleanup(value as unknown as JitMirrorDb, 200)).toEqual([
      expect.objectContaining({
        frameId: 77,
        imagePath: 'C:/rewind/77.jpg',
        nextAttemptAt: 200
      })
    ])
  })

  it('deduplicates local leases while leaving daily budgets to the server', () => {
    const value = db()
    const common = {
      budgetDay: '2026-08-24',
      snapshotRevision: 'rev-1',
      observationFingerprint: 'fp',
      now: 100
    }
    const first = claimJitWakeup(value as unknown as JitMirrorDb, {
      ...common,
      continuityKey: 'one',
      triggerId: 'trigger-1',
      lane: 'planned',
      budget: 1
    })
    expect(first).not.toBeNull()
    expect(
      claimJitWakeup(value as unknown as JitMirrorDb, {
        ...common,
        continuityKey: 'two',
        triggerId: 'trigger-1',
        lane: 'planned',
        budget: 1
      })
    ).not.toBeNull()
    const nano = claimJitWakeup(value as unknown as JitMirrorDb, {
      ...common,
      continuityKey: 'nano',
      triggerId: 'ambient:x',
      lane: 'ambient_nano',
      budget: 8,
      globalDailyBudget: 8
    })
    expect(nano).not.toBeNull()
    expect(beginJitWakeup(value as unknown as JitMirrorDb, nano!, 101)).toBe(true)
    expect(completeJitWakeup(value as unknown as JitMirrorDb, nano!, 102)).toBe(true)
    expect(
      value.prepare("SELECT COUNT(*) AS n FROM jit_wakeup_receipt WHERE lane='ambient_nano'").get()
    ).toEqual({ n: 1 })
  })

  it('still allows bounded nano triage after the full-notification budget is spent', () => {
    const value = db()
    const common = {
      budgetDay: '2026-08-24',
      snapshotRevision: 'rev-1',
      observationFingerprint: 'fp',
      now: 100,
      budget: null
    } as const
    for (const continuityKey of ['one', 'two', 'three']) {
      expect(
        claimJitWakeup(value as unknown as JitMirrorDb, {
          ...common,
          continuityKey,
          triggerId: continuityKey,
          lane: 'ambient',
          globalDailyBudget: 3
        })
      ).not.toBeNull()
    }
    expect(
      claimJitWakeup(value as unknown as JitMirrorDb, {
        ...common,
        continuityKey: 'nano-after-full-budget',
        triggerId: 'ambient:context',
        lane: 'ambient_nano',
        budget: 8,
        globalDailyBudget: 8
      })
    ).not.toBeNull()
  })

  it('persists explicit feedback without fabricating delivery success', () => {
    const value = db() as unknown as JitMirrorDb
    const eventId = 'f'.repeat(64)
    enqueueJitFeedback(value, {
      eventId,
      ownerId: 'user-1',
      accountGeneration: 3,
      action: 'false_positive',
      subjectId: 'trigger-1',
      triggerRevision: 1,
      occurredAt: 100,
      snoozedUntil: null
    })
    expect(listPendingJitFeedback(value)).toHaveLength(1)
    markJitFeedbackSending(value, eventId, 100)
    markJitFeedbackResult(value, eventId, false, 'endpoint unavailable', 100)
    expect(listPendingJitFeedback(value, 32, 30_100)[0].attempts).toBe(1)
    markJitFeedbackSending(value, eventId, 30_100)
    markJitFeedbackResult(value, eventId, true, undefined, 30_100)
    expect(listPendingJitFeedback(value)).toHaveLength(0)
  })

  it('cancels an unstarted claim during rollback without leaving an active lease', () => {
    const value = db()
    const claim = claimJitWakeup(value as unknown as JitMirrorDb, {
      continuityKey: 'cancel-me',
      triggerId: 'trigger-1',
      lane: 'planned',
      budgetDay: '2026-08-24',
      snapshotRevision: 'rev-1',
      observationFingerprint: 'fp',
      budget: 1,
      now: 100
    })
    expect(claim).not.toBeNull()
    expect(cancelJitWakeup(value as unknown as JitMirrorDb, claim!, 101)).toBe(true)
    expect(value.prepare('SELECT state FROM jit_wakeup_receipt').get()).toEqual({
      state: 'complete'
    })
  })

  it('pins an attached conversation keyframe in the JIT namespace', () => {
    const value = db() as unknown as JitMirrorDb
    pinJitConversationKeyframe(value, {
      frameId: 42,
      ownerId: 'user-1',
      conversationId: 'jit:candidate-1',
      pinnedAt: 101
    })
    expect(isJitConversationKeyframePinned(value, 42)).toBe(true)
    expect(value.prepare('SELECT conversation_id, pinned_at FROM jit_keyframe_pin').get()).toEqual({
      conversation_id: 'jit:candidate-1',
      pinned_at: 101
    })
    expect(() =>
      pinJitConversationKeyframe(value, {
        frameId: 43,
        ownerId: 'user-1',
        conversationId: 'jit:candidate-1',
        pinnedAt: 102
      })
    ).toThrowError(new JitMirrorError('conflicting_revision'))
    expect(takeJitConversationKeyframePins(value, 'jit:candidate-1')).toEqual([42])
    expect(isJitConversationKeyframePinned(value, 42)).toBe(false)
  })

  it('pages all history, excludes hidden/rejected by default, and exposes audit completeness', () => {
    const value = db()
    value
      .prepare(
        `INSERT INTO jit_ledger_snapshot_receipt (owner_id, account_generation, source_generation, writer_epoch, head_commit_id, commit_sequence, epoch_id, page_revision, chain_revision, scanned_count, projected_count, terminal_count, chain_json, row_count, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
      )
      .run('user-1', 3, 3, 1, 'h', 1, 'e', 'p', 'c', 4, 4, 2, '{}', 4, 1)
    for (let i = 0; i < 130; i++) {
      value
        .prepare(
          'INSERT INTO jit_history_mirror (history_id, account_generation, item_revision, payload_json) VALUES (?, ?, ?, ?)'
        )
        .run(
          `history-${String(i).padStart(3, '0')}`,
          3,
          1,
          JSON.stringify({ text: 'needle', status: 'active' })
        )
    }
    value
      .prepare(
        'INSERT INTO jit_history_mirror (history_id, account_generation, item_revision, payload_json) VALUES (?, ?, ?, ?)'
      )
      .run('history-025-hidden', 3, 1, JSON.stringify({ text: 'needle', status: 'hidden' }))
    const mirror = value as unknown as JitMirrorDb
    const first = queryJitHistoryPage(mirror, 'user-1', 3, 'needle', { limit: 20 })
    expect(first.items).toHaveLength(20)
    expect(first.truncated).toBe(true)
    expect(first.complete).toBe(false)
    const second = queryJitHistoryPage(mirror, 'user-1', 3, 'needle', {
      limit: 50,
      cursor: first.nextCursor
    })
    expect(second.items).toHaveLength(50)
    expect(second.complete).toBe(false)
    const audit = queryJitHistoryPage(mirror, 'user-1', 3, 'needle', {
      limit: 50,
      cursor: first.nextCursor,
      audit: true
    })
    expect(audit.items.some((item) => item.id === 'history-025-hidden')).toBe(true)
  })

  it('reports EOF truthfully for a full SQL batch and keeps the consumed cursor when the limit is larger', () => {
    const value = db()
    value
      .prepare(
        `INSERT INTO jit_ledger_snapshot_receipt (owner_id, account_generation, source_generation, writer_epoch, head_commit_id, commit_sequence, epoch_id, page_revision, chain_revision, scanned_count, projected_count, terminal_count, chain_json, row_count, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
      )
      .run('user-1', 3, 3, 1, 'h', 1, 'e', 'p', 'c', 64, 64, 64, '{}', 64, 1)
    for (let i = 0; i < 64; i++) {
      value
        .prepare(
          'INSERT INTO jit_history_mirror (history_id, account_generation, item_revision, payload_json) VALUES (?, ?, ?, ?)'
        )
        .run(`history-${String(i).padStart(3, '0')}`, 3, 1, JSON.stringify({ text: 'needle' }))
    }
    const mirror = value as unknown as JitMirrorDb
    const page = queryJitHistoryPage(mirror, 'user-1', 3, 'needle', { limit: 50 })
    expect(page.items).toHaveLength(50)
    expect(page.complete).toBe(false)
    expect(page.truncated).toBe(true)
    expect(page.nextCursor).toBe('history-049')
    const tail = queryJitHistoryPage(mirror, 'user-1', 3, 'needle', {
      limit: 50,
      cursor: page.nextCursor
    })
    expect(tail.items).toHaveLength(14)
    expect(tail.complete).toBe(true)
    expect(tail.truncated).toBe(false)
    expect(tail.nextCursor).toBeNull()
  })

  it('reports a short final SQL batch as complete when the limit exceeds its rows', () => {
    const value = db()
    value
      .prepare(
        `INSERT INTO jit_ledger_snapshot_receipt (owner_id, account_generation, source_generation, writer_epoch, head_commit_id, commit_sequence, epoch_id, page_revision, chain_revision, scanned_count, projected_count, terminal_count, chain_json, row_count, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
      )
      .run('user-1', 3, 3, 1, 'h', 1, 'e', 'p', 'c', 12, 12, 12, '{}', 12, 1)
    for (let i = 0; i < 12; i++) {
      value
        .prepare(
          'INSERT INTO jit_history_mirror (history_id, account_generation, item_revision, payload_json) VALUES (?, ?, ?, ?)'
        )
        .run(`short-${String(i).padStart(2, '0')}`, 3, 1, JSON.stringify({ text: 'needle' }))
    }
    const page = queryJitHistoryPage(value as unknown as JitMirrorDb, 'user-1', 3, 'needle', {
      limit: 50
    })
    expect(page.items).toHaveLength(12)
    expect(page.complete).toBe(true)
    expect(page.truncated).toBe(false)
    expect(page.nextCursor).toBeNull()
  })

  it('does not invent a continuation when a final sub-64 batch exactly fills the limit', () => {
    const value = db()
    value
      .prepare(
        `INSERT INTO jit_ledger_snapshot_receipt (owner_id, account_generation, source_generation, writer_epoch, head_commit_id, commit_sequence, epoch_id, page_revision, chain_revision, scanned_count, projected_count, terminal_count, chain_json, row_count, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
      )
      .run('user-1', 3, 3, 1, 'h', 1, 'e', 'p', 'c', 50, 50, 50, '{}', 50, 1)
    for (let i = 0; i < 50; i++) {
      value
        .prepare(
          'INSERT INTO jit_history_mirror (history_id, account_generation, item_revision, payload_json) VALUES (?, ?, ?, ?)'
        )
        .run(`exact-${String(i).padStart(3, '0')}`, 3, 1, JSON.stringify({ text: 'needle' }))
    }
    const page = queryJitHistoryPage(value as unknown as JitMirrorDb, 'user-1', 3, 'needle', {
      limit: 50
    })
    expect(page.items).toHaveLength(50)
    expect(page.complete).toBe(true)
    expect(page.truncated).toBe(false)
    expect(page.nextCursor).toBeNull()
  })
})
