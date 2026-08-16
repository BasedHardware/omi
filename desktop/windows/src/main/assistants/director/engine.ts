/**
 * Context proactivity engine — Windows port of macOS ContextProactivityEngine:
 * the decision orchestrator between a visit fence and a delivered (or
 * suppressed) notification.
 *
 * Invariants carried from mac, in force here:
 * - contextEntered runs its steps in the exact mac order; every await boundary
 *   re-checks the session epoch and visit freshness, and any late failure
 *   terminalizes the reserved ledger row (never leaves it dangling).
 * - Grounding: a non-silent decision needs >= 1 validated own-bucket entry ref
 *   AND >= 1 validated fact id; retrieved refs are additive citations only.
 *   Failure rewrites the decision to silence/suppressed.
 * - One retrieval hop max; a failed or empty hop keeps the first decision.
 * - Silent and failed evaluations never burn the daily budget (the ledger
 *   excludes suppressed/failed rows).
 * - The armed-candidate fast path substitutes for the director call: one visit
 *   never pays for two decisions.
 */

import type {
  BucketSnapshot,
  ContextBucketDb,
  ContextVisitFence
} from '../../ipc/contextBucketStore'
import {
  markVisitSettledOn,
  snapshotFactIdSet,
  snapshotForFenceOn,
  validatedEntryRefsOn,
  validatedFactIDsOn,
  visitFreshnessOn
} from '../../ipc/contextBucketStore'
import {
  advanceDeliveryOn,
  beginDeliveryAttemptOn,
  consumeCandidateOn,
  declineCandidateOn,
  groundingFactIDsValidOn,
  lookupArmedOn,
  recentDeliveredForBucketOn,
  restoreCandidateOn,
  tagsForBucketOn,
  type ArmedCandidate,
  type RecentDelivery
} from '../../ipc/proactivityLedger'
import { freeGate, type DeliveryGateInput } from './deliveryPolicy'
import { LaneError, type LaneClient, type LaneResult } from './laneClient'
import {
  CANDIDATE_GATE_MAX_COMPLETION_TOKENS,
  CANDIDATE_GATE_SCHEMA,
  DIRECTOR_CACHE_KEY,
  DIRECTOR_MAX_COMPLETION_TOKENS,
  candidateGatePrompt,
  decodeDirectorDecision,
  directorSchema,
  directorStablePrompt,
  directorVolatilePrompt,
  retrievalPromptSection,
  selectDirectorTasks,
  type DirectorDecision
} from './prompts'
import {
  planRetrievalHop,
  partitionCitedRefs,
  validatedRetrievedRefs,
  type RetrievalOutcome
} from './retrieval'

export const DWELL_SETTLE_MS = 2_000
export const DEPARTURE_WORTHINESS_THRESHOLD = 0.6
export const DEPARTED_FRAME_CAPTURE_EPSILON_MS = 2_000
export const MESSAGE_DEDUP_JACCARD_THRESHOLD = 0.6

export interface DirectorFrame {
  frameId: number | null
  appName: string
  windowTitle: string | null
  captureTime: number
  storedAt: number
}

export type PresentationOutcome = 'presented' | 'queued' | 'suppressed' | 'unavailable'

export interface EngineDeps {
  db(): ContextBucketDb
  lane: LaneClient
  now(): number
  sleep(ms: number): Promise<void>
  sessionEpoch(): number
  gateInput(): DeliveryGateInput
  /** Only 'queued' proceeds (mac contextDirectorPresentationPreflight). */
  presentationPreflight(): PresentationOutcome
  present(args: {
    title: string
    message: string
    decisionType: string
    provenanceRef: string
    onPresented(): void
    onDropped(): void
  }): PresentationOutcome
  trackedFrame(sinceStartedAt: number): DirectorFrame | null
  readFrameImage(frameId: number): Promise<string | null>
  incompleteTasks(): Array<{ description: string; dueAt: number | null; createdAt: number }>
  retrievalHopEnabled(): boolean
  candidatesEnabled(): boolean
  runRetrieval(query: string): Promise<RetrievalOutcome>
  /** task_candidate graduation (canonical candidate creation). */
  graduate(
    factIDs: string[],
    bucketID: string
  ): Promise<{ ok: true } | { ok: false; reason: string }>
  timeZone?: string
  log?(message: string): void
}

/** Token-set Jaccard >= 0.6 (mac SuggestionDeduplication): lowercase,
 *  non-alphanumeric split, tokens longer than 2 chars. */
