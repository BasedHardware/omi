import { describe, it, expect, beforeEach } from 'vitest'
import { DatabaseSync } from 'node:sqlite'
import { CONTEXT_BUCKET_SCHEMA } from './contextBucketSchema'
import type { ContextBucketDb, ContextVisitFence } from './contextBucketStore'
import {
  beginDeliveryAttemptOn,
  advanceDeliveryOn,
  reconcileAbandonedDeliveriesOn,
  recentDeliveredForBucketOn,
  recentDeliveredForAssignedTagsOn,
  deliveryProvenanceOn,
  insertCandidateOn,
  lookupArmedOn,
  consumeCandidateOn,
  declineCandidateOn,
  restoreCandidateOn,
  groundingFactIDsValidOn,
  expireStaleCandidatesOn,
  hasArmedCandidateWithValidGroundingOn,
  assignWorkstreamTagOn,
  tagsForBucketOn,
  workstreamTagCountsOn,
  workstreamPoolOn,
  recentContextPoolOn,
  fetchEligibleBucketsOn,
  topFactsForBucketOn,
  maxValidatedFactUpdatedAtOn
} from './proactivityLedger'
import type { DeliveryGateInput } from '../assistants/director/deliveryPolicy'

const T0 = 1_760_000_000_000
const HOUR = 60 * 60 * 1000

let db: ContextBucketDb

beforeEach(() => {
  db = new DatabaseSync(':memory:') as unknown as ContextBucketDb
  db.exec(CONTEXT_BUCKET_SCHEMA)
})

function seedBucket(id: string): void {
  db.prepare(
    `INSERT INTO context_buckets (id, subjectKind, subjectID, workstreamID, createdAt, updatedAt)
     VALUES (?, 'context', ?, NULL, ?, ?)`
  ).run(id, `subject-${id}`, T0, T0)
}

function seedVisit(id: number, bucketID: string | null): ContextVisitFence {
  db.prepare(
    `INSERT INTO context_visits (id, contextGeneration, poolEpoch, bucketID, appName, rawContextKey, normalizedContextKey, referenceHash, startedAt, outcome, createdAt, updatedAt)
     VALUES (?, 1, 1, ?, 'Code', 'raw', 'norm', 'sha256:x', ?, 'active', ?, ?)`
  ).run(id, bucketID, T0, T0, T0)
  return { visitID: id, contextGeneration: 1, poolEpoch: 1, bucketID, startedAt: T0 }
}

function seedVersion(id: number, bucketID: string): void {
  db.prepare(
    `INSERT INTO bucket_versions (id, bucketID, version, header, frozenRankedSegment, rankedTokenCount, createdAt)
     VALUES (?, ?, ?, 'Persistent work context.', X'', 0, ?)`
  ).run(id, bucketID, id, T0)
}

function seedFact(
  id: string,
  bucketID: string,
  over: Partial<{
    validityState: string
    notifyWorthiness: number
    createdAt: number
    updatedAt: number
    workstreamTag: string | null
    entryID: string
    statement: string
    expiresAt: number | null
  }> = {}
): void {
  const entryID = over.entryID ?? `e-${id}`
  const existingEntry = db.prepare(`SELECT 1 AS ok FROM bucket_entries WHERE id = ?`).get(entryID)
  if (!existingEntry) {
    // node:sqlite enforces foreign keys; entries need a backing visit row.
    if (!db.prepare(`SELECT 1 AS ok FROM context_visits WHERE id = 1`).get()) {
      db.prepare(
        `INSERT INTO context_visits (id, contextGeneration, poolEpoch, bucketID, appName, rawContextKey, normalizedContextKey, referenceHash, startedAt, outcome, createdAt, updatedAt)
         VALUES (1, 1, 1, ?, 'Code', 'raw', 'norm', 'sha256:seed', ?, 'completed', ?, ?)`
      ).run(bucketID, T0, T0, T0)
    }
    db.prepare(
      `INSERT INTO bucket_entries (id, bucketID, visitID, appName, rawContextKey, normalizedContextKey, narrative, evidenceRefsJson, tokenCount, createdAt)
       VALUES (?, ?, 1, 'Code', 'raw', 'norm', 'n', '[]', 1, ?)`
    ).run(entryID, bucketID, T0)
  }
  db.prepare(
    `INSERT INTO bucket_facts (id, bucketID, entryID, appName, statement, identifiersJson, evidenceText, evidenceRefsJson, validityState, confidence, notifyWorthiness, expiresAt, createdAt, updatedAt, workstreamTag)
     VALUES (?, ?, ?, 'Code', ?, '[]', 'e', '[]', ?, 1, ?, ?, ?, ?, ?)`
  ).run(
    id,
    bucketID,
    entryID,
    over.statement ?? `statement ${id}`,
    over.validityState ?? 'validated',
    over.notifyWorthiness ?? 0.7,
    over.expiresAt ?? null,
    over.createdAt ?? T0,
    over.updatedAt ?? T0,
    over.workstreamTag ?? null
  )
}

