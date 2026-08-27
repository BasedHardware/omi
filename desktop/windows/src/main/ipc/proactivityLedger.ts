/**
 * Proactivity ledger — delivery reservation/lifecycle, armed candidates, and
 * workstream assignments. Windows port of the persistence half of macOS
 * ContextDeliveryAuthority + the candidate/workstream store surface of
 * ContextBucketStore/ContextWorkstreamReconciler.
 *
 * Invariants carried from mac:
 * - One reservation per (visitID, bucketVersionID); a new fact republishes the
 *   version and re-enables the same visit.
 * - Terminal rows (delivered/suppressed/failed) are immutable; every advance
 *   is guarded by the advanceable-state set.
 * - Suppressed and failed rows never count against the trailing-24h budget;
 *   in-flight attempts count until they resolve.
 */

import { randomUUID } from 'node:crypto'
import type { ContextBucketDb, ContextVisitFence } from './contextBucketStore'
import { prefixChars } from './contextBucketStore'
import {
  ADVANCEABLE_DELIVERY_STATES,
  DAILY_WINDOW_MS,
  DELIVERY_ROW_EXPIRY_MS,
  ABANDONED_DELIVERY_TIMEOUT_MS,
  RECENT_DELIVERY_PROMPT_CAP,
  RECENT_DELIVERY_MEMORY_LOOKBACK_MS,
  type DeliveryGateInput,
  type DeliveryGateReason,
  freeGate
} from '../assistants/director/deliveryPolicy'

export type DeliveryLifecycleState =
  | 'attempted'
  | 'model_completed'
  | 'policy_approved'
  | 'delivered'
  | 'suppressed'
  | 'failed'

const ADVANCEABLE_SQL = ADVANCEABLE_DELIVERY_STATES.map((s) => `'${s}'`).join(', ')

function inTxn<T>(db: ContextBucketDb, fn: () => T): T {
  db.exec('BEGIN IMMEDIATE')
  try {
    const result = fn()
    db.exec('COMMIT')
    return result
  } catch (err) {
    try {
      db.exec('ROLLBACK')
    } catch {
      // best-effort rollback
    }
    throw err
  }
}

export type ReservationResult =
  | { reservationId: string }
  | { rejected: DeliveryGateReason | 'staleFence' }

/** Reserve a delivery attempt (mac beginDeliveryAttempt, CDA:215-280). */
export function beginDeliveryAttemptOn(
  db: ContextBucketDb,
  fence: ContextVisitFence,
  gate: DeliveryGateInput,
  now: number
): ReservationResult {
  return inTxn(db, () => {
    const gateReason = freeGate(gate)
    if (gateReason !== 'allowed') return { rejected: gateReason }

    const visitExists = db
      .prepare(
        `SELECT 1 AS ok FROM context_visits WHERE id = ? AND contextGeneration = ? AND poolEpoch = ?`
      )
      .get(fence.visitID, fence.contextGeneration, fence.poolEpoch)
    if (!visitExists) return { rejected: 'staleFence' }

    const latestVersion = db
      .prepare(`SELECT MAX(id) AS id FROM bucket_versions WHERE bucketID = ?`)
      .get(fence.bucketID) as { id: number | null }
    const versionId = latestVersion.id

    const duplicate = db
      .prepare(
        `SELECT 1 AS ok FROM proactive_deliveries WHERE visitID = ? AND bucketVersionID IS ?`
      )
      .get(fence.visitID, versionId)
    if (duplicate) return { rejected: 'duplicate' }

    if (gate.cooldownMs > 0) {
      const anchors = db
        .prepare(
          `SELECT
             (SELECT MAX(deliveredAt) FROM proactive_deliveries) AS lastDelivered,
             (SELECT MAX(attemptedAt) FROM proactive_deliveries WHERE lifecycleState IN (${ADVANCEABLE_SQL})) AS lastInFlight`
        )
        .get() as { lastDelivered: number | null; lastInFlight: number | null }
      const anchor = Math.max(
        anchors.lastDelivered ?? 0,
        gate.lastGlobalPresentationAt ?? 0,
        anchors.lastInFlight ?? 0
      )
      if (anchor > 0 && now - anchor < gate.cooldownMs) return { rejected: 'cooldown' }
    }

    const spent = db
      .prepare(
        `SELECT COUNT(*) AS n FROM proactive_deliveries
         WHERE attemptedAt >= ? AND lifecycleState NOT IN ('suppressed', 'failed')`
      )
      .get(now - DAILY_WINDOW_MS) as { n: number }
    if (Number(spent.n) >= gate.dailyLimit) return { rejected: 'dailyBudget' }

    const reservationId = randomUUID().toLowerCase()
    db.prepare(
      `INSERT INTO proactive_deliveries
         (id, visitID, bucketID, bucketVersionID, decisionType, lifecycleState, provenanceJson,
          message, attemptedAt, expiresAt, createdAt)
       VALUES (?, ?, ?, ?, 'pending', 'attempted', '{}', NULL, ?, ?, ?)`
    ).run(
      reservationId,
      fence.visitID,
      fence.bucketID,
      versionId,
      now,
      now + DELIVERY_ROW_EXPIRY_MS,
      now
    )
    return { reservationId }
  })
}

