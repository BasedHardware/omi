import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it, vi } from 'vitest'
import type {
  JitCalendarEvent,
  JitTriState,
  JitTriggerSnapshot
} from '../../shared/jitTriggerRuntime'
import type { RewindFrame } from '../../shared/types'
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

const frameFixture = (over: Partial<RewindFrame> = {}): RewindFrame => ({
  id: 7,
  ts: Date.parse('2026-08-24T12:00:00Z'),
  app: 'Code',
  windowTitle: 'runtime.ts',
  processName: 'Code.exe',
  ocrText: 'const x = 1',
  imagePath: 'C:/frames/7.jpg',
  width: 100,
  height: 100,
  indexed: 1,
  ...over
})

function makeRuntime(
  decision: JitTriState | (() => JitTriState) = 'enabled',
  trigger = snapshot(),
  clock: () => number = () => 100,
  ledgerPages: JitLedgerMirrorPage[] = [],
  frameExists: (frameId: number) => boolean = () => false,
  calendarObservation?: () => Promise<{ authorized: boolean; events: JitCalendarEvent[] }>
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
    ...(calendarObservation ? { calendarObservation } : {}),
    client: {
      rolloutDecision: async () => {
        // One evaluation per request: the decision seam may count calls or throw.
        const state = typeof decision === 'function' ? decision() : decision
        return {
          rollout: state,
          killSwitch: 'disabled' as const,
          effective: state,
          reason: 'test',
          errorClass: 'none' as const
        }
      },
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
    const admission = await runtime.admit({ appName: 'Code' }, '2026-08-24')
    expect(admission).toEqual({
      kind: 'suppressed',
      reason: 'authoritative_snapshot_unavailable'
    })
    expect(runtime.shouldSuppressLegacyInsight()).toBe(true)
    expect(runtime.isAuthoritativeEnabled()).toBe(false)
  })

  it('suppresses a complete empty watchlist instead of ambient fallback', async () => {
    const empty = snapshot()
    empty.rows = []
    const { runtime } = makeRuntime('enabled', empty)
    const admission = await runtime.admit({ appName: 'Code' }, '2026-08-24')
    expect(admission).toEqual({ kind: 'suppressed', reason: 'empty_watchlist' })
    expect(runtime.shouldSuppressLegacyInsight()).toBe(true)
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
    const tornAdmission = await runtime.admit({ appName: 'Code' }, '2026-08-24')
    // Trigger snapshot is sufficient: the standing watch still evaluates. The
    // first visit already claimed the day, so this is a budget suppress, not a
    // snapshot failure and not a return to Insight.
    expect(tornAdmission).toEqual({
      kind: 'suppressed',
      reason: 'planned_budget_or_duplicate'
    })
    expect(db.prepare('SELECT projected_count FROM jit_ledger_snapshot_receipt').get()).toEqual({
      projected_count: 0
    })
    expect(runtime.shouldSuppressLegacyInsight()).toBe(true)
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

  it('caches a failed rollout decision instead of re-asking on every frame', async () => {
    let now = 0
    let requests = 0
    let offline = true
    const { runtime } = makeRuntime(
      () => {
        requests += 1
        if (offline) throw new Error('offline')
        return 'enabled'
      },
      snapshot(),
      () => now
    )
    // The coordinator analyzes a frame roughly every three seconds. Without a
    // failure cache this loop was one authenticated request per frame, forever.
    for (let i = 0; i < 20; i++) {
      now += 3_000
      expect((await runtime.admit({ appName: 'Code' }, '2026-08-24')).kind).toBe('legacy_fallback')
    }
    // First attempt, then one retry after the 30s backoff; the second failure
    // doubles it to 60s, which the remaining frames are still inside.
    expect(requests).toBe(2)
    now = 93_000
    expect((await runtime.admit({ appName: 'Code' }, '2026-08-24')).kind).toBe('legacy_fallback')
    expect(requests).toBe(3)
    // A success clears the backoff, so recovery is not delayed by past failures.
    offline = false
    now = 213_001
    expect((await runtime.admit({ appName: 'Code' }, '2026-08-24')).kind).toBe('planned')
    expect(requests).toBe(4)
    offline = true
    now = 243_002
    expect((await runtime.admit({ appName: 'Code' }, '2026-08-24')).kind).toBe('legacy_fallback')
    expect(requests).toBe(5)
    now = 243_003
    expect((await runtime.admit({ appName: 'Code' }, '2026-08-24')).kind).toBe('legacy_fallback')
    expect(requests).toBe(5)
  })

  it('buys no calendar read for a user the server has not admitted', async () => {
    let calendarReads = 0
    const { runtime } = makeRuntime(
      'disabled',
      snapshot(),
      () => 100,
      [],
      () => false,
      async () => {
        calendarReads += 1
        return { authorized: true, events: [{ title: 'Standup', eventType: 'calendar_event' }] }
      }
    )
    const observation = await runtime.observationForFrame(frameFixture())
    expect(calendarReads).toBe(0)
    expect(observation.calendarAuthorized).toBeUndefined()
    expect(observation.calendarEvents).toBeUndefined()
    expect((await runtime.admit(observation, '2026-08-24')).kind).toBe('legacy_fallback')
    // A non-cohort user must pay nothing for a lane the server refuses.
    expect(calendarReads).toBe(0)
  })

  it('adds calendar evidence once the cached authority says the lane is enabled', async () => {
    let calendarReads = 0
    const { runtime } = makeRuntime(
      'enabled',
      snapshot(),
      () => 100,
      [],
      () => false,
      async () => {
        calendarReads += 1
        return { authorized: true, events: [{ title: 'Standup', eventType: 'calendar_event' }] }
      }
    )
    // The very first frame is evaluated locally; admission populates the caches.
    await runtime.observationForFrame(frameFixture())
    expect(calendarReads).toBe(0)
    await runtime.admit({ appName: 'Code' }, '2026-08-24')
    const observation = await runtime.observationForFrame(frameFixture())
    expect(calendarReads).toBe(1)
    expect(observation.calendarAuthorized).toBe(true)
    expect(observation.calendarEvents).toEqual([{ title: 'Standup', eventType: 'calendar_event' }])
  })

  it('degrades to the legacy lane when the mirror tables are missing', async () => {
    const { runtime, db } = makeRuntime()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    for (const row of db
      .prepare(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'jit\\_%' ESCAPE '\\'"
      )
      .all() as { name: string }[])
      db.exec(`DROP TABLE ${row.name}`)
    // A failed mirror bootstrap leaves the database usable and the JIT lane
    // inert: this must suppress, not throw out of the coordinator.
    expect((await runtime.admit({ appName: 'Code' }, '2026-08-24')).kind).toBe('suppressed')
    expect(runtime.pinConversationKeyframe(42, 'agent-conversation-1')).toBe(false)
    expect(runtime.markAmbientFrameTemporary(42)).toBe(false)
    expect(runtime.shouldSuppressLegacyInsight()).toBe(true)
    vi.restoreAllMocks()
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
