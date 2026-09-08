// AgentRuntimeKernel — the top of the kernel class chain and the module every
// caller imports.
//
//   KernelCore -> KernelRuns -> KernelArtifacts -> KernelSessions -> AgentRuntimeKernel
//
// Windows port of the macOS agent runtime's kernel.ts + the coordinator methods
// of kernel-coordinator.ts (desktop/macos/agent/src/runtime/). On macOS
// `AgentRuntimeKernel` IS the coordinator class; this port carries only the
// coordinator methods the run path actually depends on:
//
//   - persistDesktopContextPacket / routeDesktopIntent — called by turnContext on
//     ordinary chat turns through KernelCore's service host, so the class chain
//     does not resolve without them.
//   - listDesktopActionQueue — routeDesktopIntent's input (a pending dispatch
//     outranks every other route).
//   - the attention-override read/write the queue projection reads.
//
// The coordinator methods the agent control plane calls (awareness snapshot,
// open loops, dispatch create/resolve) live here too — see ./controlTools.
//
// Deliberately NOT ported here:
//   - workstream continuity — owned by the workstream/proactive track. The one
//     piece the control plane needs, `buildDesktopOpenLoopSnapshot`, is a pure
//     projection of the action queue and is ported standalone (below) rather
//     than pulling in that module.
//   - the JSONL/stdio transport — Windows runs the kernel in-process in Electron
//     main, so there is no subprocess protocol at all.

import { KernelSessions } from './kernelSessions'
import { buildDesktopActionQueue, type DesktopActionQueueItem } from './desktopActionQueue'
import { buildDesktopContextPacket, type BuiltDesktopContextPacket } from './desktopContextPacket'
import {
  routeDesktopIntent,
  type DesktopIntentRoute,
  type DesktopIntentRouteInput
} from './desktopIntentRouter'
import {
  boundedLimit,
  deliveryToQueueInput,
  dispatchToQueueInput,
  memoryCandidateToQueueInput,
  overrideToQueueInput,
  parseJsonObject,
  runFromRow,
  taskCandidateToQueueInput
} from './kernelSupport'
import type {
  AgentGrant,
  DesktopAttentionOverride,
  DesktopCoordinatorDispatch,
  NewDesktopContextPacket,
  NewDesktopCoordinatorDispatch
} from './types'
import type {
  DesktopActionQueueInput,
  DesktopAwarenessSnapshot,
  DesktopAwarenessSnapshotInput,
  DesktopContextPacketPersistInput,
  ResolveDesktopDispatchInput,
  ResolveDesktopDispatchResult,
  SetDesktopAttentionOverrideInput
} from './kernelTypes'

/** Default TTL for a derived open-loop snapshot. Matches macOS. */
const DEFAULT_OPEN_LOOP_TTL_MS = 5 * 60 * 1000

/** The action-queue item kinds that count as an unresolved coordinator loop. */
const OPEN_LOOP_ITEM_KINDS = [
  'dispatch',
  'failed_run',
  'artifact_delivery',
  'stale_run',
  'candidate_review'
]

export interface DesktopOpenLoopsInput {
  ownerId?: string
  ttlMs?: number
  nowMs?: number
  limit?: number
}

export interface DesktopOpenLoopSnapshot {
  ownerId: string
  sourceRuntimeId: string
  deviceScoped: true
  generatedAtMs: number
  expiresAtMs: number
  loops: Array<{
    itemKind: DesktopActionQueueItem['kind']
    subjectKind: string
    subjectId: string
    title: string
    reason: string
    sourceSessionId: string | null
    sourceRunId: string | null
  }>
}

/** Owner used when a caller does not scope the request. Matches macOS. */
const DEFAULT_OWNER_ID = 'desktop-local-user'

export class AgentRuntimeKernel extends KernelSessions {
  persistDesktopContextPacket(input: DesktopContextPacketPersistInput): BuiltDesktopContextPacket {
    const ownerId = input.ownerId ?? DEFAULT_OWNER_ID
    this.validateSensitiveContextDispatches({ ...input, ownerId })
    const built = buildDesktopContextPacket({ ...input, ownerId })
    this.withTransaction(() => {
      this.store.insertDesktopContextPacket({
        ...(built.packet as unknown as NewDesktopContextPacket),
        packetJson: JSON.stringify(built.packet.packetJson),
        redactedPreviewJson: JSON.stringify(built.packet.redactedPreviewJson)
      })
      for (const accessLog of built.accessLogs) {
        this.store.insertDesktopContextAccessLog(accessLog)
      }
    })
    return built
  }

