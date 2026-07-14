// Desktop action queue — Windows port of the macOS agent runtime's
// desktop-action-queue.ts (desktop/macos/agent/src/runtime/desktop-action-queue.ts).
//
// A pure projection: it folds pending dispatches, failed/stale runs, undelivered
// artifacts, and pending candidates into one ranked "what needs attention" list,
// with attention overrides suppressing individual subjects. No I/O, no store —
// the kernel reads the rows and hands them in.
//
// The intent router consumes this (a pending dispatch outranks any other route),
// which is why it lands with the kernel rather than with the control plane.

import type {
  DesktopArtifactDeliveryStatus,
  DesktopCandidateStatus,
  DesktopDispatchKind,
  DesktopDispatchStatus,
  RunStatus
} from './types'

export type DesktopActionQueueItemKind =
  | 'dispatch'
  | 'failed_run'
  | 'artifact_delivery'
  | 'stale_run'
  | 'candidate_review'
  | 'reusable_session'

export interface DesktopActionQueueItem {
  itemId: string
  kind: DesktopActionQueueItemKind
  subjectKind: string
  subjectId: string
  ownerId: string
  title: string
  priority: number
  rank: number
  createdAtMs: number
  sourceSessionId?: string | null
  sourceRunId?: string | null
  dispatchKind?: DesktopDispatchKind
  reason: string
}

export interface QueueDispatchInput {
  dispatchId: string
  ownerId: string
  kind: DesktopDispatchKind
  status: DesktopDispatchStatus
  title: string
  priority: number
  createdAtMs: number
  expiresAtMs?: number | null
  sourceSessionId?: string | null
  sourceRunId?: string | null
}

export interface QueueRunInput {
  runId: string
  sessionId: string
  ownerId: string
  status: RunStatus
  title?: string | null
  goalText?: string | null
  completedAtMs?: number | null
  updatedAtMs: number
  createdAtMs: number
  visibleUserGoal?: boolean
  reusable?: boolean
}

export interface QueueArtifactDeliveryInput {
  deliveryId: string
  artifactId: string
  ownerId: string
  sourceSessionId: string
  sourceRunId?: string | null
  deliveryStatus: DesktopArtifactDeliveryStatus
  reviewStatus?: string
  createdAtMs: number
  updatedAtMs: number
  targetKind: string
}

export interface QueueCandidateInput {
  candidateId: string
  ownerId: string
  kind: 'memory_candidate' | 'task_candidate'
  status: DesktopCandidateStatus
  createdAtMs: number
  sourceSessionId?: string | null
  sourceRunId?: string | null
}

export interface QueueOverrideInput {
  ownerId: string
  subjectKind: string
  subjectId: string
  hiddenUntilMs?: number | null
  dismissedAtMs?: number | null
}

export interface BuildDesktopActionQueueInput {
  nowMs: number
  staleAfterMs?: number
  dispatches?: readonly QueueDispatchInput[]
  runs?: readonly QueueRunInput[]
  runItemLimit?: number
  runSuppressionContext?: readonly QueueRunInput[]
  artifactDeliveries?: readonly QueueArtifactDeliveryInput[]
  candidates?: readonly QueueCandidateInput[]
  overrides?: readonly QueueOverrideInput[]
}

function isSuppressed(
  item: DesktopActionQueueItem,
  overrides: readonly QueueOverrideInput[],
  nowMs: number
): boolean {
  return overrides.some((override) => {
    if (
      override.ownerId !== item.ownerId ||
      override.subjectKind !== item.subjectKind ||
      override.subjectId !== item.subjectId
    ) {
      return false
    }
    if (override.dismissedAtMs != null) return true
    return override.hiddenUntilMs != null && override.hiddenUntilMs > nowMs
  })
}

function item(input: Omit<DesktopActionQueueItem, 'itemId'>): DesktopActionQueueItem {
  return { ...input, itemId: `${input.kind}:${input.subjectKind}:${input.subjectId}` }
}