export function messagesAreDuplicates(a: string, b: string): boolean {
  const tokens = (value: string): Set<string> =>
    new Set(
      value
        .toLowerCase()
        .split(/[^a-z0-9]+/)
        .filter((t) => t.length > 2)
    )
  const ta = tokens(a)
  const tb = tokens(b)
  if (ta.size === 0 || tb.size === 0) return false
  let intersection = 0
  for (const t of ta) if (tb.has(t)) intersection += 1
  const union = ta.size + tb.size - intersection
  return union > 0 && intersection / union >= MESSAGE_DEDUP_JACCARD_THRESHOLD
}

function sortedJson(value: Record<string, unknown>): string {
  const sorted: Record<string, unknown> = {}
  for (const key of Object.keys(value).sort()) sorted[key] = value[key]
  return JSON.stringify(sorted)
}

export class ContextProactivityEngine {
  private readonly deps: EngineDeps
  private readonly inflightVisits = new Set<number>()

  constructor(deps: EngineDeps) {
    this.deps = deps
  }

  /** The context-entry trigger: the exact mac step order. */
  async contextEntered(fence: ContextVisitFence): Promise<void> {
    if (fence.bucketID === null) return
    const epoch = this.deps.sessionEpoch()
    if (!this.admitVisit(fence.visitID)) return
    try {
      await this.deps.sleep(DWELL_SETTLE_MS)
      if (this.deps.sessionEpoch() !== epoch) return
      const db = this.deps.db()
      if (!markVisitSettledOn(db, fence, this.deps.now())) return
      if (this.deps.sessionEpoch() !== epoch) return
      if (freeGate(this.deps.gateInput()) !== 'allowed') return
      if (!visitFreshnessOn(db, fence, this.deps.now()).fresh) return
      const snapshot = snapshotForFenceOn(db, fence, this.deps.now())
      if (snapshot === null) return
      if (!(snapshot.notifyWorthiness > 0 && snapshot.validatedFacts.length > 0)) return

      // Sample first, then re-read freshness (order is load-bearing on mac).
      const frame = this.deps.trackedFrame(fence.startedAt)
      const freshness = visitFreshnessOn(db, fence, this.deps.now())
      if (!freshness.fresh) return
      if (frame === null || !frameMayGround(frame, fence.startedAt, freshness.endedAt)) return

      await this.evaluateAndDeliver(fence, snapshot, frame, epoch)
    } finally {
      this.inflightVisits.delete(fence.visitID)
    }
  }

  /** The departure trigger: same gates, grounded on the departing frame; no
   *  settle sleep, no frame lookup. The worthiness threshold and flag live at
   *  the caller (the rollup writer). */
  async evaluateAfterDeparture(
    fence: ContextVisitFence,
    departingFrame: DirectorFrame
  ): Promise<void> {
    if (fence.bucketID === null) return
    const epoch = this.deps.sessionEpoch()
    if (!this.admitVisit(fence.visitID)) return
    try {
      const db = this.deps.db()
      if (freeGate(this.deps.gateInput()) !== 'allowed') return
      if (!visitFreshnessOn(db, fence, this.deps.now()).fresh) return
      const snapshot = snapshotForFenceOn(db, fence, this.deps.now())
      if (snapshot === null) return
      if (!(snapshot.notifyWorthiness > 0 && snapshot.validatedFacts.length > 0)) return
      await this.evaluateAndDeliver(fence, snapshot, departingFrame, epoch)
    } finally {
      this.inflightVisits.delete(fence.visitID)
    }
  }

  private admitVisit(visitID: number): boolean {
    if (this.inflightVisits.has(visitID)) return false
    this.inflightVisits.add(visitID)
    return true
  }