  routeDesktopIntent(
    input: Omit<DesktopIntentRouteInput, 'nowMs' | 'actionQueue' | 'sessionCandidates'> & {
      ownerId?: string
    }
  ): DesktopIntentRoute {
    const ownerId = input.ownerId ?? DEFAULT_OWNER_ID
    return routeDesktopIntent({
      ...input,
      nowMs: Date.now(),
      actionQueue: this.listDesktopActionQueue({ ownerId, limit: 50 }),
      sessionCandidates: this.desktopIntentSessionCandidates(
        ownerId,
        input.surfaceKind,
        input.taskId ?? null
      )
    })
  }

  listDesktopActionQueue(input: DesktopActionQueueInput): DesktopActionQueueItem[] {
    const ownerId = input.ownerId ?? DEFAULT_OWNER_ID
    const limit = boundedLimit(input.limit, 50, 200)
    const nowMs = Date.now()
    const runWindow = this.readDesktopQueueRuns(ownerId, Math.max(limit * 5, 200))
    const queue = buildDesktopActionQueue({
      nowMs,
      staleAfterMs: input.staleAfterMs,
      dispatches: this.readDesktopDispatches(ownerId, limit).map(dispatchToQueueInput),
      runs: runWindow,
      runItemLimit: limit,
      runSuppressionContext: runWindow,
      artifactDeliveries: this.readDesktopArtifactDeliveries(ownerId, limit).map(
        deliveryToQueueInput
      ),
      candidates: [
        ...this.readDesktopMemoryCandidates(ownerId, limit).map(memoryCandidateToQueueInput),
        ...this.readDesktopTaskCandidates(ownerId, limit).map(taskCandidateToQueueInput)
      ],
      overrides: this.readDesktopAttentionOverrides(ownerId).map(overrideToQueueInput)
    })
    return queue.slice(0, limit)
  }

  /**
   * Local coordinator snapshot: sessions, runs, dispatches, deliveries,
   * candidates, the derived action queue, and runtime health. Metadata and local
   * state summaries only — never transcripts or screenshot bytes.
   */
  buildDesktopAwarenessSnapshot(input: DesktopAwarenessSnapshotInput): DesktopAwarenessSnapshot {
    const ownerId = input.ownerId ?? DEFAULT_OWNER_ID
    const limit = boundedLimit(input.limit, 50, 200)
    const sessions = this.listSessions({ ownerId, limit })
    const runs = this.store
      .allRows(
        `SELECT r.*
         FROM runs r
         JOIN sessions s ON s.session_id = r.session_id
         WHERE s.owner_id = ?
         ORDER BY r.updated_at_ms DESC
         LIMIT ?`,
        [ownerId, limit]
      )
      .map(runFromRow)
    return {
      ownerId,
      generatedAtMs: Date.now(),
      sessions,
      runs,
      dispatches: this.readDesktopDispatches(ownerId, limit),
      artifactDeliveries: this.readDesktopArtifactDeliveries(ownerId, limit),
      memoryCandidates: this.readDesktopMemoryCandidates(ownerId, limit),
      taskCandidates: this.readDesktopTaskCandidates(ownerId, limit),
      actionQueue: this.listDesktopActionQueue({ ownerId, limit }),
      runtime: {
        activeExecutionCount: this.activeExecutions.size,
        registeredAdapters: this.registry.adapterIds()
      }
    }
  }

  /**
   * Unresolved coordinator loops, derived from the action queue. A pure
   * projection — nothing is persisted.
   *
   * macOS routes this through `buildWorkstreamOpenLoopSnapshot` in
   * workstream-continuity.ts and decorates each loop with the `workstreamId` of
   * its source session. Windows has no workstream sessions, so that lookup would
   * be `null` for every row; the field is omitted rather than always-null. The
   * loop selection, TTL, and shape are otherwise the macOS ones.
   */
  getDesktopOpenLoops(input: DesktopOpenLoopsInput = {}): DesktopOpenLoopSnapshot {
    const ownerId = input.ownerId ?? DEFAULT_OWNER_ID
    const nowMs = input.nowMs ?? Date.now()
    const ttlMs = input.ttlMs ?? DEFAULT_OPEN_LOOP_TTL_MS
    if (!Number.isFinite(ttlMs) || ttlMs <= 0) {
      throw new Error('Open-loop snapshot TTL must be positive')
    }
    return {
      ownerId,
      sourceRuntimeId: this.runtimeNodeId,
      deviceScoped: true,
      generatedAtMs: nowMs,
      expiresAtMs: nowMs + ttlMs,
      loops: this.listDesktopActionQueue({ ownerId, limit: input.limit })
        .filter((item) => OPEN_LOOP_ITEM_KINDS.includes(item.kind))
        .map((item) => ({
          itemKind: item.kind,
          subjectKind: item.subjectKind,
          subjectId: item.subjectId,
          title: item.title,
          reason: item.reason,
          sourceSessionId: item.sourceSessionId ?? null,
          sourceRunId: item.sourceRunId ?? null
        }))
    }
  }