const gate = (over: Partial<DeliveryGateInput> = {}): DeliveryGateInput => ({
  masterEnabled: true,
  frequencyLevel: 3,
  paywalled: false,
  cooldownMs: 600 * 1000,
  dailyLimit: 40,
  lastGlobalPresentationAt: null,
  ...over
})

describe('delivery reservation', () => {
  it('rejects at the free gate in order: master, frequency, paywall', () => {
    seedBucket('b')
    const fence = seedVisit(1, 'b')
    expect(beginDeliveryAttemptOn(db, fence, gate({ masterEnabled: false }), T0)).toEqual({
      rejected: 'masterDisabled'
    })
    expect(beginDeliveryAttemptOn(db, fence, gate({ frequencyLevel: 0 }), T0)).toEqual({
      rejected: 'frequencyDisabled'
    })
    expect(beginDeliveryAttemptOn(db, fence, gate({ paywalled: true }), T0)).toEqual({
      rejected: 'paywalled'
    })
  })

  it('reserves once per (visit, bucket version), including the NULL-version case', () => {
    seedBucket('b')
    const fence = seedVisit(1, 'b')
    const first = beginDeliveryAttemptOn(db, fence, gate(), T0)
    expect('reservationId' in first).toBe(true)
    expect(beginDeliveryAttemptOn(db, fence, gate({ cooldownMs: 0 }), T0 + 1)).toEqual({
      rejected: 'duplicate'
    })

    // A republished version re-enables the same visit.
    seedVersion(7, 'b')
    const second = beginDeliveryAttemptOn(
      db,
      fence,
      gate({ cooldownMs: 0, dailyLimit: 40 }),
      T0 + 2
    )
    expect('reservationId' in second).toBe(true)
  })

  it('cooldown anchors on delivered rows, the global presentation clock, and in-flight attempts', () => {
    seedBucket('b')
    const fence = seedVisit(1, 'b')
    const other = seedVisit(2, 'b')
    seedVersion(1, 'b')

    // In-flight attempt from another visit holds the cooldown.
    const r = beginDeliveryAttemptOn(db, other, gate({ cooldownMs: 600_000 }), T0)
    expect('reservationId' in r).toBe(true)
    expect(beginDeliveryAttemptOn(db, fence, gate({ cooldownMs: 600_000 }), T0 + 60_000)).toEqual({
      rejected: 'cooldown'
    })

    // Resolving it as failed releases the anchor entirely (failed rows are excluded).
    advanceDeliveryOn(db, {
      id: (r as { reservationId: string }).reservationId,
      state: 'failed',
      decisionType: 'silence',
      provenanceJson: '{"failure":"abandoned"}',
      at: T0 + 61_000
    })
    const after = beginDeliveryAttemptOn(db, fence, gate({ cooldownMs: 600_000 }), T0 + 62_000)
    expect('reservationId' in after).toBe(true)

    // The cross-assistant global presentation clock also anchors.
    const third = seedVisit(3, 'b')
    expect(
      beginDeliveryAttemptOn(
        db,
        third,
        gate({ cooldownMs: 600_000, lastGlobalPresentationAt: T0 + 400_000 }),
        T0 + 500_000
      )
    ).toEqual({ rejected: 'cooldown' })
  })

  it('daily budget counts the trailing 24h excluding suppressed and failed rows', () => {
    seedBucket('b')
    const insert = db.prepare(
      `INSERT INTO proactive_deliveries (id, decisionType, lifecycleState, provenanceJson, attemptedAt, expiresAt, createdAt)
       VALUES (?, 'insight', ?, '{}', ?, ?, ?)`
    )
    insert.run('d1', 'delivered', T0 - HOUR, T0 + 30 * 24 * HOUR, T0 - HOUR)
    insert.run('d2', 'suppressed', T0 - HOUR, T0 + 30 * 24 * HOUR, T0 - HOUR)
    insert.run('d3', 'failed', T0 - HOUR, T0 + 30 * 24 * HOUR, T0 - HOUR)
    insert.run('d4', 'delivered', T0 - 25 * HOUR, T0 + 30 * 24 * HOUR, T0 - 25 * HOUR)

    const fence = seedVisit(1, 'b')
    // Only d1 counts: limit 1 is already spent.
    expect(beginDeliveryAttemptOn(db, fence, gate({ cooldownMs: 0, dailyLimit: 1 }), T0)).toEqual({
      rejected: 'dailyBudget'
    })
    expect(
      'reservationId' in
        beginDeliveryAttemptOn(db, fence, gate({ cooldownMs: 0, dailyLimit: 2 }), T0)
    ).toBe(true)
  })
})

