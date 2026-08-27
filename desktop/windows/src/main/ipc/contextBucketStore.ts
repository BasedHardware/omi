/**
 * Context-bucket store — visits, buckets, entries/facts, versions, snapshots,
 * destination binding, subject bindings, and deterministic GC.
 * Windows port of macOS ContextBucketStore.swift + the destination binder from
 * ContextDestinationKey.swift; rule-for-rule per the ground-truth extraction.
 *
 * Driver-agnostic (insightStore/taskStore pattern): every function is
 * `*On(db, …)` over a structural handle; db.ts execs CONTEXT_BUCKET_SCHEMA and
 * binds thin wrappers. Fence discipline: every write revalidates
 * (id, contextGeneration, poolEpoch, outcome) and reports staleness by
 * returning null/false instead of throwing — callers drop in-memory state.
 */

import { createHash, randomUUID } from 'node:crypto'
import { identityKey, normalizeTitleForIdentity } from '../assistants/director/titleNormalizer'
import {
  type WorkHandle,
  handleIdentityKey,
  isDurable,
  primaryHandle
} from '../assistants/director/workHandles'
import {
  DESTINATION_DERIVATION_SOURCE,
  DESTINATION_SUBJECT_PREFIX
} from '../assistants/director/destinationKey'

export interface ContextBucketDb {
  exec(sql: string): unknown
  prepare(sql: string): {
    run: (...params: unknown[]) => unknown
    all: (...params: unknown[]) => unknown[]
    get: (...params: unknown[]) => unknown
  }
}

export interface ContextVisitFence {
  visitID: number
  contextGeneration: number
  poolEpoch: number
  bucketID: string | null
  startedAt: number
}

export type VisitOutcome = 'active' | 'completed' | 'interrupted' | 'discarded'

export interface BucketSnapshot {
  bucketID: string
  versionID: number | null
  frozenRankedSegment: string
  tail: string[]
  validatedFacts: string[]
  notifyWorthiness: number
  visitCount: number
}

// --- constants (mac names and values; see the ground-truth doc for sources) ---

export const SECOND_VISIT_GATE_WINDOW_MS = 7 * 24 * 60 * 60 * 1000
export const DELIVERY_VALIDITY_WINDOW_MS = 60 * 1000
export const STALE_BUCKET_AGE_MS = 30 * 24 * 60 * 60 * 1000
export const BUCKET_OVERFLOW_KEEP = 250
export const SNAPSHOT_TAIL_CAP = 5
export const SNAPSHOT_FACTS_CAP = 20
export const RETAINED_TAIL_COUNT = 5
export const FROZEN_RANKED_BYTE_BUDGET = 16_000
export const STABLE_HEADER = 'Persistent work context.'
export const NARRATIVE_CAP = 2_400
export const FACTS_PER_EXTRACTION = 20
export const STATEMENT_CAP = 500
export const EVIDENCE_TEXT_CAP = 1_000
export const EVIDENCE_REFS_PER_FACT = 10
export const EVIDENCE_REFS_PER_ENTRY = 40
export const EVIDENCE_REF_LENGTH_CAP = 200
export const IDENTIFIERS_PER_FACT = 8
export const IDENTIFIER_LENGTH_CAP = 200
export const BINDING_UNBOUND_RETENTION_MS = 30 * 24 * 60 * 60 * 1000
export const BINDING_UNBOUND_KEEP = 256
export const BINDING_RESOLVE_WINDOW_MS = 30 * 24 * 60 * 60 * 1000

/** Statement prefixes that mark model scaffolding rather than real facts
 *  (mac: ContextWorkstreamPooling.scaffoldingPrefixes). */
export const SCAFFOLDING_PREFIXES = [
  'identifier',
  'ambient narrative',
  'evidence fragment',
  'evidence record',
  'proposed record',
  'proposed fact',
  'proposal ',
  'proposal:'
]

const BOOKKEEPING_IDENTIFIER_RE = /^(fact|f|ftn|visit|screenshot)[-:_ ]?\d+$/i

export function isScaffoldingStatement(statement: string): boolean {
  const lowered = statement.trim().toLowerCase()
  return SCAFFOLDING_PREFIXES.some((p) => lowered.startsWith(p))
}

export function referenceHashFor(key: string): string {
  return 'sha256:' + createHash('sha256').update(key, 'utf8').digest('hex')
}

export function ephemeralHash(): string {
  return 'ephemeral:' + randomUUID().toLowerCase()
}

export function estimatedTokens(text: string): number {
  return Math.max(1, Math.ceil(Buffer.byteLength(text, 'utf8') / 4))
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.min(1, Math.max(0, value))
}