export interface DeliveryAdvance {
  id: string
  state: DeliveryLifecycleState
  decisionType?: string
  provenanceJson?: string
  message?: string | null
  at: number
}

/** Advance a delivery row; terminal rows are immutable. Returns whether the
 *  row changed. Timestamps stamp per target state (mac completeDelivery). */
export function advanceDeliveryOn(db: ContextBucketDb, advance: DeliveryAdvance): boolean {
  const stampColumn =
    advance.state === 'model_completed'
      ? 'modelCompletedAt'
      : advance.state === 'policy_approved'
        ? 'policyApprovedAt'
        : advance.state === 'delivered'
          ? 'deliveredAt'
          : null

  const sets: string[] = ['lifecycleState = ?']
  const params: unknown[] = [advance.state]
  if (advance.decisionType !== undefined) {
    sets.push('decisionType = ?')
    params.push(advance.decisionType)
  }
  if (advance.provenanceJson !== undefined) {
    sets.push('provenanceJson = ?')
    params.push(advance.provenanceJson)
  }
  if (advance.message !== undefined) {
    sets.push('message = ?')
    params.push(advance.message)
  }
  if (stampColumn) {
    sets.push(`${stampColumn} = ?`)
    params.push(advance.at)
  }
  params.push(advance.id)

  const info = db
    .prepare(
      `UPDATE proactive_deliveries SET ${sets.join(', ')}
       WHERE id = ? AND lifecycleState IN (${ADVANCEABLE_SQL})`
    )
    .run(...params) as { changes: number | bigint }
  return Number(info.changes) === 1
}

/** Rows stuck in advanceable states past the timeout become silence/failed. */
export function reconcileAbandonedDeliveriesOn(
  db: ContextBucketDb,
  now: number,
  timeoutMs = ABANDONED_DELIVERY_TIMEOUT_MS
): number {
  const info = db
    .prepare(
      `UPDATE proactive_deliveries
       SET decisionType = 'silence', lifecycleState = 'failed',
           provenanceJson = '{"failure":"abandoned"}', message = NULL
       WHERE lifecycleState IN (${ADVANCEABLE_SQL}) AND attemptedAt <= ?`
    )
    .run(now - timeoutMs) as { changes: number | bigint }
  return Number(info.changes)
}

export interface RecentDelivery {
  decisionType: string
  deliveredAt: number
  message: string | null
}