describe('delivery lifecycle', () => {
  it('stamps per-state timestamps and keeps terminal rows immutable', () => {
    seedBucket('b')
    const fence = seedVisit(1, 'b')
    const r = beginDeliveryAttemptOn(db, fence, gate(), T0) as { reservationId: string }

    expect(
      advanceDeliveryOn(db, {
        id: r.reservationId,
        state: 'model_completed',
        decisionType: 'insight',
        at: T0 + 1
      })
    ).toBe(true)
    expect(
      advanceDeliveryOn(db, { id: r.reservationId, state: 'policy_approved', at: T0 + 2 })
    ).toBe(true)
    expect(
      advanceDeliveryOn(db, {
        id: r.reservationId,
        state: 'delivered',
        message: 'hello',
        at: T0 + 3
      })
    ).toBe(true)
    const row = db
      .prepare(
        `SELECT lifecycleState, modelCompletedAt, policyApprovedAt, deliveredAt, message FROM proactive_deliveries WHERE id = ?`
      )
      .get(r.reservationId) as Record<string, unknown>
    expect(row).toEqual({
      lifecycleState: 'delivered',
      modelCompletedAt: T0 + 1,
      policyApprovedAt: T0 + 2,
      deliveredAt: T0 + 3,
      message: 'hello'
    })

    // Terminal: a late suppression cannot revive or rewrite it.
    expect(advanceDeliveryOn(db, { id: r.reservationId, state: 'suppressed', at: T0 + 4 })).toBe(
      false
    )
  })

  it('reconciles abandoned rows to silence/failed after the timeout', () => {
    seedBucket('b')
    const fence = seedVisit(1, 'b')
    const r = beginDeliveryAttemptOn(db, fence, gate(), T0) as { reservationId: string }
    expect(reconcileAbandonedDeliveriesOn(db, T0 + 14 * 60 * 1000)).toBe(0)
    expect(reconcileAbandonedDeliveriesOn(db, T0 + 16 * 60 * 1000)).toBe(1)
    const row = db
      .prepare(
        `SELECT decisionType, lifecycleState, provenanceJson FROM proactive_deliveries WHERE id = ?`
      )
      .get(r.reservationId) as Record<string, unknown>
    expect(row).toEqual({
      decisionType: 'silence',
      lifecycleState: 'failed',
      provenanceJson: '{"failure":"abandoned"}'
    })
  })

  it('recent-delivered reads respect the 6h lookback and the assigned-tag sibling scope', () => {
    seedBucket('own')
    seedBucket('sib')
    seedBucket('other')
    assignWorkstreamTagOn(db, 'sib', 'omi-port', T0)
    assignWorkstreamTagOn(db, 'other', 'different', T0)
    const insert = db.prepare(
      `INSERT INTO proactive_deliveries (id, bucketID, decisionType, lifecycleState, provenanceJson, attemptedAt, deliveredAt, expiresAt, createdAt)
       VALUES (?, ?, 'insight', 'delivered', '{}', ?, ?, ?, ?)`
    )
    insert.run('recent-own', 'own', T0 - HOUR, T0 - HOUR, T0 + 720 * HOUR, T0 - HOUR)
    insert.run('old-own', 'own', T0 - 7 * HOUR, T0 - 7 * HOUR, T0 + 720 * HOUR, T0 - 7 * HOUR)
    insert.run('recent-sib', 'sib', T0 - 2 * HOUR, T0 - 2 * HOUR, T0 + 720 * HOUR, T0 - 2 * HOUR)
    insert.run(
      'recent-other',
      'other',
      T0 - 2 * HOUR,
      T0 - 2 * HOUR,
      T0 + 720 * HOUR,
      T0 - 2 * HOUR
    )

    expect(recentDeliveredForBucketOn(db, 'own', T0).map((r) => r.deliveredAt)).toEqual([T0 - HOUR])
    expect(recentDeliveredForAssignedTagsOn(db, 'own', ['omi-port'], T0).length).toBe(1)
    expect(recentDeliveredForAssignedTagsOn(db, 'own', [], T0)).toEqual([])
  })

  it('provenance reads only until row expiry', () => {
    seedBucket('b')
    const fence = seedVisit(1, 'b')
    const r = beginDeliveryAttemptOn(db, fence, gate(), T0) as { reservationId: string }
    expect(deliveryProvenanceOn(db, r.reservationId, T0 + 1)).toBe('{}')
    expect(deliveryProvenanceOn(db, r.reservationId, T0 + 31 * 24 * HOUR)).toBeNull()
  })
})

