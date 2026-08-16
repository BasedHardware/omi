// Wire types for the task-intelligence loop (mac parity: OmiApi.generated.swift
// structs consumed by DashboardIntelligenceStore). Field names are the backend's
// snake_case, verbatim from backend/models/task_recommendation.py and
// backend/models/goal.py. Enums decode leniently: an unknown wire string maps to
// '_unknown' instead of throwing, mirroring the generated Swift client's
// `__unknown__` cases, and rows with unknown subject kinds are then dropped by
// the projection rules rather than failing the whole payload.

export type RecommendationSubjectKind =
  'candidate' | 'task' | 'workstream' | 'artifact' | 'decision' | 'agent_open_loop' | '_unknown'

export type FeedbackSubjectKind =
  'candidate' | 'task' | 'workstream' | 'artifact' | 'decision' | '_unknown'

export type FeedbackAction =
  'do_now' | 'later' | 'dismiss' | 'accept_candidate' | 'edit' | 'complete'

export type FeedbackReason = 'already_handled' | 'not_mine' | 'not_useful'

export type WorkflowMode = 'off' | 'shadow' | 'write' | 'read' | '_unknown'

export type GoalStatus = 'background' | 'focused' | 'paused' | 'achieved' | 'abandoned' | '_unknown'

/** Terminal lifecycle targets the backend accepts (GoalLifecycleRequest rejects
 *  everything else). */
export type GoalLifecycleTarget = 'paused' | 'achieved' | 'abandoned'

const RECOMMENDATION_SUBJECT_KINDS: ReadonlySet<string> = new Set([
  'candidate',
  'task',
  'workstream',
  'artifact',
  'decision',
  'agent_open_loop'
])

const FEEDBACK_SUBJECT_KINDS: ReadonlySet<string> = new Set([
  'candidate',
  'task',
  'workstream',
  'artifact',
  'decision'
])

const WORKFLOW_MODES: ReadonlySet<string> = new Set(['off', 'shadow', 'write', 'read'])

const GOAL_STATUSES: ReadonlySet<string> = new Set([
  'background',
  'focused',
  'paused',
  'achieved',
  'abandoned'
])

export function readRecommendationSubjectKind(value: unknown): RecommendationSubjectKind {
  return typeof value === 'string' && RECOMMENDATION_SUBJECT_KINDS.has(value)
    ? (value as RecommendationSubjectKind)
    : '_unknown'
}

export function readFeedbackSubjectKind(value: unknown): FeedbackSubjectKind {
  return typeof value === 'string' && FEEDBACK_SUBJECT_KINDS.has(value)
    ? (value as FeedbackSubjectKind)
    : '_unknown'
}

export function readWorkflowMode(value: unknown): WorkflowMode {
  return typeof value === 'string' && WORKFLOW_MODES.has(value)
    ? (value as WorkflowMode)
    : '_unknown'
}

export function readGoalStatus(value: unknown): GoalStatus {
  return typeof value === 'string' && GOAL_STATUSES.has(value) ? (value as GoalStatus) : '_unknown'
}

/** GET /v1/candidates/control (TaskWorkflowControl). */
export type WorkflowControl = {
  workflowMode: WorkflowMode
  accountGeneration: number
}

export function readWorkflowControl(data: unknown): WorkflowControl {
  const raw = (data ?? {}) as { workflow_mode?: unknown; account_generation?: unknown }
  return {
    workflowMode: readWorkflowMode(raw.workflow_mode),
    accountGeneration: typeof raw.account_generation === 'number' ? raw.account_generation : 0
  }
}

/** One row of the What Matters Now projection (backend Recommendation model).
 *  The server registers the presentation intervention during evaluation, so
 *  every row already carries its intervention_id; feedback threads it directly
 *  and the client never registers interventions for this surface. */
export type WmnRecommendation = {
  interventionId: string
  outputVersion: string
  subjectKind: RecommendationSubjectKind
  subjectId: string
  feedbackSubjectKind: FeedbackSubjectKind
  feedbackSubjectId: string
  destinationTaskId: string | null
  destinationWorkstreamId: string | null
  headline: string
  whyNow: string
  contextLabel: string | null
  recommendedAction: string
  alternativeAction: string | null
  evidencePreview: string
  dedupeKey: string
  expiresAt: string
}

export type WmnProjection = {
  evaluationId: string
  outputVersion: string
  materialVersion: string
  generatedAt: string
  expiresAt: string
  recommendations: WmnRecommendation[]
}

function readString(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null
}