export function recentDeliveredForBucketOn(
  db: ContextBucketDb,
  bucketID: string,
  now: number
): RecentDelivery[] {
  return db
    .prepare(
      `SELECT decisionType, deliveredAt, message FROM proactive_deliveries
       WHERE bucketID = ? AND lifecycleState = 'delivered' AND deliveredAt >= ?
       ORDER BY deliveredAt DESC LIMIT ?`
    )
    .all(
      bucketID,
      now - RECENT_DELIVERY_MEMORY_LOOKBACK_MS,
      RECENT_DELIVERY_PROMPT_CAP
    ) as RecentDelivery[]
}

/** Sibling-bucket delivered rows via durable workstream assignments (6h). */
export function recentDeliveredForAssignedTagsOn(
  db: ContextBucketDb,
  bucketID: string,
  tags: readonly string[],
  now: number
): RecentDelivery[] {
  if (tags.length === 0) return []
  const marks = tags.map(() => '?').join(', ')
  return db
    .prepare(
      `SELECT d.decisionType, d.deliveredAt, d.message FROM proactive_deliveries d
       WHERE d.lifecycleState = 'delivered' AND d.deliveredAt >= ?
         AND d.bucketID <> ?
         AND d.bucketID IN (SELECT bucketID FROM bucket_workstreams WHERE tag IN (${marks}))
       ORDER BY d.deliveredAt DESC LIMIT ?`
    )
    .all(
      now - RECENT_DELIVERY_MEMORY_LOOKBACK_MS,
      bucketID,
      ...tags,
      RECENT_DELIVERY_PROMPT_CAP
    ) as RecentDelivery[]
}

export function deliveryProvenanceOn(db: ContextBucketDb, id: string, now: number): string | null {
  const row = db
    .prepare(`SELECT provenanceJson FROM proactive_deliveries WHERE id = ? AND expiresAt > ?`)
    .get(id, now) as { provenanceJson: string } | undefined
  return row?.provenanceJson ?? null
}

// --- armed candidates ------------------------------------------------------

export const CANDIDATE_LIFETIME_MS = 12 * 60 * 60 * 1000
export const CANDIDATE_MESSAGE_CAP = 600
export const CANDIDATE_TRIGGER_NOTE_CAP = 300

export interface ArmedCandidate {
  id: string
  bucketID: string
  workstreamTag: string | null
  message: string
  groundingFactIDs: string[]
  triggerNote: string
  createdAt: number
  expiresAt: number
}

export function insertCandidateOn(
  db: ContextBucketDb,
  candidate: {
    bucketID: string
    workstreamTag: string | null
    message: string
    groundingFactIDs: string[]
    triggerNote: string
  },
  now: number
): string | null {
  const bucketExists = db
    .prepare(`SELECT 1 AS ok FROM context_buckets WHERE id = ?`)
    .get(candidate.bucketID)
  if (!bucketExists) return null
  const id = randomUUID().toLowerCase()
  db.prepare(
    `INSERT INTO proactive_candidates
       (id, bucketID, workstreamTag, message, groundingFactIDsJson, triggerNote, state, createdAt, expiresAt, consumedAt)
     VALUES (?, ?, ?, ?, ?, ?, 'armed', ?, ?, NULL)`
  ).run(
    id,
    candidate.bucketID,
    candidate.workstreamTag,
    prefixChars(candidate.message, CANDIDATE_MESSAGE_CAP),
    JSON.stringify(candidate.groundingFactIDs),
    prefixChars(candidate.triggerNote, CANDIDATE_TRIGGER_NOTE_CAP),
    now,
    now + CANDIDATE_LIFETIME_MS
  )
  return id
}

function parseGroundingFactIDs(json: string): string[] {
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter((v): v is string => typeof v === 'string')
      .map((v) => (v.startsWith('fact:') ? v.slice('fact:'.length) : v))
      .filter((v) => v.length > 0)
  } catch {
    return []
  }
}