/** Code-point prefix (mac String.prefix analog). */
export function prefixChars(value: string, cap: number): string {
  const points = [...value]
  return points.length > cap ? points.slice(0, cap).join('') : value
}

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
      // rollback best-effort; the original error is what matters
    }
    throw err
  }
}

function placeholders(count: number): string {
  return new Array(count).fill('?').join(', ')
}

// --- visit lifecycle -------------------------------------------------------

export interface StartVisitInput {
  contextGeneration: number
  poolEpoch: number
  appName: string
  windowTitle: string | null
  handles: WorkHandle[]
  processName: string | null
  startedAt: number
}

interface BindingRow {
  referenceHash: string
  bucketID: string | null
  subjectKind: string
  subjectID: string
  workstreamID: string | null
  confidence: number
  source: string
}

function resolveBucketId(
  db: ContextBucketDb,
  args: {
    referenceHash: string
    normalizedTitle: string | null
    handle: WorkHandle | null
    startedAt: number
  }
): string | null {
  const handleIdentity = args.handle && isDurable(args.handle) ? args.handle : null
  const lookupHash = handleIdentity ? handleIdentityKey(handleIdentity) : args.referenceHash

  const binding = db
    .prepare(
      `SELECT referenceHash, bucketID, subjectKind, subjectID, workstreamID, confidence, source
       FROM subject_bindings WHERE referenceHash = ?`
    )
    .get(lookupHash) as BindingRow | undefined

  const subjectKind = binding?.subjectKind ?? handleIdentity?.kind ?? 'context'
  const subjectID = binding?.subjectID ?? handleIdentity?.value ?? args.referenceHash
  const workstreamID = binding?.workstreamID ?? null

  if (binding?.bucketID) {
    const consistent = db
      .prepare(
        `SELECT id FROM context_buckets
         WHERE id = ? AND subjectKind = ? AND subjectID = ? AND workstreamID IS ?`
      )
      .get(binding.bucketID, subjectKind, subjectID, workstreamID) as { id: string } | undefined
    if (consistent) return binding.bucketID
    // Explicit rebinding moved the subject: fall through and re-resolve.
  }

  if (args.normalizedTitle === null && handleIdentity === null) return null

  if (!binding) {
    // Second-visit gate: a brand-new context earns a bucket only on its second
    // qualifying (completed) visit within 7 days.
    const cutoff = args.startedAt - SECOND_VISIT_GATE_WINDOW_MS
    const countRow = (
      handleIdentity
        ? db
            .prepare(
              `SELECT COUNT(*) AS n FROM context_visits
               WHERE primaryHandleType = ? AND primaryHandleValue = ?
                 AND outcome = 'completed' AND endedAt >= ?`
            )
            .get(handleIdentity.kind, handleIdentity.value, cutoff)
        : db
            .prepare(
              `SELECT COUNT(*) AS n FROM context_visits
               WHERE referenceHash = ? AND outcome = 'completed' AND endedAt >= ?`
            )
            .get(args.referenceHash, cutoff)
    ) as { n: number }
    if (Number(countRow.n) < 1) return null
  }

  const existing = db
    .prepare(
      `SELECT id FROM context_buckets WHERE subjectKind = ? AND subjectID = ? AND workstreamID IS ?`
    )
    .get(subjectKind, subjectID, workstreamID) as { id: string } | undefined

  let bucketID: string
  if (existing) {
    bucketID = existing.id
  } else {
    bucketID = randomUUID().toLowerCase()
    db.prepare(
      `INSERT INTO context_buckets
         (id, subjectKind, subjectID, workstreamID, displayLabel, notifyWorthiness,
          visitCount, lastVisitedAt, createdAt, updatedAt)
       VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?)`
    ).run(
      bucketID,
      subjectKind,
      subjectID,
      workstreamID,
      handleIdentity?.value ?? args.normalizedTitle,
      args.startedAt,
      args.startedAt,
      args.startedAt
    )
  }

  db.prepare(
    `INSERT INTO subject_bindings
       (referenceHash, bucketID, subjectKind, subjectID, workstreamID, confidence, source,
        occurrenceCount, createdAt, updatedAt)
     VALUES (?, ?, ?, ?, ?, ?, ?, 2, ?, ?)
     ON CONFLICT(referenceHash) DO UPDATE SET
       bucketID = excluded.bucketID,
       occurrenceCount = occurrenceCount + 1,
       updatedAt = excluded.updatedAt`
  ).run(
    lookupHash,
    bucketID,
    subjectKind,
    subjectID,
    workstreamID,
    binding?.confidence ?? (handleIdentity ? 0.8 : 0.5),
    binding?.source ?? (handleIdentity ? 'source_handle' : 'repeat_cooccurrence'),
    args.startedAt,
    args.startedAt
  )

  return bucketID
}