  private async evaluateAndDeliver(
    fence: ContextVisitFence,
    snapshot: BucketSnapshot,
    frame: DirectorFrame,
    epoch: number
  ): Promise<void> {
    const db = this.deps.db()
    const bucketID = fence.bucketID as string
    if (this.deps.presentationPreflight() !== 'queued') return

    const recentDeliveries = recentDeliveredForBucketOn(db, bucketID, this.deps.now())

    // Candidate fast path substitutes for the director call.
    if (this.deps.candidatesEnabled()) {
      const candidate = this.deliverableCandidate(db, bucketID, recentDeliveries)
      if (candidate !== null) {
        await this.runCandidateGate(fence, candidate, frame, recentDeliveries, epoch)
        return
      }
    }

    const reservation = beginDeliveryAttemptOn(db, fence, this.deps.gateInput(), this.deps.now())
    if ('rejected' in reservation) {
      this.deps.log?.(`director reservation rejected: ${reservation.rejected}`)
      return
    }
    const rowId = reservation.reservationId

    const allowLookup = this.deps.retrievalHopEnabled()
    const stablePrompt = directorStablePrompt(snapshot, allowLookup)
    const volatilePrompt = directorVolatilePrompt({
      tasks: selectDirectorTasks(this.deps.incompleteTasks(), frame.captureTime),
      frame: {
        appName: frame.appName,
        windowTitle: frame.windowTitle,
        captureTime: frame.captureTime
      },
      recentDeliveries,
      visitCount: snapshot.visitCount,
      timeZone: this.deps.timeZone
    })
    const image = frame.frameId !== null ? await this.deps.readFrameImage(frame.frameId) : null

    let first: DirectorDecision
    let firstResult: LaneResult
    try {
      firstResult = await this.deps.lane.complete({
        operation: 'proactive_reasoning',
        prompt: stablePrompt,
        uncachedPrompt: volatilePrompt,
        imageBase64Jpeg: image ?? undefined,
        jsonSchema: directorSchema(allowLookup),
        cacheKey: DIRECTOR_CACHE_KEY,
        maxCompletionTokens: DIRECTOR_MAX_COMPLETION_TOKENS
      })
      const decoded = decodeDirectorDecision(firstResult.content)
      if (decoded === null) throw new LaneError('decode', 'director decision failed to decode')
      first = decoded
    } catch (err) {
      this.failRow(rowId, err)
      return
    }

    if (!this.scopeStillCurrent(fence, epoch)) {
      this.terminalize(rowId, 'stale_visit')
      return
    }

    // One bounded retrieval hop; a failed or empty hop keeps the first decision.
    let final = first
    let laneResult = firstResult
    let hop: RetrievalOutcome | null = null
    let hopQuery: string | null = null
    const plannedQuery = planRetrievalHop(first.lookupQuery, allowLookup, 0)
    if (plannedQuery !== null) {
      hopQuery = plannedQuery
      try {
        const outcome = await this.deps.runRetrieval(plannedQuery)
        if (!this.scopeStillCurrent(fence, epoch)) {
          this.terminalize(rowId, 'stale_visit')
          return
        }
        if (freeGate(this.deps.gateInput()) !== 'allowed') {
          this.terminalize(rowId, 'pre_model_gate')
          return
        }
        const section = retrievalPromptSection(plannedQuery, outcome.items, this.deps.timeZone)
        if (section !== null) {
          const second = await this.deps.lane.complete({
            operation: 'proactive_reasoning',
            prompt: stablePrompt,
            uncachedPrompt: `${volatilePrompt}\n\n${section}`,
            imageBase64Jpeg: image ?? undefined,
            jsonSchema: directorSchema(true),
            cacheKey: DIRECTOR_CACHE_KEY,
            maxCompletionTokens: DIRECTOR_MAX_COMPLETION_TOKENS
          })
          const decodedSecond = decodeDirectorDecision(second.content)
          if (decodedSecond !== null) {
            final = decodedSecond
            laneResult = second
            hop = outcome
          }
        }
      } catch {
        // Retrieval may upgrade a decision, never lose one.
      }
      if (!this.scopeStillCurrent(fence, epoch)) {
        this.terminalize(rowId, 'stale_visit')
        return
      }
    }

    // Validate citations against the store and the per-call allowlist.
    const { bucketRefs, retrievedRefs } = partitionCitedRefs(final.bucketEntryRefs)
    const validEntryRefs = validatedEntryRefsOn(db, bucketRefs, bucketID)
    const validRetrieved = validatedRetrievedRefs(retrievedRefs, hop?.allowedRefs ?? new Set())
    const validFactIDs =
      final.decision === 'silence'
        ? []
        : validatedFactIDsOn(
            db,
            final.factIDs,
            snapshotFactIdSet(snapshot),
            bucketID,
            this.deps.now()
          )

    const provenance: Record<string, unknown> = {
      bucket_id: bucketID,
      bucket_version_id: snapshot.versionID,
      bucket_entry_refs: [...validEntryRefs, ...validRetrieved],
      fact_ids: validFactIDs,
      reasoning: final.reasoning,
      provider_model: laneResult.providerModel,
      cached_tokens: laneResult.cachedTokens,
      cache_write_tokens: laneResult.cacheWriteTokens
    }
    if (hopQuery !== null) {
      provenance.retrieval = {
        query: hopQuery,
        result_count: hop?.items.length ?? 0,
        hop_completed: hop !== null,
        cited_refs: validRetrieved
      }
    }

    advanceDeliveryOn(db, {
      id: rowId,
      state: 'model_completed',
      decisionType: final.decision,
      provenanceJson: sortedJson(provenance),
      message: final.message,
      at: this.deps.now()
    })

    if (final.decision === 'silence') {
      advanceDeliveryOn(db, { id: rowId, state: 'suppressed', at: this.deps.now() })
      return
    }

    // Grounding: bucket-only refs; retrieved citations never substitute.
    if (!(validEntryRefs.length > 0 && validFactIDs.length > 0)) {
      advanceDeliveryOn(db, {
        id: rowId,
        state: 'suppressed',
        decisionType: 'silence',
        at: this.deps.now()
      })
      return
    }

    advanceDeliveryOn(db, { id: rowId, state: 'policy_approved', at: this.deps.now() })

    if (final.decision === 'task_candidate') {
      const graduation = await this.deps.graduate(
        validFactIDs.map((id) => id.slice('fact:'.length)),
        bucketID
      )
      if (!this.scopeStillCurrent(fence, epoch)) {
        this.terminalize(rowId, 'stale_visit')
        return
      }
      if (!graduation.ok) {
        advanceDeliveryOn(db, {
          id: rowId,
          state: 'failed',
          provenanceJson: sortedJson({
            ...provenance,
            failure: 'candidate_graduation_failed',
            graduation_reason: graduation.reason
          }),
          at: this.deps.now()
        })
        return
      }
    }

    // A mid-flight master-off/paywall/frequency change still suppresses.
    if (
      freeGate(this.deps.gateInput()) !== 'allowed' ||
      this.deps.presentationPreflight() !== 'queued'
    ) {
      advanceDeliveryOn(db, { id: rowId, state: 'suppressed', at: this.deps.now() })
      return
    }

    this.presentDecision(rowId, final)
  }

