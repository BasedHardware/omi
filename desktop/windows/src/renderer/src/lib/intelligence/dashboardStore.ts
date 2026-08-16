// The What Matters Now + canonical goals store (mac parity:
// DashboardIntelligenceStore.swift, ported rule-for-rule). One instance backs
// the Home hub; React binds through useDashboardIntelligence.
//
// Contract highlights, all mirrored from mac:
// - The surface is generation-gated: load bails to a cleared, error-free state
//   unless GET /v1/candidates/control reports workflow_mode 'read', and every
//   mutation requires the captured account generation.
// - GET /v1/what-matters-now returning 404 means "account without the
//   intelligence capability" and clears recommendations WITHOUT surfacing an
//   error; any other failure surfaces one.
// - Rows carry server-registered intervention ids; feedback threads them
//   directly (this surface never registers interventions client-side).
// - Feedback is write-ahead queued in the per-owner durable outbox and the row
//   is removed locally after the attempt, success or not.
import { omiApi } from '../apiClient'
import {
  enqueueFeedback,
  loadOutbox,
  matchesPendingSuppression,
  outboxOwnerId,
  purgeMismatchedGeneration,
  removeFeedback,
  replayOutbox,
  type PendingFeedback
} from './feedbackOutbox'
import { emitFeedbackRecorded, emitInterventionPresented } from './attribution'
import {
  readCanonicalGoal,
  readGoalDetail,
  readWmnProjection,
  readWorkflowControl,
  type CanonicalGoal,
  type FeedbackAction,
  type FeedbackCreateBody,
  type FeedbackReason,
  type FeedbackSubjectKind,
  type GoalDetail,
  type GoalLifecycleTarget,
  type WmnProjection,
  type WmnRecommendation
} from './wireTypes'

// User-facing copy, verbatim from mac.
export const RETRY_BANNER = 'Saved feedback will retry automatically.'
export const FEEDBACK_SAVED_ERROR = 'Saved. Feedback will retry automatically.'
export const TARGET_UNAVAILABLE = 'This review target is no longer available.'
export const CHOOSE_REPLACEMENT = 'Choose a focused goal to replace.'
export const GOALS_UNAVAILABLE = 'Goals are unavailable right now. Try again.'
export const GOAL_UNAVAILABLE = 'This goal is no longer available.'

export type RecommendationDestination =
  | { kind: 'suggested'; candidateId: string }
  | { kind: 'task'; taskId: string; workstreamId: string | null }
  | { kind: 'thread'; workstreamId: string; taskId: string | null }

export type ProjectedRecommendation = {
  /** Stable row id: `${outputVersion}:${dedupeKey}`, the same format mac uses. */
  id: string
  headline: string
  whyNow: string
  contextLabel: string | null
  recommendedAction: string
  destination: RecommendationDestination
  wire: WmnRecommendation
}

/** The projection rules, ported verbatim from mac's DashboardIntelligenceStore.project:
 *  1. an expired projection yields nothing (the whole payload expires atomically);
 *  2. rows suppressed by pending later/dismiss outbox entries are dropped;
 *  3. expired rows are dropped;
 *  4. duplicate dedupe keys keep the FIRST row;
 *  5. subject kinds map to destinations, and artifact/decision/agent_open_loop
 *     rows without a destination workstream are dropped, as are unknown kinds;
 *  6. at most three rows survive. */
export function projectRecommendations(
  projection: WmnProjection,
  now: number,
  pending: PendingFeedback[]
): ProjectedRecommendation[] {
  const projectionExpiry = Date.parse(projection.expiresAt)
  if (Number.isNaN(projectionExpiry) || projectionExpiry <= now) return []
  const seen = new Set<string>()
  const rows: ProjectedRecommendation[] = []
  for (const item of projection.recommendations) {
    if (matchesPendingSuppression(pending, item)) continue
    const rowExpiry = Date.parse(item.expiresAt)
    if (Number.isNaN(rowExpiry) || rowExpiry <= now) continue
    if (seen.has(item.dedupeKey)) continue
    const destination = destinationFor(item)
    if (!destination) continue
    seen.add(item.dedupeKey)
    rows.push({
      id: `${item.outputVersion}:${item.dedupeKey}`,
      headline: item.headline,
      whyNow: item.whyNow,
      contextLabel: item.contextLabel,
      recommendedAction: item.recommendedAction,
      destination,
      wire: item
    })
    if (rows.length >= 3) break
  }
  return rows
}