describe('armed candidates', () => {
  it('inserts with clamps and refuses unknown buckets', () => {
    seedBucket('b')
    expect(
      insertCandidateOn(
        db,
        {
          bucketID: 'missing',
          workstreamTag: null,
          message: 'm',
          groundingFactIDs: [],
          triggerNote: 't'
        },
        T0
      )
    ).toBeNull()
    const id = insertCandidateOn(
      db,
      {
        bucketID: 'b',
        workstreamTag: 'tag',
        message: 'x'.repeat(700),
        groundingFactIDs: ['f1'],
        triggerNote: 'y'.repeat(400)
      },
      T0
    )
    const row = db
      .prepare(
        `SELECT LENGTH(message) AS m, LENGTH(triggerNote) AS t, expiresAt FROM proactive_candidates WHERE id = ?`
      )
      .get(id) as { m: number; t: number; expiresAt: number }
    expect(row.m).toBe(600)
    expect(row.t).toBe(300)
    expect(row.expiresAt).toBe(T0 + 12 * HOUR)
  })

  it('lookupArmed orders own bucket first, then shared-tag siblings, newest first', () => {
    seedBucket('own')
    seedBucket('sib')
    assignWorkstreamTagOn(db, 'sib', 'shared', T0)
    expect(tagsForBucketOn(db, 'sib')).toEqual(['shared'])
    db.prepare(
      `INSERT INTO proactive_candidates (id, bucketID, workstreamTag, message, groundingFactIDsJson, triggerNote, state, createdAt, expiresAt)
       VALUES ('c-sib', 'sib', 'shared', 'sibling', '["fact:f1"]', 't', 'armed', ?, ?)`
    ).run(T0 + 5_000, T0 + HOUR)
    db.prepare(
      `INSERT INTO proactive_candidates (id, bucketID, workstreamTag, message, groundingFactIDsJson, triggerNote, state, createdAt, expiresAt)
       VALUES ('c-own', 'own', NULL, 'mine', '["f2"]', 't', 'armed', ?, ?)`
    ).run(T0, T0 + HOUR)

    const rows = lookupArmedOn(db, 'own', ['shared'], T0 + 10_000)
    expect(rows.map((r) => r.id)).toEqual(['c-own', 'c-sib'])
    // Grounding fact ids come back with fact: prefixes stripped.
    expect(rows[0].groundingFactIDs).toEqual(['f2'])
    expect(rows[1].groundingFactIDs).toEqual(['f1'])
    // Without tags, siblings are invisible.
    expect(lookupArmedOn(db, 'own', [], T0 + 10_000).map((r) => r.id)).toEqual(['c-own'])
  })

  it('consume/decline/restore carry the exact state semantics', () => {
    seedBucket('b')
    const id = insertCandidateOn(
      db,
      {
        bucketID: 'b',
        workstreamTag: null,
        message: 'm',
        groundingFactIDs: ['f'],
        triggerNote: 't'
      },
      T0
    ) as string

    expect(consumeCandidateOn(db, id, T0 + 1)).toBe(true)
    expect(consumeCandidateOn(db, id, T0 + 2)).toBe(false)
    expect(restoreCandidateOn(db, id, T0 + 3)).toBe(true)
    expect(consumeCandidateOn(db, id, T0 + 4)).toBe(true)

    // Restore refuses once expired.
    declineCandidateOn(db, id, T0 + 5)
    expect(restoreCandidateOn(db, id, T0 + 6)).toBe(false)
  })

  it('grounding validation demands every fact validated and unexpired; expiry sweep retires armed', () => {
    seedBucket('b')
    seedFact('f1', 'b')
    seedFact('f2', 'b', { validityState: 'needs_review' })
    expect(groundingFactIDsValidOn(db, ['f1'], 'b', T0)).toBe(true)
    expect(groundingFactIDsValidOn(db, ['f1', 'f2'], 'b', T0)).toBe(false)
    expect(groundingFactIDsValidOn(db, [], 'b', T0)).toBe(false)

    const id = insertCandidateOn(
      db,
      {
        bucketID: 'b',
        workstreamTag: null,
        message: 'm',
        groundingFactIDs: ['f1'],
        triggerNote: 't'
      },
      T0
    ) as string
    expect(hasArmedCandidateWithValidGroundingOn(db, 'b', T0)).toBe(true)
    db.prepare(`UPDATE proactive_candidates SET expiresAt = ? WHERE id = ?`).run(T0 - 1, id)
    expect(expireStaleCandidatesOn(db, T0)).toBe(1)
    expect(hasArmedCandidateWithValidGroundingOn(db, 'b', T0)).toBe(false)
  })
})