  private deliverableCandidate(
    db: ContextBucketDb,
    bucketID: string,
    recentDeliveries: RecentDelivery[]
  ): ArmedCandidate | null {
    const tags = tagsForBucketOn(db, bucketID)
    const armed = lookupArmedOn(db, bucketID, tags, this.deps.now())
    for (const candidate of armed) {
      if (candidate.message.trim().length === 0) continue
      const duplicate = recentDeliveries.some(
        (d) => d.message !== null && messagesAreDuplicates(candidate.message, d.message)
      )
      if (duplicate) continue
      if (
        !groundingFactIDsValidOn(
          db,
          candidate.groundingFactIDs,
          candidate.bucketID,
          this.deps.now()
        )
      ) {
        declineCandidateOn(db, candidate.id, this.deps.now())
        continue
      }
      return candidate
    }
    return null
  }

  private async runCandidateGate(
    fence: ContextVisitFence,
    candidate: ArmedCandidate,
    frame: DirectorFrame,
    recentDeliveries: RecentDelivery[],
    epoch: number
  ): Promise<void> {
    const db = this.deps.db()
    const reservation = beginDeliveryAttemptOn(db, fence, this.deps.gateInput(), this.deps.now())
    if ('rejected' in reservation) return
    const rowId = reservation.reservationId

    const snapshot = snapshotForFenceOn(db, fence, this.deps.now())
    const visitFacts = snapshot?.validatedFacts ?? []
    const image = frame.frameId !== null ? await this.deps.readFrameImage(frame.frameId) : null

    let show = false
    let reason = ''
    try {
      const result = await this.deps.lane.complete({
        operation: 'proactive_reasoning',
        prompt: candidateGatePrompt({
          message: candidate.message,
          visitFacts,
          recentDeliveries,
          timeZone: this.deps.timeZone
        }),
        imageBase64Jpeg: image ?? undefined,
        jsonSchema: CANDIDATE_GATE_SCHEMA as unknown as Record<string, unknown>,
        maxCompletionTokens: CANDIDATE_GATE_MAX_COMPLETION_TOKENS
      })
      const parsed: unknown = JSON.parse(result.content)
      if (typeof parsed === 'object' && parsed !== null) {
        show = (parsed as Record<string, unknown>).show === true
        const rawReason = (parsed as Record<string, unknown>).reason
        reason = typeof rawReason === 'string' ? [...rawReason].slice(0, 1_200).join('') : ''
      }
    } catch (err) {
      this.failRow(rowId, err)
      return
    }

    if (!this.scopeStillCurrent(fence, epoch)) {
      this.terminalize(rowId, 'stale_visit')
      return
    }

    const provenance = sortedJson({
      source: 'candidate',
      candidate_id: candidate.id,
      reason,
      workstream: candidate.workstreamTag
    })

    if (!show) {
      // Declined gate: suppressed (never burns budget), candidate retired.
      declineCandidateOn(db, candidate.id, this.deps.now())
      advanceDeliveryOn(db, {
        id: rowId,
        state: 'suppressed',
        decisionType: 'silence',
        provenanceJson: provenance,
        at: this.deps.now()
      })
      return
    }

    if (
      freeGate(this.deps.gateInput()) !== 'allowed' ||
      this.deps.presentationPreflight() !== 'queued'
    ) {
      advanceDeliveryOn(db, {
        id: rowId,
        state: 'suppressed',
        provenanceJson: provenance,
        at: this.deps.now()
      })
      return
    }

    advanceDeliveryOn(db, {
      id: rowId,
      state: 'model_completed',
      decisionType: 'insight',
      provenanceJson: provenance,
      message: [...candidate.message].slice(0, 600).join(''),
      at: this.deps.now()
    })
    advanceDeliveryOn(db, { id: rowId, state: 'policy_approved', at: this.deps.now() })

    // Consume only after every pre-presentation gate has passed; restore on drop.
    consumeCandidateOn(db, candidate.id, this.deps.now())
    const outcome = this.deps.present({
      title: [...candidate.message].slice(0, 120).join(''),
      message: [...candidate.message].slice(0, 600).join(''),
      decisionType: 'insight',
      provenanceRef: rowId,
      onPresented: () => {
        advanceDeliveryOn(this.deps.db(), { id: rowId, state: 'delivered', at: this.deps.now() })
      },
      onDropped: () => {
        restoreCandidateOn(this.deps.db(), candidate.id, this.deps.now())
        advanceDeliveryOn(this.deps.db(), {
          id: rowId,
          state: 'failed',
          decisionType: 'silence',
          provenanceJson: '{"failure":"notification_dropped"}',
          at: this.deps.now()
        })
      }
    })
    if (outcome === 'suppressed' || outcome === 'unavailable') {
      // Synchronous refusal paths run onDropped exactly once via present().
    }
  }