export function readWmnProjection(data: unknown): WmnProjection | null {
  const raw = data as Record<string, unknown> | null | undefined
  if (!raw || typeof raw !== 'object') return null
  const evaluationId = readString(raw.evaluation_id)
  const outputVersion = readString(raw.output_version)
  const expiresAt = readString(raw.expires_at)
  if (!evaluationId || !outputVersion || !expiresAt) return null
  const rows = Array.isArray(raw.recommendations) ? raw.recommendations : []
  const recommendations: WmnRecommendation[] = []
  for (const item of rows) {
    const r = item as Record<string, unknown> | null
    if (!r || typeof r !== 'object') continue
    const interventionId = readString(r.intervention_id)
    const rowOutputVersion = readString(r.output_version)
    const subjectId = readString(r.subject_id)
    const feedbackSubjectId = readString(r.feedback_subject_id)
    const headline = readString(r.headline)
    const dedupeKey = readString(r.dedupe_key)
    const rowExpiresAt = readString(r.expires_at)
    if (
      !interventionId ||
      !rowOutputVersion ||
      !subjectId ||
      !feedbackSubjectId ||
      !headline ||
      !dedupeKey ||
      !rowExpiresAt
    ) {
      continue
    }
    recommendations.push({
      interventionId,
      outputVersion: rowOutputVersion,
      subjectKind: readRecommendationSubjectKind(r.subject_kind),
      subjectId,
      feedbackSubjectKind: readFeedbackSubjectKind(r.feedback_subject_kind),
      feedbackSubjectId,
      destinationTaskId: readString(r.destination_task_id),
      destinationWorkstreamId: readString(r.destination_workstream_id),
      headline,
      whyNow: readString(r.why_now) ?? '',
      contextLabel: readString(r.goal_or_workstream_label),
      recommendedAction: readString(r.recommended_action) ?? '',
      alternativeAction: readString(r.alternative_action),
      evidencePreview: readString(r.evidence_preview) ?? '',
      dedupeKey,
      expiresAt: rowExpiresAt
    })
  }
  return {
    evaluationId,
    outputVersion,
    materialVersion: readString(raw.material_version) ?? '',
    generatedAt: readString(raw.generated_at) ?? '',
    expiresAt,
    recommendations
  }
}

/** Backend GoalResponse, the subset the home surfaces consume. */
export type CanonicalGoal = {
  goalId: string
  title: string
  desiredOutcome: string
  whyItMatters: string | null
  successCriteria: string[]
  status: GoalStatus
  focusRank: number | null
  isActive: boolean
  updatedAt: string
  currentValue: number | null
  targetValue: number | null
  unit: string | null
}

export function readCanonicalGoal(data: unknown): CanonicalGoal | null {
  const raw = data as Record<string, unknown> | null | undefined
  if (!raw || typeof raw !== 'object') return null
  const goalId = readString(raw.goal_id) ?? readString(raw.id)
  const title = readString(raw.title)
  if (!goalId || !title) return null
  const criteria = Array.isArray(raw.success_criteria)
    ? raw.success_criteria.filter((c): c is string => typeof c === 'string')
    : []
  return {
    goalId,
    title,
    desiredOutcome: readString(raw.desired_outcome) ?? '',
    whyItMatters: readString(raw.why_it_matters),
    successCriteria: criteria,
    status: readGoalStatus(raw.status),
    focusRank: typeof raw.focus_rank === 'number' ? raw.focus_rank : null,
    isActive: raw.is_active !== false,
    updatedAt: readString(raw.updated_at) ?? '',
    currentValue: typeof raw.current_value === 'number' ? raw.current_value : null,
    targetValue: typeof raw.target_value === 'number' ? raw.target_value : null,
    unit: readString(raw.unit)
  }
}

/** GET /v1/goals/{id}/detail (GoalDetailProjection): {goal, tasks, active_threads,
 *  progress_events}. Tasks and threads keep only what the detail sheet renders. */
export type GoalDetail = {
  goal: CanonicalGoal
  tasks: { id: string; description: string; completed: boolean }[]
  activeThreads: { workstreamId: string; summary: string }[]
  progressEvents: { summary: string }[]
}

export function readGoalDetail(data: unknown): GoalDetail | null {
  const raw = data as Record<string, unknown> | null | undefined
  if (!raw || typeof raw !== 'object') return null
  const goal = readCanonicalGoal(raw.goal)
  if (!goal) return null
  const tasks = Array.isArray(raw.tasks)
    ? raw.tasks.flatMap((t) => {
        const row = t as Record<string, unknown> | null
        const id = row ? readString(row.id) : null
        if (!row || !id) return []
        return [
          {
            id,
            description: readString(row.description) ?? '',
            completed: row.completed === true
          }
        ]
      })
    : []
  const activeThreads = Array.isArray(raw.active_threads)
    ? raw.active_threads.flatMap((t) => {
        const row = t as Record<string, unknown> | null
        const workstreamId = row ? readString(row.workstream_id) : null
        if (!row || !workstreamId) return []
        const summary =
          readString(row.current_state_summary) ?? readString(row.objective) ?? workstreamId
        return [{ workstreamId, summary }]
      })
    : []
  const progressEvents = Array.isArray(raw.progress_events)
    ? raw.progress_events.flatMap((e) => {
        const row = e as Record<string, unknown> | null
        const summary = row ? readString(row.summary) : null
        return summary ? [{ summary }] : []
      })
    : []
  return { goal, tasks, activeThreads, progressEvents }
}

/** POST /v1/task-intelligence/feedback request body (FeedbackCreate). Wire keys
 *  stay snake_case; context_snapshot_hash is always null from this surface,
 *  matching mac's DashboardIntelligenceStore. */
export type FeedbackCreateBody = {
  action: FeedbackAction
  subject_kind: FeedbackSubjectKind
  subject_id: string
  intervention_id: string
  reason: FeedbackReason | null
  later_until: string | null
  context_snapshot_hash: null
}