export function startVisitOn(db: ContextBucketDb, input: StartVisitInput): ContextVisitFence {
  return inTxn(db, () => {
    const normalizedTitle = normalizeTitleForIdentity(input.windowTitle, input.appName)
    const key = identityKey(input.appName, input.windowTitle)
    const referenceHash = key !== null ? referenceHashFor(key) : ephemeralHash()
    const primary = primaryHandle(input.handles)

    let bucketID: string | null = null
    if (key !== null || (primary !== null && isDurable(primary))) {
      bucketID = resolveBucketId(db, {
        referenceHash,
        normalizedTitle,
        handle: primary,
        startedAt: input.startedAt
      })
    }

    const info = db
      .prepare(
        `INSERT INTO context_visits
           (contextGeneration, poolEpoch, bucketID, appName, rawContextKey, normalizedContextKey,
            referenceHash, startedAt, outcome, createdAt, updatedAt,
            primaryHandleType, primaryHandleValue, handlesJson, processName)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)`
      )
      .run(
        input.contextGeneration,
        input.poolEpoch,
        bucketID,
        input.appName,
        `${input.appName}\n${input.windowTitle ?? ''}`,
        key ?? '',
        referenceHash,
        input.startedAt,
        input.startedAt,
        input.startedAt,
        primary?.kind ?? null,
        primary?.value ?? null,
        input.handles.length > 0 ? JSON.stringify(input.handles) : null,
        input.processName
      ) as { lastInsertRowid: number | bigint }

    return {
      visitID: Number(info.lastInsertRowid),
      contextGeneration: input.contextGeneration,
      poolEpoch: input.poolEpoch,
      bucketID,
      startedAt: input.startedAt
    }
  })
}

export function finalizeVisitOn(
  db: ContextBucketDb,
  fence: ContextVisitFence,
  opts: {
    outcome: 'completed' | 'discarded' | 'interrupted'
    exitReason: string
    endedAt: number
    lastFrameId: number | null
  }
): boolean {
  return inTxn(db, () => {
    const info = db
      .prepare(
        `UPDATE context_visits SET outcome = ?, exitReason = ?, endedAt = ?, lastFrameId = ?, updatedAt = ?
         WHERE id = ? AND contextGeneration = ? AND poolEpoch = ? AND outcome = 'active'`
      )
      .run(
        opts.outcome,
        opts.exitReason,
        opts.endedAt,
        opts.lastFrameId,
        opts.endedAt,
        fence.visitID,
        fence.contextGeneration,
        fence.poolEpoch
      ) as { changes: number | bigint }
    if (Number(info.changes) !== 1) return false

    if (opts.outcome === 'completed' && fence.bucketID !== null) {
      db.prepare(
        `UPDATE context_buckets SET visitCount = visitCount + 1, lastVisitedAt = ?, updatedAt = ? WHERE id = ?`
      ).run(opts.endedAt, opts.endedAt, fence.bucketID)
    }
    return true
  })
}

export function markVisitSettledOn(
  db: ContextBucketDb,
  fence: ContextVisitFence,
  at: number
): boolean {
  const info = db
    .prepare(
      `UPDATE context_visits SET settledAt = COALESCE(settledAt, ?), updatedAt = ?
       WHERE id = ? AND contextGeneration = ? AND poolEpoch = ? AND outcome = 'active'`
    )
    .run(at, at, fence.visitID, fence.contextGeneration, fence.poolEpoch) as {
    changes: number | bigint
  }
  return Number(info.changes) === 1
}

export function reconcileInterruptedVisitsOn(db: ContextBucketDb, now: number): number {
  const info = db
    .prepare(
      `UPDATE context_visits SET outcome = 'interrupted', exitReason = 'startup_reconcile', endedAt = ?, updatedAt = ?
       WHERE outcome = 'active'`
    )
    .run(now, now) as { changes: number | bigint }
  return Number(info.changes)
}

export interface VisitFreshness {
  fresh: boolean
  endedAt: number | null
}

/** Run-to-completion admission: active is fresh; completed is fresh for 60s
 *  after departure; discarded/interrupted/missing never are. */