export function buildDesktopActionQueue(
  input: BuildDesktopActionQueueInput
): DesktopActionQueueItem[] {
  const nowMs = input.nowMs
  const staleAfterMs = input.staleAfterMs ?? 30 * 60 * 1000
  const items: DesktopActionQueueItem[] = []
  const runItems: DesktopActionQueueItem[] = []
  const reusableSessions = new Map<string, QueueRunInput>()
  const suppressionRuns = input.runSuppressionContext ?? input.runs ?? []
  const successfulVisibleRuns = suppressionRuns.filter(
    (run) => run.status === 'succeeded' && run.visibleUserGoal !== false
  )

  for (const dispatch of input.dispatches ?? []) {
    if (dispatch.status !== 'pending') continue
    if (dispatch.expiresAtMs != null && dispatch.expiresAtMs <= nowMs) continue
    items.push(
      item({
        kind: 'dispatch',
        subjectKind: 'dispatch',
        subjectId: dispatch.dispatchId,
        ownerId: dispatch.ownerId,
        title: dispatch.title,
        priority: 100 + dispatch.priority,
        rank: 1,
        createdAtMs: dispatch.createdAtMs,
        sourceSessionId: dispatch.sourceSessionId ?? null,
        sourceRunId: dispatch.sourceRunId ?? null,
        dispatchKind: dispatch.kind,
        reason: 'Pending dispatch blocks local coordinator progress.'
      })
    )
  }

  for (const run of input.runs ?? []) {
    if ((run.status === 'failed' || run.status === 'orphaned') && run.visibleUserGoal !== false) {
      if (isCoveredByNewerSuccessfulRun(run, successfulVisibleRuns)) continue
      runItems.push(
        item({
          kind: 'failed_run',
          subjectKind: 'run',
          subjectId: run.runId,
          ownerId: run.ownerId,
          title: run.title ?? 'Recover failed agent run',
          priority: 90,
          rank: 2,
          createdAtMs: run.updatedAtMs,
          sourceSessionId: run.sessionId,
          sourceRunId: run.runId,
          reason: `${run.status} run tied to a visible user goal needs recovery.`
        })
      )
    } else if (
      ['queued', 'starting', 'running', 'waiting_input', 'waiting_approval'].includes(run.status) &&
      nowMs - run.updatedAtMs >= staleAfterMs
    ) {
      runItems.push(
        item({
          kind: 'stale_run',
          subjectKind: 'run',
          subjectId: run.runId,
          ownerId: run.ownerId,
          title: run.title ?? 'Check stale agent run',
          priority: 70,
          rank: 4,
          createdAtMs: run.updatedAtMs,
          sourceSessionId: run.sessionId,
          sourceRunId: run.runId,
          reason: 'Active run has not advanced within the stale threshold.'
        })
      )
    } else if (run.reusable === true) {
      const existing = reusableSessions.get(run.sessionId)
      if (!existing || run.updatedAtMs > existing.updatedAtMs) {
        reusableSessions.set(run.sessionId, run)
      }
    }
  }

  for (const run of reusableSessions.values()) {
    runItems.push(
      item({
        kind: 'reusable_session',
        subjectKind: 'session',
        subjectId: run.sessionId,
        ownerId: run.ownerId,
        title: run.title ?? 'Reusable agent session',
        priority: 20,
        rank: 7,
        createdAtMs: run.updatedAtMs,
        sourceSessionId: run.sessionId,
        sourceRunId: run.runId,
        reason: 'Existing session may be relevant to the current request.'
      })
    )
  }
  const visibleRunItems = runItems
    .filter((queueItem) => !isSuppressed(queueItem, input.overrides ?? [], nowMs))
    .sort(compareQueueItems)
    .slice(0, input.runItemLimit ?? runItems.length)
  items.push(...visibleRunItems)

  for (const delivery of input.artifactDeliveries ?? []) {
    if (!['pending', 'failed', 'retrying'].includes(delivery.deliveryStatus)) continue
    items.push(
      item({
        kind: 'artifact_delivery',
        subjectKind: 'artifact_delivery',
        subjectId: delivery.deliveryId,
        ownerId: delivery.ownerId,
        title: `Review ${delivery.targetKind} artifact delivery`,
        priority: delivery.deliveryStatus === 'failed' ? 85 : 80,
        rank: 3,
        createdAtMs: delivery.updatedAtMs,
        sourceSessionId: delivery.sourceSessionId,
        sourceRunId: delivery.sourceRunId ?? null,
        reason: 'Completed run has an undelivered artifact or result.'
      })
    )
  }

  for (const candidate of input.candidates ?? []) {
    if (candidate.status !== 'pending') continue
    items.push(
      item({
        kind: 'candidate_review',
        subjectKind: candidate.kind,
        subjectId: candidate.candidateId,
        ownerId: candidate.ownerId,
        title:
          candidate.kind === 'memory_candidate'
            ? 'Review memory candidate'
            : 'Review task candidate',
        priority: 60,
        rank: 5,
        createdAtMs: candidate.createdAtMs,
        sourceSessionId: candidate.sourceSessionId ?? null,
        sourceRunId: candidate.sourceRunId ?? null,
        reason: 'Candidate mutation requires explicit review before canonical state changes.'
      })
    )
  }

  return items
    .filter((queueItem) => !isSuppressed(queueItem, input.overrides ?? [], nowMs))
    .sort(compareQueueItems)
}