function destinationFor(item: WmnRecommendation): RecommendationDestination | null {
  switch (item.subjectKind) {
    case 'candidate':
      return { kind: 'suggested', candidateId: item.subjectId }
    case 'task':
      return {
        kind: 'task',
        taskId: item.destinationTaskId ?? item.subjectId,
        workstreamId: item.destinationWorkstreamId
      }
    case 'workstream':
      return {
        kind: 'thread',
        workstreamId: item.destinationWorkstreamId ?? item.subjectId,
        taskId: item.destinationTaskId
      }
    case 'artifact':
    case 'decision':
    case 'agent_open_loop':
      return item.destinationWorkstreamId
        ? {
            kind: 'thread',
            workstreamId: item.destinationWorkstreamId,
            taskId: item.destinationTaskId
          }
        : null
    default:
      return null
  }
}

export type DashboardIntelligenceState = {
  accountGeneration: number | null
  recommendations: ProjectedRecommendation[]
  goals: CanonicalGoal[]
  selectedGoalDetail: GoalDetail | null
  /** Error scoped to the goal-detail request, so an unrelated dashboard error
   *  can never masquerade as this goal's failure (and vice versa). */
  goalDetailError: string | null
  focusReplacementGoalId: string | null
  error: string | null
  isLoading: boolean
  /** True once any load has completed for the current owner; surfaces gate
   *  their canonical-vs-fallback choice on it instead of flashing the fallback
   *  during the cold start. */
  hasLoadedOnce: boolean
  pendingFeedbackCount: number
}

const MAX_FOCUS_RANK_SORT = Number.MAX_SAFE_INTEGER

export function focusedGoals(goals: CanonicalGoal[]): CanonicalGoal[] {
  return goals
    .filter((g) => g.status === 'focused')
    .sort((a, b) => {
      const ra = a.focusRank ?? MAX_FOCUS_RANK_SORT
      const rb = b.focusRank ?? MAX_FOCUS_RANK_SORT
      if (ra !== rb) return ra - rb
      return a.updatedAt.localeCompare(b.updatedAt)
    })
}

export function currentGoals(goals: CanonicalGoal[]): CanonicalGoal[] {
  return goals.filter((g) => g.status !== 'achieved' && g.status !== 'abandoned')
}

export function endedGoals(goals: CanonicalGoal[]): CanonicalGoal[] {
  return goals.filter((g) => g.status === 'achieved' || g.status === 'abandoned')
}

type Deps = {
  get: typeof omiApi.get
  post: typeof omiApi.post
  del: typeof omiApi.delete
  now: () => number
  uuid: () => string
  ownerId: () => string
}

function defaultDeps(): Deps {
  // Late-bound wrappers, not .bind at construction: the store singleton is
  // created at module import, and eagerly dereferencing client methods there
  // couples every importer's test double to the full axios surface.
  return {
    get: ((...args: Parameters<typeof omiApi.get>) => omiApi.get(...args)) as typeof omiApi.get,
    post: ((...args: Parameters<typeof omiApi.post>) => omiApi.post(...args)) as typeof omiApi.post,
    del: ((...args: Parameters<typeof omiApi.delete>) =>
      omiApi.delete(...args)) as typeof omiApi.delete,
    now: Date.now,
    uuid: () => crypto.randomUUID(),
    ownerId: outboxOwnerId
  }
}

function httpStatus(e: unknown): number | undefined {
  return (e as { response?: { status?: number } }).response?.status
}

export class DashboardIntelligenceStore {
  private state: DashboardIntelligenceState = {
    accountGeneration: null,
    recommendations: [],
    goals: [],
    selectedGoalDetail: null,
    goalDetailError: null,
    focusReplacementGoalId: null,
    error: null,
    isLoading: false,
    hasLoadedOnce: false,
    pendingFeedbackCount: 0
  }