export function visitFreshnessOn(
  db: ContextBucketDb,
  fence: ContextVisitFence,
  now: number
): VisitFreshness {
  const row = db
    .prepare(
      `SELECT outcome, endedAt FROM context_visits
       WHERE id = ? AND contextGeneration = ? AND poolEpoch = ?`
    )
    .get(fence.visitID, fence.contextGeneration, fence.poolEpoch) as
    | { outcome: VisitOutcome; endedAt: number | null }
    | undefined
  if (!row) return { fresh: false, endedAt: null }
  if (row.outcome === 'active') return { fresh: true, endedAt: null }
  if (row.outcome === 'completed') {
    const endedAt = row.endedAt ?? 0
    return { fresh: endedAt >= now - DELIVERY_VALIDITY_WINDOW_MS, endedAt: row.endedAt }
  }
  return { fresh: false, endedAt: row.endedAt }
}

// --- snapshot --------------------------------------------------------------

function frozenToString(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  return Buffer.from(value as Uint8Array).toString('utf8')
}

function snapshotOn(db: ContextBucketDb, bucketID: string, now: number): BucketSnapshot | null {
  const bucket = db.prepare(`SELECT visitCount FROM context_buckets WHERE id = ?`).get(bucketID) as
    | { visitCount: number }
    | undefined
  if (!bucket) return null

  const version = db
    .prepare(
      `SELECT id, frozenRankedSegment FROM bucket_versions WHERE bucketID = ? ORDER BY version DESC LIMIT 1`
    )
    .get(bucketID) as { id: number; frozenRankedSegment: unknown } | undefined

  const tailDesc = db
    .prepare(
      `SELECT 'entry:' || id || ' ' || narrative AS line FROM bucket_entries
       WHERE bucketID = ? AND isCompacted = 0 ORDER BY createdAt DESC, id DESC LIMIT ?`
    )
    .all(bucketID, SNAPSHOT_TAIL_CAP) as { line: string }[]

  const facts = db
    .prepare(
      `SELECT 'fact:' || id || ' ' || statement || ' [evidence: ' || evidenceText || '; refs: ' || evidenceRefsJson || ']' AS line
       FROM bucket_facts
       WHERE bucketID = ? AND validityState = 'validated' AND (expiresAt IS NULL OR expiresAt > ?)
       ORDER BY createdAt DESC, id DESC LIMIT ?`
    )
    .all(bucketID, now, SNAPSHOT_FACTS_CAP) as { line: string }[]

  const worthiness = db
    .prepare(
      `SELECT COALESCE(MAX(notifyWorthiness), 0) AS w FROM bucket_facts
       WHERE bucketID = ? AND validityState = 'validated' AND (expiresAt IS NULL OR expiresAt > ?)`
    )
    .get(bucketID, now) as { w: number }

  return {
    bucketID,
    versionID: version ? Number(version.id) : null,
    frozenRankedSegment: version ? frozenToString(version.frozenRankedSegment) : '',
    tail: tailDesc.map((r) => r.line).reverse(),
    validatedFacts: facts.map((r) => r.line),
    notifyWorthiness: Number(worthiness.w),
    visitCount: Number(bucket.visitCount)
  }
}

/** Snapshot for a fence: the persisted visit's bucket must still equal the
 *  fence's (mid-visit rebind guard), and the visit must be active|completed. */
export function snapshotForFenceOn(
  db: ContextBucketDb,
  fence: ContextVisitFence,
  now: number
): BucketSnapshot | null {
  if (fence.bucketID === null) return null
  const visit = db
    .prepare(
      `SELECT bucketID, outcome FROM context_visits
       WHERE id = ? AND contextGeneration = ? AND poolEpoch = ?`
    )
    .get(fence.visitID, fence.contextGeneration, fence.poolEpoch) as
    | { bucketID: string | null; outcome: VisitOutcome }
    | undefined
  if (!visit) return null
  if (visit.outcome !== 'active' && visit.outcome !== 'completed') return null
  if (visit.bucketID !== fence.bucketID) return null
  return snapshotOn(db, fence.bucketID, now)
}

// --- citation validation ---------------------------------------------------

export function validatedEntryRefsOn(
  db: ContextBucketDb,
  refs: readonly string[],
  bucketID: string
): string[] {
  const out: string[] = []
  const stmt = db.prepare(`SELECT 1 AS ok FROM bucket_entries WHERE id = ? AND bucketID = ?`)
  for (const ref of refs) {
    const id = ref.startsWith('entry:') ? ref.slice('entry:'.length) : ref
    if (id.length === 0) continue
    if (stmt.get(id, bucketID)) out.push('entry:' + id)
  }
  return out
}

