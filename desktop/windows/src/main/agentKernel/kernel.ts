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
// Deliberately NOT ported here:
//   - the control-plane API (awareness snapshot, dispatch create/resolve, control
//     tools, tool policy, tool manifest) — that is the agent control plane.
//   - workstream continuity — owned by the workstream/proactive track.
//   - the JSONL/stdio transport — Windows runs the kernel in-process in Electron
//     main, so there is no subprocess protocol at all.

import { KernelSessions } from './kernelSessions'
import {
  buildDesktopActionQueue,
  type DesktopActionQueueItem
} from './desktopActionQueue'
import {
  buildDesktopContextPacket,
  type BuiltDesktopContextPacket
} from './desktopContextPacket'
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
  taskCandidateToQueueInput
} from './kernelSupport'
import type { DesktopAttentionOverride, NewDesktopContextPacket } from './types'
import type {
  DesktopActionQueueInput,
  DesktopContextPacketPersistInput,
  SetDesktopAttentionOverrideInput
} from './kernelTypes'

/** Owner used when a caller does not scope the request. Matches macOS. */
const DEFAULT_OWNER_ID = 'desktop-local-user'

export class AgentRuntimeKernel extends KernelSessions {
  persistDesktopContextPacket(
    input: DesktopContextPacketPersistInput
  ): BuiltDesktopContextPacket {
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

  listDesktopAttentionOverrides(ownerId: string): DesktopAttentionOverride[] {
    return this.readDesktopAttentionOverrides(ownerId)
  }

  setDesktopAttentionOverride(
    input: SetDesktopAttentionOverrideInput
  ): DesktopAttentionOverride {
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