/** Armed unexpired candidates: own bucket first, then shared-tag siblings. */
export function lookupArmedOn(
  db: ContextBucketDb,
  bucketID: string,
  tags: readonly string[],
  now: number
): ArmedCandidate[] {
  const marks = tags.map(() => '?').join(', ')
  const tagClause = tags.length > 0 ? `OR (workstreamTag IN (${marks}) AND bucketID <> ?)` : ''
  const params: unknown[] = [
    now,
    bucketID,
    ...(tags.length > 0 ? [...tags, bucketID] : []),
    bucketID
  ]
  const rows = db
    .prepare(
      `SELECT id, bucketID, workstreamTag, message, groundingFactIDsJson, triggerNote, createdAt, expiresAt
       FROM proactive_candidates
       WHERE state = 'armed' AND expiresAt > ? AND (bucketID = ? ${tagClause})
       ORDER BY CASE WHEN bucketID = ? THEN 0 ELSE 1 END, createdAt DESC`
    )
    .all(...params) as Array<{
    id: string
    bucketID: string
    workstreamTag: string | null
    message: string
    groundingFactIDsJson: string
    triggerNote: string
    createdAt: number
    expiresAt: number
  }>
  return rows.map((r) => ({
    id: r.id,
    bucketID: r.bucketID,
    workstreamTag: r.workstreamTag,
    message: r.message,
    groundingFactIDs: parseGroundingFactIDs(r.groundingFactIDsJson),
    triggerNote: r.triggerNote,
    createdAt: Number(r.createdAt),
    expiresAt: Number(r.expiresAt)
  }))
}

export function consumeCandidateOn(db: ContextBucketDb, id: string, now: number): boolean {
  const info = db
    .prepare(
      `UPDATE proactive_candidates SET state = 'consumed', consumedAt = ?
       WHERE id = ? AND state = 'armed' AND expiresAt > ?`
    )
    .run(now, id, now) as { changes: number | bigint }
  return Number(info.changes) === 1
}

/** Retire immediately by collapsing expiry (declined candidates must not
 *  re-bill the gate). */
export function declineCandidateOn(db: ContextBucketDb, id: string, now: number): void {
  db.prepare(`UPDATE proactive_candidates SET expiresAt = ? WHERE id = ?`).run(now, id)
}

/** Claimed-but-never-shown path: consumed -> armed while unexpired. */
export function restoreCandidateOn(db: ContextBucketDb, id: string, now: number): boolean {
  const info = db
    .prepare(
      `UPDATE proactive_candidates SET state = 'armed', consumedAt = NULL
       WHERE id = ? AND state = 'consumed' AND expiresAt > ?`
    )
    .run(id, now) as { changes: number | bigint }
  return Number(info.changes) === 1
}

/** Every grounding fact must still be validated and unexpired in that bucket
 *  (set semantics, no partial credit). */
export function groundingFactIDsValidOn(
  db: ContextBucketDb,
  factIDs: readonly string[],
  bucketID: string,
  now: number
): boolean {
  if (factIDs.length === 0) return false
  const stmt = db.prepare(
    `SELECT 1 AS ok FROM bucket_facts
     WHERE id = ? AND bucketID = ? AND validityState = 'validated' AND (expiresAt IS NULL OR expiresAt > ?)`
  )
  for (const id of factIDs) {
    if (!stmt.get(id, bucketID, now)) return false
  }
  return true
}

export function expireStaleCandidatesOn(db: ContextBucketDb, now: number): number {
  const info = db
    .prepare(
      `UPDATE proactive_candidates SET state = 'expired' WHERE state = 'armed' AND expiresAt <= ?`
    )
    .run(now) as { changes: number | bigint }
  return Number(info.changes)
}

/** An armed candidate whose grounding facts are all still valid blocks a new
 *  candidate for the bucket (reconciler needsCandidate check). */