export function validatedFactIDsOn(
  db: ContextBucketDb,
  ids: readonly string[],
  snapshotFactIds: ReadonlySet<string>,
  bucketID: string,
  now: number
): string[] {
  const out: string[] = []
  const stmt = db.prepare(
    `SELECT 1 AS ok FROM bucket_facts
     WHERE id = ? AND bucketID = ? AND validityState = 'validated' AND (expiresAt IS NULL OR expiresAt > ?)`
  )
  for (const rawId of ids) {
    const id = rawId.startsWith('fact:') ? rawId.slice('fact:'.length) : rawId
    if (id.length === 0) continue
    if (!snapshotFactIds.has(id)) continue
    if (stmt.get(id, bucketID, now)) out.push('fact:' + id)
  }
  return out
}

/** Parse the ids back out of a snapshot's quoted fact lines (`fact:<id> …`). */
export function snapshotFactIdSet(snapshot: BucketSnapshot): Set<string> {
  const ids = new Set<string>()
  for (const line of snapshot.validatedFacts) {
    if (!line.startsWith('fact:')) continue
    const space = line.indexOf(' ')
    if (space > 'fact:'.length) ids.add(line.slice('fact:'.length, space))
  }
  return ids
}

// --- extraction write + version publish ------------------------------------

export interface ExtractionFact {
  statement: string
  identifiers: string[]
  evidence_text: string
  evidence_refs: string[]
  confidence: number
  notify_worthiness: number
}

export interface BucketExtraction {
  narrative: string
  facts: ExtractionFact[]
  destination?: string
}

export interface ExtractionWriteResult {
  versionID: number
  maximumValidatedWorthiness: number
}

export function writeExtractionOn(
  db: ContextBucketDb,
  fence: ContextVisitFence,
  extraction: BucketExtraction,
  ctx: { appName: string; windowTitle: string | null },
  now: number
): ExtractionWriteResult | null {
  if (fence.bucketID === null) return null
  const bucketID = fence.bucketID
  return inTxn(db, () => {
    const visit = db
      .prepare(
        `SELECT outcome, lastFrameId FROM context_visits
         WHERE id = ? AND contextGeneration = ? AND poolEpoch = ? AND bucketID = ?`
      )
      .get(fence.visitID, fence.contextGeneration, fence.poolEpoch, bucketID) as
      | { outcome: VisitOutcome; lastFrameId: number | null }
      | undefined
    // Extraction only lands for completed departed visits whose persisted
    // bucket still matches the fence (GC or a rebind nulls/moves it).
    if (!visit || visit.outcome !== 'completed') return null

    const allowedRefs = new Set<string>([`visit:${fence.visitID}`])
    if (visit.lastFrameId !== null) allowedRefs.add(`screenshot:${visit.lastFrameId}`)

    const narrative = prefixChars(extraction.narrative, NARRATIVE_CAP)
    const facts = extraction.facts.slice(0, FACTS_PER_EXTRACTION)

    const resolvableRefs = (refs: readonly string[]): string[] =>
      refs.map((r) => prefixChars(r, EVIDENCE_REF_LENGTH_CAP)).filter((r) => allowedRefs.has(r))

    // Entry evidence = the union of the facts' resolvable refs, capped at 40.
    const entryRefs: string[] = []
    for (const fact of facts) {
      for (const ref of resolvableRefs(fact.evidence_refs)) {
        if (entryRefs.length >= EVIDENCE_REFS_PER_ENTRY) break
        entryRefs.push(ref)
      }
    }

    const entryID = randomUUID().toLowerCase()
    db.prepare(
      `INSERT INTO bucket_entries
         (id, bucketID, visitID, bucketVersionID, appName, rawContextKey, normalizedContextKey,
          narrative, evidenceRefsJson, tokenCount, isCompacted, createdAt)
       VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, 0, ?)`
    ).run(
      entryID,
      bucketID,
      fence.visitID,
      ctx.appName,
      `${ctx.appName}\n${ctx.windowTitle ?? ''}`,
      identityKey(ctx.appName, ctx.windowTitle) ?? '',
      narrative,
      JSON.stringify(entryRefs),
      estimatedTokens(narrative),
      now
    )

    let maximumValidatedWorthiness = 0
    const duplicateStmt = db.prepare(
      `SELECT 1 AS ok FROM bucket_facts WHERE bucketID = ? AND statement = ?`
    )
    const insertFact = db.prepare(
      `INSERT INTO bucket_facts
         (id, bucketID, entryID, appName, statement, identifiersJson, evidenceText, evidenceRefsJson,
          validityState, dispositionState, confidence, notifyWorthiness, expiresAt, createdAt, updatedAt, workstreamTag)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'none', ?, ?, NULL, ?, ?, NULL)`
    )

    for (const fact of facts) {
      const statement = prefixChars(fact.statement, STATEMENT_CAP)
      if (isScaffoldingStatement(statement)) continue

      const evidenceText = prefixChars(fact.evidence_text, EVIDENCE_TEXT_CAP)
      const evidenceRefs = resolvableRefs(fact.evidence_refs.slice(0, EVIDENCE_REFS_PER_FACT))
      const loweredEvidence = evidenceText.toLowerCase()
      const identifiers = fact.identifiers
        .slice(0, IDENTIFIERS_PER_FACT)
        .map((i) => prefixChars(i, IDENTIFIER_LENGTH_CAP).trim())
        .filter((i) => i.length > 0)
        .filter((i) => !BOOKKEEPING_IDENTIFIER_RE.test(i))
        .filter((i) => loweredEvidence.includes(i.toLowerCase()))

      const isDuplicate = duplicateStmt.get(bucketID, statement) !== undefined
      let validity: string
      if (isDuplicate) {
        validity = 'superseded'
      } else if (
        identifiers.length > 0 &&
        evidenceText.trim().length > 0 &&
        evidenceRefs.length > 0
      ) {
        validity = 'validated'
      } else {
        validity = 'needs_review'
      }

      const worthiness = validity === 'validated' ? clamp01(fact.notify_worthiness) : 0
      if (worthiness > maximumValidatedWorthiness) maximumValidatedWorthiness = worthiness

      insertFact.run(
        randomUUID().toLowerCase(),
        bucketID,
        entryID,
        ctx.appName,
        statement,
        JSON.stringify(identifiers),
        evidenceText,
        JSON.stringify(evidenceRefs),
        validity,
        clamp01(fact.confidence),
        worthiness,
        now,
        now
      )
    }

    db.prepare(
      `UPDATE context_buckets SET notifyWorthiness = MAX(notifyWorthiness, ?), updatedAt = ? WHERE id = ?`
    ).run(maximumValidatedWorthiness, now, bucketID)

    const versionID = publishVersion(db, bucketID, now)
    db.prepare(`UPDATE bucket_entries SET bucketVersionID = ? WHERE id = ?`).run(versionID, entryID)

    return { versionID, maximumValidatedWorthiness }
  })
}