  private presentDecision(rowId: string, decision: DirectorDecision): void {
    this.deps.present({
      title: decision.title,
      message: decision.message,
      decisionType: decision.decision,
      provenanceRef: rowId,
      onPresented: () => {
        advanceDeliveryOn(this.deps.db(), { id: rowId, state: 'delivered', at: this.deps.now() })
      },
      onDropped: () => {
        advanceDeliveryOn(this.deps.db(), {
          id: rowId,
          state: 'failed',
          decisionType: 'silence',
          provenanceJson: '{"failure":"notification_dropped"}',
          at: this.deps.now()
        })
      }
    })
  }

  private scopeStillCurrent(fence: ContextVisitFence, epoch: number): boolean {
    if (this.deps.sessionEpoch() !== epoch) return false
    return visitFreshnessOn(this.deps.db(), fence, this.deps.now()).fresh
  }

  private terminalize(
    rowId: string,
    failure: 'stale_owner' | 'stale_visit' | 'pre_model_gate'
  ): void {
    advanceDeliveryOn(this.deps.db(), {
      id: rowId,
      state: 'failed',
      decisionType: 'silence',
      provenanceJson: JSON.stringify({ failure }),
      message: null,
      at: this.deps.now()
    })
  }

  private failRow(rowId: string, err: unknown): void {
    const provenance = err instanceof LaneError ? err.provenance() : { failure: 'decode' }
    advanceDeliveryOn(this.deps.db(), {
      id: rowId,
      state: 'failed',
      decisionType: 'silence',
      provenanceJson: sortedJson(provenance),
      message: null,
      at: this.deps.now()
    })
  }
}

/** A frame may ground an evaluation only when captured inside the visit:
 *  captureTime >= startedAt, and for a departed visit additionally
 *  storedAt <= endedAt and captureTime <= endedAt + 2s. */
export function frameMayGround(
  frame: DirectorFrame,
  startedAt: number,
  endedAt: number | null
): boolean {
  if (frame.captureTime < startedAt) return false
  if (endedAt === null) return true
  return (
    frame.storedAt <= endedAt && frame.captureTime <= endedAt + DEPARTED_FRAME_CAPTURE_EPSILON_MS
  )
}