export function hasArmedCandidateWithValidGroundingOn(
  db: ContextBucketDb,
  bucketID: string,
  now: number
): boolean {
  const rows = db
    .prepare(
      `SELECT groundingFactIDsJson FROM proactive_candidates
       WHERE bucketID = ? AND state = 'armed' AND expiresAt > ?`
    )
    .all(bucketID, now) as { groundingFactIDsJson: string }[]
  for (const row of rows) {
    const ids = parseGroundingFactIDs(row.groundingFactIDsJson)
    if (ids.length > 0 && groundingFactIDsValidOn(db, ids, bucketID, now)) return true
  }
  return false
}

// --- workstream assignments -------------------------------------------------

export function assignWorkstreamTagOn(
  db: ContextBucketDb,
  bucketID: string,
  tag: string,
  now: number
): boolean {
  const bucketExists = db.prepare(`SELECT 1 AS ok FROM context_buckets WHERE id = ?`).get(bucketID)
  if (!bucketExists) return false
  const info = db
    .prepare(
      `INSERT OR IGNORE INTO bucket_workstreams (id, bucketID, tag, source, assignedAt)
       VALUES (?, ?, ?, 'reconciler', ?)`
    )
    .run(randomUUID().toLowerCase(), bucketID, tag, now) as { changes: number | bigint }
  return Number(info.changes) === 1
}

export function tagsForBucketOn(db: ContextBucketDb, bucketID: string): string[] {
  const rows = db
    .prepare(`SELECT tag FROM bucket_workstreams WHERE bucketID = ? ORDER BY assignedAt ASC`)
    .all(bucketID) as { tag: string }[]
  return rows.map((r) => r.tag)
}

export function allWorkstreamTagsOn(db: ContextBucketDb): string[] {
  const rows = db.prepare(`SELECT DISTINCT tag FROM bucket_workstreams ORDER BY tag ASC`).all() as {
    tag: string
  }[]
  return rows.map((r) => r.tag)
}

// --- pooled fact queries ----------------------------------------------------

export interface PooledFactRow {
  factID: string
  bucketID: string
  appName: string
  statement: string
  notifyWorthiness: number
  createdAt: number
}

export const POOL_CANDIDATE_FETCH_LIMIT = 200
export const RECENT_CONTEXT_WINDOW_MS = 15 * 60 * 1000

/** Validated tagged facts of THIS visit vs the whole bucket, as tag->count
 *  maps for the live-tag rule (mac liveWorkstreamTag, CBS:439-471). */
export function workstreamTagCountsOn(
  db: ContextBucketDb,
  bucketID: string,
  visitID: number,
  now: number
): { own: Map<string, number>; bucket: Map<string, number> } {
  const ownRows = db
    .prepare(
      `SELECT f.workstreamTag AS tag, COUNT(*) AS n FROM bucket_facts f
       JOIN bucket_entries e ON e.id = f.entryID
       WHERE f.bucketID = ? AND e.visitID = ? AND f.validityState = 'validated'
         AND (f.expiresAt IS NULL OR f.expiresAt > ?) AND f.workstreamTag IS NOT NULL
       GROUP BY f.workstreamTag`
    )
    .all(bucketID, visitID, now) as { tag: string; n: number }[]
  const bucketRows = db
    .prepare(
      `SELECT workstreamTag AS tag, COUNT(*) AS n FROM bucket_facts
       WHERE bucketID = ? AND validityState = 'validated'
         AND (expiresAt IS NULL OR expiresAt > ?) AND workstreamTag IS NOT NULL
       GROUP BY workstreamTag`
    )
    .all(bucketID, now) as { tag: string; n: number }[]
  return {
    own: new Map(ownRows.map((r) => [r.tag, Number(r.n)])),
    bucket: new Map(bucketRows.map((r) => [r.tag, Number(r.n)]))
  }
}