/** Publish a new bucket version: compact when more than 5 uncompacted entries
 *  (all but the newest 5 append to the frozen segment as `- entry:<id> <narrative>`
 *  lines), then front-trim the frozen bytes to the 16,000-byte budget. */
function publishVersion(db: ContextBucketDb, bucketID: string, now: number): number {
  const last = db
    .prepare(
      `SELECT COALESCE(MAX(version), 0) AS v, MAX(id) AS lastId FROM bucket_versions WHERE bucketID = ?`
    )
    .get(bucketID) as { v: number; lastId: number | null }

  const previousFrozen =
    last.lastId !== null
      ? frozenToString(
          (
            db
              .prepare(`SELECT frozenRankedSegment FROM bucket_versions WHERE id = ?`)
              .get(last.lastId) as {
              frozenRankedSegment: unknown
            }
          ).frozenRankedSegment
        )
      : ''

  let frozen = previousFrozen
  const uncompacted = db
    .prepare(
      `SELECT id, narrative FROM bucket_entries WHERE bucketID = ? AND isCompacted = 0 ORDER BY createdAt ASC, id ASC`
    )
    .all(bucketID) as { id: string; narrative: string }[]

  if (uncompacted.length > RETAINED_TAIL_COUNT) {
    const toCompact = uncompacted.slice(0, uncompacted.length - RETAINED_TAIL_COUNT)
    const mark = db.prepare(`UPDATE bucket_entries SET isCompacted = 1 WHERE id = ?`)
    for (const entry of toCompact) {
      frozen += `- entry:${entry.id} ${entry.narrative}\n`
      mark.run(entry.id)
    }
  }

  // Front-trim oldest lines to the byte budget (never split a line).
  while (Buffer.byteLength(frozen, 'utf8') > FROZEN_RANKED_BYTE_BUDGET) {
    const firstNewline = frozen.indexOf('\n')
    if (firstNewline < 0 || firstNewline === frozen.length - 1) break
    frozen = frozen.slice(firstNewline + 1)
  }

  const info = db
    .prepare(
      `INSERT INTO bucket_versions (bucketID, version, header, frozenRankedSegment, rankedTokenCount, createdAt)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
    .run(
      bucketID,
      Number(last.v) + 1,
      STABLE_HEADER,
      Buffer.from(frozen, 'utf8'),
      estimatedTokens(frozen),
      now
    ) as {
    lastInsertRowid: number | bigint
  }
  return Number(info.lastInsertRowid)
}

// --- destination binding ---------------------------------------------------

/** Apply a sanitized `dest:` subject to the visit's binding (mac
 *  ContextDestinationBinder.apply, fence-gated by applyDestination). Returns
 *  the bucket the binding now points at, or null when nothing changed. */
export function applyDestinationOn(
  db: ContextBucketDb,
  fence: ContextVisitFence,
  subjectID: string,
  now: number
): string | null {
  if (fence.bucketID === null) return null
  if (!subjectID.startsWith(DESTINATION_SUBJECT_PREFIX)) return null
  const currentBucketID = fence.bucketID

  return inTxn(db, () => {
    const visit = db
      .prepare(
        `SELECT referenceHash FROM context_visits
         WHERE id = ? AND contextGeneration = ? AND poolEpoch = ? AND bucketID = ?
           AND outcome IN ('active', 'completed')`
      )
      .get(fence.visitID, fence.contextGeneration, fence.poolEpoch, currentBucketID) as
      | { referenceHash: string }
      | undefined
    if (!visit) return null
    const referenceHash = visit.referenceHash
    if (referenceHash.startsWith('ephemeral:')) return null

    const binding = db
      .prepare(`SELECT subjectID, source FROM subject_bindings WHERE referenceHash = ?`)
      .get(referenceHash) as { subjectID: string; source: string } | undefined
    if (!binding) return null
    if (binding.source.endsWith('explicit_open')) return null
    if (binding.source.startsWith('derived_destination:')) return null
    if (binding.subjectID === subjectID) return null

    const existing = db
      .prepare(
        `SELECT id FROM context_buckets WHERE subjectKind = 'context' AND subjectID = ? AND workstreamID IS NULL`
      )
      .get(subjectID) as { id: string } | undefined

    let resolved: string
    if (existing) {
      // Another title already owns this destination: point future visits there
      // and credit its freshness so GC never prefers deleting the destination
      // bucket over the per-title orphans feeding it.
      db.prepare(
        `UPDATE context_buckets SET visitCount = visitCount + 1, lastVisitedAt = ?, updatedAt = ? WHERE id = ?`
      ).run(now, now, existing.id)
      resolved = existing.id
    } else {
      const claimed = db
        .prepare(
          `UPDATE context_buckets SET subjectID = ?, displayLabel = COALESCE(displayLabel, ?), updatedAt = ?
           WHERE id = ? AND subjectKind = 'context' AND workstreamID IS NULL`
        )
        .run(
          subjectID,
          subjectID.slice(DESTINATION_SUBJECT_PREFIX.length),
          now,
          currentBucketID
        ) as {
        changes: number | bigint
      }
      if (Number(claimed.changes) === 0) return null
      resolved = currentBucketID
    }

    db.prepare(
      `UPDATE subject_bindings
       SET bucketID = ?, subjectKind = 'context', subjectID = ?, source = ?, updatedAt = ?
       WHERE referenceHash = ?`
    ).run(resolved, subjectID, DESTINATION_DERIVATION_SOURCE, now, referenceHash)

    return resolved
  })
}

// --- subject bindings (explicit) -------------------------------------------

export function upsertExplicitBindingOn(
  db: ContextBucketDb,
  binding: {
    referenceHash: string
    subjectKind: string
    subjectID: string
    workstreamID: string | null
  },
  now: number
): boolean {
  if (!binding.referenceHash.startsWith('sha256:')) return false
  inTxn(db, () => {
    db.prepare(
      `INSERT INTO subject_bindings
         (referenceHash, subjectKind, subjectID, workstreamID, confidence, source, occurrenceCount, createdAt, updatedAt)
       VALUES (?, ?, ?, ?, 1.0, 'explicit_open', 1, ?, ?)
       ON CONFLICT(referenceHash) DO UPDATE SET
         subjectKind = excluded.subjectKind,
         subjectID = excluded.subjectID,
         workstreamID = excluded.workstreamID,
         confidence = 1.0,
         source = 'explicit_open',
         occurrenceCount = occurrenceCount + 1,
         updatedAt = excluded.updatedAt`
    ).run(
      binding.referenceHash,
      binding.subjectKind,
      binding.subjectID,
      binding.workstreamID,
      now,
      now
    )
    pruneUnboundBindings(db, now)
  })
  return true
}

function pruneUnboundBindings(db: ContextBucketDb, now: number): void {
  db.prepare(`DELETE FROM subject_bindings WHERE bucketID IS NULL AND updatedAt <= ?`).run(
    now - BINDING_UNBOUND_RETENTION_MS
  )
  db.prepare(
    `DELETE FROM subject_bindings WHERE bucketID IS NULL AND referenceHash NOT IN (
       SELECT referenceHash FROM subject_bindings WHERE bucketID IS NULL ORDER BY updatedAt DESC LIMIT ?
     )`
  ).run(BINDING_UNBOUND_KEEP)
}

export interface StoredSubjectBinding {
  subjectKind: string
  subjectID: string
  workstreamID: string | null
}

/** Resolve a stored binding for a reference hash, only when fresh (30 days). */
export function lookupBindingOn(
  db: ContextBucketDb,
  referenceHash: string,
  now: number
): StoredSubjectBinding | null {
  const row = db
    .prepare(
      `SELECT subjectKind, subjectID, workstreamID FROM subject_bindings
       WHERE referenceHash = ? AND updatedAt > ?`
    )
    .get(referenceHash, now - BINDING_RESOLVE_WINDOW_MS) as StoredSubjectBinding | undefined
  return row ?? null
}

// --- deterministic GC ------------------------------------------------------

function deleteBucketsCascade(db: ContextBucketDb, bucketIDs: string[]): void {
  if (bucketIDs.length === 0) return
  const marks = placeholders(bucketIDs.length)
  db.prepare(
    `UPDATE proactive_deliveries SET bucketVersionID = NULL
     WHERE bucketVersionID IN (SELECT id FROM bucket_versions WHERE bucketID IN (${marks}))`
  ).run(...bucketIDs)
  db.prepare(`DELETE FROM bucket_facts WHERE bucketID IN (${marks})`).run(...bucketIDs)
  db.prepare(`DELETE FROM bucket_entries WHERE bucketID IN (${marks})`).run(...bucketIDs)
  db.prepare(`DELETE FROM bucket_versions WHERE bucketID IN (${marks})`).run(...bucketIDs)
  db.prepare(`DELETE FROM bucket_workstreams WHERE bucketID IN (${marks})`).run(...bucketIDs)
  db.prepare(`DELETE FROM proactive_candidates WHERE bucketID IN (${marks})`).run(...bucketIDs)
  db.prepare(`UPDATE context_visits SET bucketID = NULL WHERE bucketID IN (${marks})`).run(
    ...bucketIDs
  )
  db.prepare(`UPDATE subject_bindings SET bucketID = NULL WHERE bucketID IN (${marks})`).run(
    ...bucketIDs
  )
  db.prepare(`UPDATE proactive_deliveries SET bucketID = NULL WHERE bucketID IN (${marks})`).run(
    ...bucketIDs
  )
  db.prepare(`DELETE FROM context_buckets WHERE id IN (${marks})`).run(...bucketIDs)
}

export function runDeterministicGCOn(db: ContextBucketDb, now: number): void {
  inTxn(db, () => {
    db.prepare(`DELETE FROM proactive_deliveries WHERE expiresAt <= ?`).run(now)
    db.prepare(`DELETE FROM proactive_candidates WHERE state <> 'armed' OR expiresAt <= ?`).run(now)
    db.prepare(`DELETE FROM bucket_facts WHERE expiresAt IS NOT NULL AND expiresAt <= ?`).run(now)

    const stale = db
      .prepare(
        `SELECT id FROM context_buckets b
         WHERE lastVisitedAt IS NOT NULL AND lastVisitedAt < ?
           AND NOT EXISTS (SELECT 1 FROM context_visits v WHERE v.bucketID = b.id AND v.outcome = 'active')`
      )
      .all(now - STALE_BUCKET_AGE_MS) as { id: string }[]

    const overflow = db
      .prepare(
        `SELECT id FROM context_buckets b
         WHERE NOT EXISTS (SELECT 1 FROM context_visits v WHERE v.bucketID = b.id AND v.outcome = 'active')
         ORDER BY COALESCE(lastVisitedAt, createdAt) DESC LIMIT -1 OFFSET ?`
      )
      .all(BUCKET_OVERFLOW_KEEP) as { id: string }[]

    const toDelete = [...new Set([...stale.map((r) => r.id), ...overflow.map((r) => r.id)])]
    deleteBucketsCascade(db, toDelete)
  })
}