describe('workstream pools and reconciler queries', () => {
  it('tag counts split own-visit facts from bucket-wide facts', () => {
    seedBucket('b')
    seedVisit(1, 'b')
    seedVisit(2, 'b')
    db.prepare(
      `INSERT INTO bucket_entries (id, bucketID, visitID, appName, rawContextKey, normalizedContextKey, narrative, evidenceRefsJson, tokenCount, createdAt)
       VALUES ('e-own', 'b', 1, 'Code', 'r', 'n', 'n', '[]', 1, ?)`
    ).run(T0)
    db.prepare(
      `INSERT INTO bucket_entries (id, bucketID, visitID, appName, rawContextKey, normalizedContextKey, narrative, evidenceRefsJson, tokenCount, createdAt)
       VALUES ('e-other', 'b', 2, 'Code', 'r', 'n', 'n', '[]', 1, ?)`
    ).run(T0)
    seedFact('f-own', 'b', { entryID: 'e-own', workstreamTag: 'alpha' })
    seedFact('f-other', 'b', { entryID: 'e-other', workstreamTag: 'beta' })

    const counts = workstreamTagCountsOn(db, 'b', 1, T0)
    expect([...counts.own.entries()]).toEqual([['alpha', 1]])
    expect(new Map(counts.bucket)).toEqual(
      new Map([
        ['alpha', 1],
        ['beta', 1]
      ])
    )
  })

  it('pool queries respect floors, windows, and bucket exclusion', () => {
    seedBucket('own')
    seedBucket('other')
    seedFact('p1', 'other', {
      workstreamTag: 'shared',
      notifyWorthiness: 0.5,
      createdAt: T0 - 1_000
    })
    seedFact('p2', 'other', {
      workstreamTag: 'shared',
      notifyWorthiness: 0.2,
      createdAt: T0 - 2_000
    })
    seedFact('p3', 'own', { workstreamTag: 'shared', notifyWorthiness: 0.9, createdAt: T0 - 500 })
    expect(workstreamPoolOn(db, 'shared', 'own', T0, 0.3).map((r) => r.factID)).toEqual(['p1'])

    seedFact('r1', 'other', { notifyWorthiness: 0.7, createdAt: T0 - 10 * 60 * 1000 })
    seedFact('r2', 'other', { notifyWorthiness: 0.7, createdAt: T0 - 20 * 60 * 1000 })
    expect(recentContextPoolOn(db, 'own', T0, 0.6).map((r) => r.factID)).toEqual(['r1'])
  })

  it('eligibility orders untagged-first and top facts cap at 20', () => {
    seedBucket('tagged')
    seedBucket('untagged')
    assignWorkstreamTagOn(db, 'tagged', 'x', T0)
    for (let i = 0; i < 3; i++) seedFact(`t${i}`, 'tagged', { createdAt: T0 + i })
    for (let i = 0; i < 4; i++) seedFact(`u${i}`, 'untagged', { createdAt: T0 + i })
    seedBucket('thin')
    seedFact('thin1', 'thin')

    const eligible = fetchEligibleBucketsOn(db, T0 + 100)
    expect(eligible.map((r) => r.bucketID)).toEqual(['untagged', 'tagged'])
    expect(eligible[0].tagged).toBe(false)

    for (let i = 0; i < 25; i++) seedFact(`many${i}`, 'untagged', { createdAt: T0 + 100 + i })
    expect(topFactsForBucketOn(db, 'untagged', T0 + 200).length).toBe(20)
  })

  it('maxValidatedFactUpdatedAt reads only validated facts', () => {
    expect(maxValidatedFactUpdatedAtOn(db)).toBeNull()
    seedBucket('b')
    seedFact('f1', 'b', { updatedAt: T0 + 5 })
    seedFact('f2', 'b', { validityState: 'needs_review', updatedAt: T0 + 50 })
    expect(maxValidatedFactUpdatedAtOn(db)).toBe(T0 + 5)
  })
})