export function workstreamPoolOn(
  db: ContextBucketDb,
  tag: string,
  excludeBucketID: string,
  now: number,
  worthinessFloor: number
): PooledFactRow[] {
  return db
    .prepare(
      `SELECT id AS factID, bucketID, appName, statement, notifyWorthiness, createdAt
       FROM bucket_facts
       WHERE workstreamTag = ? AND bucketID <> ? AND validityState = 'validated'
         AND (expiresAt IS NULL OR expiresAt > ?) AND notifyWorthiness >= ?
       ORDER BY createdAt DESC LIMIT ?`
    )
    .all(tag, excludeBucketID, now, worthinessFloor, POOL_CANDIDATE_FETCH_LIMIT) as PooledFactRow[]
}

export function recentContextPoolOn(
  db: ContextBucketDb,
  excludeBucketID: string,
  now: number,
  worthinessFloor: number
): PooledFactRow[] {
  return db
    .prepare(
      `SELECT id AS factID, bucketID, appName, statement, notifyWorthiness, createdAt
       FROM bucket_facts
       WHERE bucketID <> ? AND validityState = 'validated'
         AND (expiresAt IS NULL OR expiresAt > ?) AND notifyWorthiness >= ? AND createdAt >= ?
       ORDER BY createdAt DESC LIMIT ?`
    )
    .all(
      excludeBucketID,
      now,
      worthinessFloor,
      now - RECENT_CONTEXT_WINDOW_MS,
      POOL_CANDIDATE_FETCH_LIMIT
    ) as PooledFactRow[]
}

// --- reconciler batch queries ----------------------------------------------

export interface EligibleBucketRow {
  bucketID: string
  factCount: number
  newestFactAt: number
  tagged: boolean
}

export const RECONCILER_MINIMUM_FACTS = 3
export const RECONCILER_FACT_FETCH_CAP = 20

export function maxValidatedFactUpdatedAtOn(db: ContextBucketDb): number | null {
  const row = db
    .prepare(`SELECT MAX(updatedAt) AS m FROM bucket_facts WHERE validityState = 'validated'`)
    .get() as { m: number | null }
  return row.m === null ? null : Number(row.m)
}

export function fetchEligibleBucketsOn(db: ContextBucketDb, now: number): EligibleBucketRow[] {
  const rows = db
    .prepare(
      `SELECT f.bucketID AS bucketID, COUNT(*) AS factCount, MAX(f.createdAt) AS newestFactAt,
              EXISTS(SELECT 1 FROM bucket_workstreams w WHERE w.bucketID = f.bucketID) AS tagged
       FROM bucket_facts f
       WHERE f.validityState = 'validated' AND (f.expiresAt IS NULL OR f.expiresAt > ?)
       GROUP BY f.bucketID
       HAVING COUNT(*) >= ?
       ORDER BY tagged ASC, factCount DESC, newestFactAt DESC, f.bucketID ASC`
    )
    .all(now, RECONCILER_MINIMUM_FACTS) as Array<{
    bucketID: string
    factCount: number
    newestFactAt: number
    tagged: number
  }>
  return rows.map((r) => ({
    bucketID: r.bucketID,
    factCount: Number(r.factCount),
    newestFactAt: Number(r.newestFactAt),
    tagged: Number(r.tagged) === 1
  }))
}

export interface ReconcilerFactRow {
  factID: string
  statement: string
  notifyWorthiness: number
  createdAt: number
}

/** Top facts per bucket by (worthiness, recency), SQL-capped at 20 before the
 *  pure scaffolding filter takes the final 5. */
export function topFactsForBucketOn(
  db: ContextBucketDb,
  bucketID: string,
  now: number
): ReconcilerFactRow[] {
  return db
    .prepare(
      `SELECT id AS factID, statement, notifyWorthiness, createdAt FROM bucket_facts
       WHERE bucketID = ? AND validityState = 'validated' AND (expiresAt IS NULL OR expiresAt > ?)
       ORDER BY notifyWorthiness DESC, createdAt DESC LIMIT ?`
    )
    .all(bucketID, now, RECONCILER_FACT_FETCH_CAP) as ReconcilerFactRow[]
}