function compareQueueItems(left: DesktopActionQueueItem, right: DesktopActionQueueItem): number {
  return (
    left.rank - right.rank || right.priority - left.priority || right.createdAtMs - left.createdAtMs
  )
}

function isCoveredByNewerSuccessfulRun(
  run: QueueRunInput,
  successfulRuns: readonly QueueRunInput[]
): boolean {
  return successfulRuns.some((candidate) => {
    if (candidate.ownerId !== run.ownerId) return false
    if (runRecencyMs(candidate) <= runRecencyMs(run)) return false
    return visibleGoalsOverlap(run, candidate)
  })
}

function runRecencyMs(run: QueueRunInput): number {
  return run.completedAtMs ?? run.createdAtMs
}

function visibleGoalsOverlap(left: QueueRunInput, right: QueueRunInput): boolean {
  const leftTokens = visibleGoalTokens(left)
  const rightTokens = visibleGoalTokens(right)
  if (leftTokens.size === 0 || rightTokens.size === 0) return false

  let overlap = 0
  for (const token of leftTokens) {
    if (rightTokens.has(token)) overlap += 1
  }
  return overlap >= 2
}

function visibleGoalTokens(run: QueueRunInput): Set<string> {
  const text = `${run.title ?? ''} ${run.goalText ?? ''}`.toLowerCase()
  const tokens = new Set<string>()
  for (const raw of text.match(/[a-z0-9]+/g) ?? []) {
    const token = normalizeGoalToken(raw)
    if (token.length >= 4 && !STOPWORDS.has(token)) {
      tokens.add(token)
    }
  }
  return tokens
}

function normalizeGoalToken(token: string): string {
  if (token === 'memories') return 'memory'
  if (token === 'storyline' || token === 'stories') return 'story'
  if (token.endsWith('ies') && token.length > 5) return `${token.slice(0, -3)}y`
  if (token.endsWith('ing') && token.length > 6) return token.slice(0, -3)
  if (token.endsWith('ed') && token.length > 5) return token.slice(0, -2)
  if (token.endsWith('s') && token.length > 5) return token.slice(0, -1)
  return token
}

const STOPWORDS = new Set([
  'agent',
  'background',
  'based',
  'come',
  'create',
  'from',
  'have',
  'look',
  'once',
  'recent',
  'retry',
  'search',
  'short',
  'subagent',
  'through',
  'with'
])