  createDesktopDispatch(input: NewDesktopCoordinatorDispatch): DesktopCoordinatorDispatch {
    return this.store.insertDesktopDispatch(input)
  }

  /**
   * Resolve or cancel a pending dispatch, optionally minting the scoped grant the
   * user's approval authorizes. Grant creation and the ordered `approval.resolved`
   * event are appended in the SAME transaction as the resolution — a grant can
   * never exist without the approval record that justifies it.
   *
   * Every guard below is a fail-closed check on that authorization: only an
   * `approval` dispatch may mint a grant, only an explicit `allow` resolution, and
   * the grant's capability/operation/resource must each match what the user was
   * actually asked to approve. This is what stops a resolved dispatch for one
   * capability from being redeemed as a grant for another.
   */
  resolveDesktopDispatch(
    dispatchId: string,
    input: ResolveDesktopDispatchInput
  ): ResolveDesktopDispatchResult {
    return this.withTransaction(() => {
      const dispatch = this.store.resolveDesktopDispatch(dispatchId, input)
      let grant: AgentGrant | null = null
      if (input.status === 'resolved' && input.grant && input.grant.effect === 'allow') {
        const resolution = parseJsonObject(input.resolutionJson ?? '{}') as Record<string, unknown>
        if (dispatch.kind !== 'approval') {
          throw new Error('Only approval dispatches can mint grants')
        }
        if (resolution.decision !== 'allow') {
          throw new Error('Resolved dispatch grants require an allow resolution')
        }
        if (!dispatch.capability || input.grant.capability !== dispatch.capability) {
          throw new Error('Resolved dispatch grant capability must match the approval request')
        }
        if (!dispatch.operation || input.grant.operation !== dispatch.operation) {
          throw new Error('Resolved dispatch grant operation must match the approval request')
        }
        if (!dispatch.resourceRef || input.grant.resourcePattern !== dispatch.resourceRef) {
          throw new Error('Resolved dispatch grant resource must match the approval request')
        }
        if (!Number.isFinite(input.grant.expiresAtMs)) {
          throw new Error('Resolved dispatch grants require a finite expiry')
        }
        const sessionId = input.grant.sessionId ?? dispatch.sourceSessionId
        if (!sessionId) {
          throw new Error('Resolved dispatch grants require a session scope')
        }
        this.assertSessionOwner(this.readSession(sessionId), input.ownerId)
        grant = this.store.insertGrant({
          ...input.grant,
          sessionId,
          runId: input.grant.runId ?? dispatch.sourceRunId,
          source: input.grant.source ?? 'user'
        })
      }
      const event = dispatch.sourceSessionId
        ? this.appendEvent({
            sessionId: dispatch.sourceSessionId,
            runId: dispatch.sourceRunId,
            attemptId: dispatch.sourceAttemptId,
            type: 'approval.resolved',
            payload: {
              dispatchId: dispatch.dispatchId,
              status: dispatch.status,
              resolvedBy: dispatch.resolvedBy,
              resolution: parseJsonObject(dispatch.resolutionJson ?? '{}'),
              grantId: grant?.grantId ?? null
            }
          })
        : null
      return { dispatch, grant, event }
    })
  }

  listDesktopAttentionOverrides(ownerId: string): DesktopAttentionOverride[] {
    return this.readDesktopAttentionOverrides(ownerId)
  }

  setDesktopAttentionOverride(input: SetDesktopAttentionOverrideInput): DesktopAttentionOverride {
    return this.store.upsertDesktopAttentionOverride({
      ownerId: input.ownerId,
      subjectKind: input.subjectKind,
      subjectId: input.subjectId,
      dismissedAtMs: input.dismissedAtMs ?? null,
      hiddenUntilMs: input.hiddenUntilMs ?? null,
      reason: input.reason ?? null
    })
  }
}

export { StaleAdapterBindingError } from './kernelTypes'
export type * from './kernelTypes'
export type { ResolveSurfaceSessionResult, SurfaceRef } from './surfaceSession'