  private listeners = new Set<() => void>()
  private deps: Deps
  private activeLoad: Promise<void> | null = null
  private loadedOwnerId: string | null = null
  private ownerRevision = 0
  // intervention_presented fires once per intervention id per store lifetime
  // (mac parity: presentedInterventionIDs).
  private presentedInterventionIds = new Set<string>()

  constructor(deps: Partial<Deps> = {}) {
    this.deps = { ...defaultDeps(), ...deps }
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  getState(): DashboardIntelligenceState {
    return this.state
  }

  private setState(patch: Partial<DashboardIntelligenceState>): void {
    this.state = { ...this.state, ...patch }
    for (const listener of this.listeners) listener()
  }

  /** Full load: control gate, outbox purge + replay, projection, goals. A
   *  concurrent same-owner load awaits the active one instead of stacking. */
  async load(): Promise<void> {
    const owner = this.deps.ownerId()
    if (this.loadedOwnerId !== null && this.loadedOwnerId !== owner) {
      // Owner switched (sign-out/in): bump the revision so every in-flight
      // continuation from the old owner refuses to commit, then clear every
      // owner-scoped piece before loading the new owner's world.
      this.ownerRevision += 1
      this.activeLoad = null
      this.state = {
        accountGeneration: null,
        recommendations: [],
        goals: [],
        selectedGoalDetail: null,
        goalDetailError: null,
        focusReplacementGoalId: null,
        error: null,
        isLoading: false,
        hasLoadedOnce: false,
        pendingFeedbackCount: 0
      }
    }
    if (this.activeLoad) return this.activeLoad
    this.loadedOwnerId = owner
    const run = this.performLoad(owner, this.ownerRevision).finally(() => {
      // Only the load that owns the handle clears it; a superseded load must
      // not null out its successor's.
      if (this.activeLoad === run) this.activeLoad = null
    })
    this.activeLoad = run
    return run
  }

  /** True while `owner` at `revision` is still the world we may commit into
   *  (mac's ownerScopeIsCurrent). Checked after every await before setState. */
  private scopeCurrent(owner: string, revision: number): boolean {
    return this.ownerRevision === revision && this.deps.ownerId() === owner
  }

  private async performLoad(owner: string, revision: number): Promise<void> {
    this.setState({ isLoading: true })
    try {
      let control
      try {
        const controlRes = await this.deps.get('/v1/candidates/control')
        control = readWorkflowControl(controlRes.data)
      } catch {
        if (!this.scopeCurrent(owner, revision)) return
        // A failed control leaves no trustworthy generation: stale rows must
        // not stay actionable under an old generation, so clear them along
        // with the gate (goals stay visible; their mutations are generation-
        // gated off anyway).
        this.setState({
          accountGeneration: null,
          recommendations: [],
          isLoading: false,
          hasLoadedOnce: true,
          error: 'Recommendations are unavailable right now.'
        })
        return
      }
      if (!this.scopeCurrent(owner, revision)) return
      if (control.workflowMode !== 'read') {
        // Any non-read mode clears the surface without error text (mac parity:
        // accounts outside the rollout keep a calm dashboard).
        this.setState({
          accountGeneration: null,
          recommendations: [],
          goals: [],
          error: null,
          isLoading: false,
          hasLoadedOnce: true,
          pendingFeedbackCount: 0
        })
        return
      }

      let pending = purgeMismatchedGeneration(control.accountGeneration, owner)
      if (pending.length > 0) {
        await replayOutbox(
          async (entry) => {
            await this.postFeedback(entry)
          },
          owner,
          () => this.scopeCurrent(owner, revision)
        )
        pending = loadOutbox(owner)
      }
      if (!this.scopeCurrent(owner, revision)) return

      let recommendations: ProjectedRecommendation[] = []
      let wmnError: string | null = null
      try {
        const wmnRes = await this.deps.get('/v1/what-matters-now')
        const projection = readWmnProjection(wmnRes.data)
        if (projection) {
          recommendations = projectRecommendations(projection, this.deps.now(), pending)
        }
      } catch (e) {
        if (httpStatus(e) !== 404) {
          wmnError = 'Recommendations are unavailable right now.'
        }
        // 404 = account without the intelligence capability: empty, no error.
      }

      let goals: CanonicalGoal[] = this.state.goals
      let goalsError: string | null = null
      try {
        const goalsRes = await this.deps.get('/v1/goals/canonical/list', {
          params: { include_ended: true }
        })
        const rows = Array.isArray(goalsRes.data) ? goalsRes.data : []
        goals = rows.flatMap((g) => {
          const goal = readCanonicalGoal(g)
          return goal ? [goal] : []
        })
      } catch {
        goals = []
        goalsError = 'Goals are unavailable right now.'
      }

      if (!this.scopeCurrent(owner, revision)) return
      this.emitPresented(recommendations)
      const error = wmnError ?? goalsError ?? (pending.length > 0 ? RETRY_BANNER : null)
      this.setState({
        accountGeneration: control.accountGeneration,
        recommendations,
        goals,
        error,
        isLoading: false,
        hasLoadedOnce: true,
        pendingFeedbackCount: pending.length
      })
    } finally {
      if (this.scopeCurrent(owner, revision) && this.state.isLoading) {
        this.setState({ isLoading: false })
      }
    }
  }

  /** Apply an externally evaluated projection (the future context-director seam;
   *  mac: applyContextProjection). Re-projects rows, clears the error, and
   *  leaves goals and loading state untouched. */
  applyContextProjection(projection: WmnProjection): void {
    const pending = loadOutbox(this.deps.ownerId())
    const recommendations = projectRecommendations(projection, this.deps.now(), pending)
    this.emitPresented(recommendations)
    this.setState({ recommendations, error: null })
  }

  private emitPresented(recommendations: ProjectedRecommendation[]): void {
    for (const row of recommendations) {
      if (this.presentedInterventionIds.has(row.wire.interventionId)) continue
      this.presentedInterventionIds.add(row.wire.interventionId)
      emitInterventionPresented({
        interventionId: row.wire.interventionId,
        subjectKind: row.wire.feedbackSubjectKind,
        subjectId: row.wire.feedbackSubjectId
      })
    }
  }

  private async postFeedback(entry: PendingFeedback): Promise<string | null> {
    const res = await this.deps.post('/v1/task-intelligence/feedback', entry.request, {
      headers: {
        'Idempotency-Key': entry.idempotencyKey,
        'X-Account-Generation': entry.accountGeneration
      }
    })
    const record = res.data as { attribution_chain_id?: unknown } | null
    return record && typeof record.attribution_chain_id === 'string'
      ? record.attribution_chain_id
      : null
  }

  /** Write-ahead feedback: queue, POST, then remove the row locally whether or
   *  not the POST succeeded (the outbox owns retrying). */
  private async recordFeedback(
    row: ProjectedRecommendation,
    action: FeedbackAction,
    idempotencyKey: string,
    reason: FeedbackReason | null = null,
    laterUntil: string | null = null
  ): Promise<void> {
    const generation = this.state.accountGeneration
    if (generation === null) return
    if (!this.state.recommendations.some((r) => r.id === row.id)) return
    const owner = this.deps.ownerId()
    const request: FeedbackCreateBody = {
      action,
      subject_kind: row.wire.feedbackSubjectKind,
      subject_id: row.wire.feedbackSubjectId,
      intervention_id: row.wire.interventionId,
      reason,
      later_until: laterUntil,
      context_snapshot_hash: null
    }
    const entry: PendingFeedback = { request, idempotencyKey, accountGeneration: generation }
    enqueueFeedback(entry, owner)
    let error: string | null = null
    try {
      const attributionChainId = await this.postFeedback(entry)
      removeFeedback(idempotencyKey, owner)
      emitFeedbackRecorded({
        interventionId: row.wire.interventionId,
        subjectKind: row.wire.feedbackSubjectKind,
        subjectId: row.wire.feedbackSubjectId,
        action,
        reason,
        attributionChainId
      })
    } catch {
      error = FEEDBACK_SAVED_ERROR
    }
    this.setState({
      recommendations: this.state.recommendations.filter((r) => r.id !== row.id),
      error,
      pendingFeedbackCount: loadOutbox(owner).length
    })
  }

  /** do_now, recorded after a successful open. Deterministic key: repeat opens
   *  of the same intervention collapse into one feedback. */
  async recordPrimaryAction(row: ProjectedRecommendation): Promise<void> {
    await this.recordFeedback(row, 'do_now', `wmn:${row.wire.interventionId}:do-now`)
  }

  /** later = +24h, unique key per occurrence. */
  async later(row: ProjectedRecommendation): Promise<void> {
    const laterUntil = new Date(this.deps.now() + 24 * 60 * 60 * 1000).toISOString()
    await this.recordFeedback(
      row,
      'later',
      `wmn:${row.wire.interventionId}:later:${this.deps.uuid().toLowerCase()}`,
      null,
      laterUntil
    )
  }

  /** dismiss with an optional reason; the key is deterministic per
   *  (intervention, reason), with the literal 'none' for a reasonless dismiss. */
  async dismiss(row: ProjectedRecommendation, reason: FeedbackReason | null): Promise<void> {
    await this.recordFeedback(
      row,
      'dismiss',
      `wmn:${row.wire.interventionId}:dismiss:${reason ?? 'none'}`,
      reason
    )
  }

  private async goalMutation(run: () => Promise<void>): Promise<boolean> {
    try {
      await run()
      await this.reload()
      return true
    } catch {
      this.setState({ error: GOALS_UNAVAILABLE })
      return false
    }
  }

  private async reload(): Promise<void> {
    this.loadedOwnerId = null
    await this.load()
  }

  /** Create a canonical goal. status/source are hardcoded server-required
   *  values (mac parity); the occurrence id is the idempotency key and must be
   *  stable across retries of the same sheet. */
  async createGoal(
    fields: {
      title: string
      desiredOutcome: string
      whyItMatters: string | null
      successCriteria: string[]
    },
    occurrenceId: string
  ): Promise<boolean> {
    const generation = this.state.accountGeneration
    if (generation === null) return false
    return this.goalMutation(() =>
      this.deps
        .post(
          '/v1/goals/canonical',
          {
            title: fields.title,
            desired_outcome: fields.desiredOutcome,
            why_it_matters: fields.whyItMatters,
            success_criteria: fields.successCriteria,
            status: 'background',
            source: 'user'
          },
          {
            headers: { 'Idempotency-Key': occurrenceId, 'X-Account-Generation': generation }
          }
        )
        .then(() => undefined)
    )
  }

  /** Focus a goal. A 409 without a replacement means the focus set is full: the
   *  store exposes the goal id so the UI can run the replacement flow. */
  async focus(goalId: string, replacementGoalId: string | null): Promise<boolean> {
    const generation = this.state.accountGeneration
    if (generation === null) return false
    try {
      await this.deps.post(
        `/v1/goals/${goalId}/focus`,
        { replacement_goal_id: replacementGoalId, focus_rank: null },
        {
          headers: {
            'Idempotency-Key': `goal-focus:${goalId}:${this.deps.uuid().toLowerCase()}`,
            'X-Account-Generation': generation
          }
        }
      )
    } catch (e) {
      if (httpStatus(e) === 409 && replacementGoalId === null) {
        this.setState({ focusReplacementGoalId: goalId, error: CHOOSE_REPLACEMENT })
      } else {
        this.setState({ error: GOALS_UNAVAILABLE })
      }
      return false
    }
    this.setState({ focusReplacementGoalId: null, error: null })
    await this.reload()
    return true
  }

  async unfocus(goalId: string): Promise<boolean> {
    const generation = this.state.accountGeneration
    if (generation === null) return false
    return this.goalMutation(() =>
      this.deps
        .del(`/v1/goals/${goalId}/focus`, {
          headers: {
            'Idempotency-Key': `goal-unfocus:${goalId}:${this.deps.uuid().toLowerCase()}`,
            'X-Account-Generation': generation
          }
        })
        .then(() => undefined)
    )
  }

  /** Pause, achieve, or abandon. The relationship disposition is always
   *  'retain' from this surface (mac parity): ended goals keep their threads. */
  async transition(goalId: string, status: GoalLifecycleTarget): Promise<boolean> {
    const generation = this.state.accountGeneration
    if (generation === null) return false
    return this.goalMutation(() =>
      this.deps
        .post(
          `/v1/goals/${goalId}/lifecycle`,
          { status, relationship_disposition: 'retain' },
          {
            headers: {
              'Idempotency-Key': `goal-lifecycle:${goalId}:${status}:${this.deps.uuid().toLowerCase()}`,
              'X-Account-Generation': generation
            }
          }
        )
        .then(() => undefined)
    )
  }

  async loadGoalDetail(goalId: string): Promise<GoalDetail | null> {
    this.setState({ goalDetailError: null })
    try {
      const res = await this.deps.get(`/v1/goals/${goalId}/detail`)
      const detail = readGoalDetail(res.data)
      this.setState({ selectedGoalDetail: detail })
      return detail
    } catch {
      this.setState({ selectedGoalDetail: null, goalDetailError: GOAL_UNAVAILABLE })
      return null
    }
  }

  clearGoalDetail(): void {
    this.setState({ selectedGoalDetail: null, goalDetailError: null })
  }

  /** Open a recommendation by row id (mac parity: openRecommendation). When
   *  the id is not in the current rows, one full load() runs first — the id may
   *  be stale from a notification or an automation call. The handler performs
   *  the actual navigation and reports success; do_now feedback records ONLY
   *  after a successful open, and a missing row or absent handler surfaces the
   *  review-target-unavailable error instead of failing silently. */
  async openRecommendation(
    id: string,
    handler: (row: ProjectedRecommendation) => Promise<boolean> | boolean
  ): Promise<boolean> {
    let row = this.state.recommendations.find((r) => r.id === id)
    if (!row) {
      await this.load()
      row = this.state.recommendations.find((r) => r.id === id)
    }
    if (!row) {
      this.setState({ error: TARGET_UNAVAILABLE })
      return false
    }
    const opened = await handler(row)
    if (!opened) return false
    // Mac parity: a successful open binds the most recent learnable screen
    // context to this recommendation's subject (main-side binding service,
    // 90-second window). Optional-chained: absent bridge = no-op.
    void window.omi?.directorBindRecentContext?.({
      kind: row.wire.subjectKind,
      id: row.wire.subjectId,
      workstreamID: row.wire.destinationWorkstreamId ?? null
    })
    await this.recordPrimaryAction(row)
    return true
  }

  /** POST /v1/task-intelligence/outcomes. Declared-unused parity with mac:
   *  both DashboardIntelligenceClient implementations carry this call and no
   *  desktop call site constructs an OutcomeCreate yet; the wire shape is
   *  {attribution_chain_id, outcome_code, subject_id, subject_kind}. Kept so
   *  outcome wiring lands as a call-site change, not a client change. */
  async recordTaskOutcome(outcome: {
    attributionChainId: string
    outcomeCode:
      | 'task_completed'
      | 'artifact_approved'
      | 'artifact_delivered'
      | 'decision_resolved'
      | 'agent_output_applied'
      | 'workstream_advanced'
    subjectKind: FeedbackSubjectKind
    subjectId: string
  }): Promise<boolean> {
    const generation = this.state.accountGeneration
    if (generation === null) return false
    try {
      await this.deps.post(
        '/v1/task-intelligence/outcomes',
        {
          attribution_chain_id: outcome.attributionChainId,
          outcome_code: outcome.outcomeCode,
          subject_kind: outcome.subjectKind,
          subject_id: outcome.subjectId
        },
        {
          headers: {
            'Idempotency-Key': `wmn-outcome:${outcome.attributionChainId}:${outcome.outcomeCode}`,
            'X-Account-Generation': generation
          }
        }
      )
      return true
    } catch {
      return false
    }
  }

  clearFocusReplacement(): void {
    this.setState({ focusReplacementGoalId: null })
  }
}

/** The app-wide singleton the Home hub binds to. Tests construct their own. */
export const dashboardIntelligence = new DashboardIntelligenceStore()
