import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import type { JitTriState, JitTriggerSnapshot } from '../../shared/jitTriggerRuntime'
import { WindowsJitRuntime } from './jitRuntime'
import {
  initializeJitTriggerMirror,
  type JitLedgerMirrorPage,
  type JitMirrorDb
} from './jitTriggerMirror'

const snapshot = (revision = 'rev-1'): JitTriggerSnapshot => ({
  ownerId: 'user-1',
  accountGeneration: 1,
  headCommitId: 'head',
  commitSequence: 1,
  snapshotRevision: revision,
  complete: true,
  rows: [
    {
      memoryId: 'trigger-1',
      itemRevision: 1,
      updatedAt: '2026-08-24T12:00:00.000Z',
      triggerConditionJson: JSON.stringify({
        schema_version: 'jit_trigger.v1',
        match_mode: 'all',
        apps: ['Code'],
        action: { type: 'agent_prompt', prompt: 'Do the next step.' }
      }),
      action: { type: 'agent_prompt', prompt: 'Do the next step.' },
      wakeupBudgetPerDay: 1
    }
  ],
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

function makeRuntime(
  decision: JitTriState | (() => JitTriState) = 'enabled',
  trigger = snapshot(),
  clock: () => number = () => 100,
  ledgerPages: JitLedgerMirrorPage[] = [],
  frameExists: (frameId: number) => boolean = () => false
): {
  runtime: WindowsJitRuntime
  db: DatabaseSync
  reservations: Array<{
    eventId: string
    candidateId: string
    operation: string
    parentEventId?: string | null
  }>
} {
  const db = new DatabaseSync(':memory:')
  initializeJitTriggerMirror(db as unknown as JitMirrorDb)
  const reservations: Array<{
    eventId: string
    candidateId: string
    operation: string
    parentEventId?: string | null
  }> = []
  const runtime = new WindowsJitRuntime({
    db: db as unknown as JitMirrorDb,
    ownerId: () => 'user-1',
    accountGeneration: () => null,
    authorizationCurrent: () => true,
    now: clock,
    frameExists,
    client: {
      rolloutDecision: async () => ({
        rollout: typeof decision === 'function' ? decision() : decision,
        killSwitch: 'disabled',
        effective: typeof decision === 'function' ? decision() : decision,
        reason: 'test',
        errorClass: 'none'
      }),
      triggerSnapshot: async () => trigger,
      ledgerMirrorPage: async () =>
        ledgerPages.shift() ?? {
          schemaVersion: 'knowledge_ledger_mirror.v1' as const,
          ownerId: 'user-1',
          accountGeneration: 1,
          sourceGeneration: 1,
          writerEpoch: 1,
          headCommitId: 'head',
          commitSequence: 1,
          epochId: 'epoch-1',
          pageRevision: 'page-1',
          chainRevision: 'chain-1',
          scannedCount: 0,
          projectedCount: 0,
          terminalCount: 0,
          rows: [],
          aliases: [],
          nextCursor: null,
          finalPage: true,
          failureReason: null
        },
      reserveProactivity: async (input) => {
        reservations.push(input)
        return {
          reserved: true,
          receipt: {
            schemaVersion: 'jit_proactivity_event.v1',
            uid: 'user-1',
            eventId: input.eventId,
            candidateId: input.candidateId,
            operation: input.operation,
            accountGeneration: input.accountGeneration,
            triggerMemoryId: input.triggerMemoryId ?? null,
            triggerRevision: input.triggerRevision ?? null,
            budgetDay: '2026-08-24',
            deviceId: input.deviceId,
            createdAt: '2026-08-24T12:00:00.000Z',
            requestHash: 'a'.repeat(64),
            feedbackId: null,
            parentEventId: input.parentEventId ?? null
          }
        }
      }
    }
  })
  return { runtime, db, reservations }
}

describe('Windows JIT runtime authority', () => {
  it('requires backend enablement, reconciles the snapshot, and claims a planned wake', async () => {
    const { runtime, db } = makeRuntime()
    const admission = await runtime.admit(
      { appName: 'Code', occurredAt: new Date('2026-08-24T12:00:00Z') },
      '2026-08-24'
    )
    expect(admission.kind).toBe('planned')
    if (admission.kind !== 'planned') return
    expect(runtime.begin(admission.continuityKey)).toBe(true)
    expect(runtime.complete(admission.continuityKey)).toBe(true)
    expect(db.prepare("SELECT state FROM jit_wakeup_receipt WHERE lane='planned'").get()).toEqual({
      state: 'complete'
    })
    expect(
      (
        await runtime.admit(
          { appName: 'Code', occurredAt: new Date('2026-08-24T12:00:00Z') },
          '2026-08-24'
        )
      ).kind
    ).toBe('suppressed')
  })

  it('chains the paid full-turn reservation to the notification admission', async () => {
    const { runtime, reservations } = makeRuntime()
    const admission = await runtime.admit({ appName: 'Code' }, '2026-08-24')
    expect(admission.kind).toBe('planned')
    if (admission.kind !== 'planned') return
    const notification = await runtime.reserveOperation(admission, 'planned_notification')
    expect(notification).not.toBeNull()
    if (!notification) return
    const fullTurn = await runtime.reserveOperation(
      admission,
      'full_turn',
      notification.receipt.eventId
    )
    expect(fullTurn).not.toBeNull()
    expect(reservations.map((entry) => entry.operation)).toEqual([
      'planned_notification',
      'full_turn'
    ])
    expect(reservations[1].parentEventId).toBe(reservations[0].eventId)
    expect(reservations[1].candidateId).toBe(reservations[0].candidateId)
  })

  it('uses the legacy lane when rollout authority is disabled or unknown', async () => {
    expect(
      (await makeRuntime('disabled').runtime.admit({ appName: 'Code' }, '2026-08-24')).kind
    ).toBe('legacy_fallback')
    expect(
      (await makeRuntime('unknown').runtime.admit({ appName: 'Code' }, '2026-08-24')).kind
    ).toBe('legacy_fallback')
  })

  it('clears active authority when the current rollout expires or is killed', async () => {
    let now = 100
    let decision: JitTriState = 'enabled'
    const { runtime, db } = makeRuntime(
      () => decision,
      snapshot(),
      () => now
    )
    await runtime.admit({ appName: 'Code' }, '2026-08-24')
    expect(runtime.isAuthoritativeEnabled()).toBe(true)
    decision = 'disabled'
    now = 30_101
    expect(runtime.isAuthoritativeEnabled()).toBe(false)
    expect((await runtime.admit({ appName: 'Code' }, '2026-08-24')).kind).toBe('legacy_fallback')
    // The durable mirror is retained for rollback; only in-memory authority
    // caches and pending execution leases are cleared.
    expect(db.prepare('SELECT COUNT(*) AS n FROM jit_snapshot_receipt').get()).toEqual({ n: 1 })
  })

  it('suppresses incomplete snapshots instead of activating from partial data', async () => {
    const incomplete = snapshot()
    incomplete.complete = false
    incomplete.failureReason = 'query_failed'
    const { runtime } = makeRuntime('enabled', incomplete)
    expect((await runtime.admit({ appName: 'Code' }, '2026-08-24')).kind).toBe('suppressed')
  })

  it('keeps the prior ledger receipt when a torn cumulative page is received', async () => {
    let now = 100
    const ledgerPages: JitLedgerMirrorPage[] = []
    const { runtime, db } = makeRuntime('enabled', snapshot(), () => now, ledgerPages)
    await runtime.admit({ appName: 'Code' }, '2026-08-24')
    expect(db.prepare('SELECT projected_count FROM jit_ledger_snapshot_receipt').get()).toEqual({
      projected_count: 0
    })
    ledgerPages.push({
      schemaVersion: 'knowledge_ledger_mirror.v1',
      ownerId: 'user-1',
      accountGeneration: 1,
      sourceGeneration: 1,
      writerEpoch: 1,
      headCommitId: 'head',
      commitSequence: 1,
      epochId: 'epoch-1',
      pageRevision: 'page-torn',
      chainRevision: 'chain-torn',
      scannedCount: 1,
      projectedCount: 1,
      terminalCount: 0,
      rows: [],
      aliases: [],
      nextCursor: null,
      finalPage: true,
      failureReason: null
    })
    now = 30_101
    expect((await runtime.admit({ appName: 'Code' }, '2026-08-24')).kind).toBe('suppressed')
    expect(db.prepare('SELECT projected_count FROM jit_ledger_snapshot_receipt').get()).toEqual({
      projected_count: 0
    })
  })

  it('routes an ambiguous planned trigger through one server-reserved nano triage', async () => {
    const ambiguous = snapshot()
    ambiguous.rows[0].triggerConditionJson = JSON.stringify({
      schema_version: 'jit_trigger.v1',
      match_mode: 'all',
      entity_aliases: { person: ['Alex'], project: ['Alex'] },
      apps: ['Code'],
      action: { type: 'agent_prompt', prompt: 'Do the next step.' }
    })
    const { runtime, db } = makeRuntime('enabled', ambiguous)
    const admission = await runtime.admitAmbiguousPlanned(
      { appName: 'Code', entityLabels: ['Alex'] },
      '2026-08-24',
      async () => 'approved'
    )
    expect(admission.kind).toBe('planned')
    expect(db.prepare('SELECT operation FROM jit_proactivity_reservation_receipt').all()).toEqual([
      { operation: 'nano_triage' }
    ])
  })

  it('only pins a Rewind frame after existence validation', () => {
    const absent = makeRuntime(
      'enabled',
      snapshot(),
      () => 100,
      [],
      () => false
    )
    expect(absent.runtime.pinConversationKeyframe(42, 'agent-conversation-1')).toBe(false)
    expect(absent.db.prepare('SELECT COUNT(*) AS n FROM jit_keyframe_pin').get()).toEqual({ n: 0 })

    const present = makeRuntime(
      'enabled',
      snapshot(),
      () => 100,
      [],
      (frameId) => frameId === 42
    )
    expect(
      present.runtime.pinConversationKeyframe(
        42,
        'agent-conversation-1',
        'C:/frames/42.jpg',
        'renderer-chat-42'
      )
    ).toBe(true)
    expect(
      present.db.prepare('SELECT frame_id, renderer_deletion_key FROM jit_keyframe_pin').get()
    ).toEqual({
      frame_id: 42,
      renderer_deletion_key: 'renderer-chat-42'
    })
  })
})
