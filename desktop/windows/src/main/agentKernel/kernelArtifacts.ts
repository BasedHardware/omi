// KernelArtifacts — Windows port of the macOS agent runtime's kernel-artifacts.ts
// (desktop/macos/agent/src/runtime/kernel-artifacts.ts).
//
// Artifact + run inspection surface: getRun, inspectArtifacts, persistArtifact,
// artifact lifecycle transitions, the artifact-delivery outbox, and the
// adapter-capacity predicates the callers use before dispatching work.

import { KernelRuns } from './kernelRuns'
import {
  boundedLimit,
  desktopArtifactDeliveryFromRow,
  placeholders
} from './kernelSupport'
import type { AgentArtifact, DesktopArtifactDelivery, NewDesktopArtifactDelivery } from './types'
import type {
  GetRunInput,
  InspectArtifactsInput,
  KernelRunDetails,
  PersistArtifactInput,
  UpdateArtifactLifecycleInput,
  UpdateArtifactLifecycleResult
} from './kernelTypes'

export class KernelArtifacts extends KernelRuns {
  queueArtifactDelivery(input: NewDesktopArtifactDelivery): DesktopArtifactDelivery {
    if (input.deliveryId) {
      const existing = this.store.getOptionalRow(
        'SELECT * FROM desktop_artifact_deliveries WHERE delivery_id = ? AND owner_id = ?',
        [input.deliveryId, input.ownerId]
      )
      if (existing) return desktopArtifactDeliveryFromRow(existing)
    }
    return this.store.insertDesktopArtifactDelivery(input)
  }

  listArtifactDeliveries(input: {
    ownerId: string
    targetRef?: string
    statuses?: DesktopArtifactDelivery['deliveryStatus'][]
    limit?: number
  }): DesktopArtifactDelivery[] {
    const where = ['owner_id = ?']
    const values: unknown[] = [input.ownerId]
    if (input.targetRef) {
      where.push('target_ref = ?')
      values.push(input.targetRef)
    }
    if (input.statuses?.length) {
      where.push(`delivery_status IN (${placeholders(input.statuses.length)})`)
      values.push(...input.statuses)
    }
    values.push(boundedLimit(input.limit, 100, 500))
    return this.store
      .allRows(
        `SELECT * FROM desktop_artifact_deliveries
       WHERE ${where.join(' AND ')}
       ORDER BY created_at_ms ASC LIMIT ?`,
        values
      )
      .map(desktopArtifactDeliveryFromRow)
  }

  updateArtifactDelivery(
    deliveryId: string,
    input: { ownerId: string } & Partial<
      Pick<
        DesktopArtifactDelivery,
        'deliveryStatus' | 'attemptCount' | 'receiptJson' | 'errorJson' | 'deliveredAtMs'
      >
    >
  ): DesktopArtifactDelivery {
    return this.store.updateDesktopArtifactDelivery(deliveryId, input)
  }

  getRun(input: GetRunInput): KernelRunDetails {
    const run = this.readRun(input.runId)
    const session = this.readSession(run.sessionId)
    if (input.ownerId) {
      this.assertSessionOwner(session, input.ownerId)
    }
    return {
      session,
      run,
      attempts: this.readAttemptsForRun(run.runId),
      adapterBindings: this.readBindingsForSession(session.sessionId),
      artifacts: this.readArtifacts({ runId: run.runId, limit: 100 }),
      events: input.includeEvents
        ? this.readEventsForRun(run.runId, boundedLimit(input.eventLimit, 100, 500))
        : [],
      parentDelegations: this.readParentDelegationsForRun(run.runId),
      childDelegations: this.readChildDelegationsForRun(run.runId)
    }
  }

  inspectArtifacts(input: InspectArtifactsInput): AgentArtifact[] {
    if (!input.artifactId && !input.sessionId && !input.runId && !input.attemptId) {
      throw new Error('Inspecting artifacts requires artifactId, sessionId, runId, or attemptId')
    }
    if (input.ownerId) {
      this.assertArtifactSelectorOwner(input, input.ownerId)
    }
    return this.readArtifacts(input)
  }

  updateArtifactLifecycle(input: UpdateArtifactLifecycleInput): UpdateArtifactLifecycleResult {
    return this.withTransaction(() => {
      const artifact = this.readArtifact(input.artifactId)
      this.assertArtifactScope(artifact, input)
      if (input.ownerId) {
        this.assertSessionOwner(this.readSession(artifact.sessionId), input.ownerId)
      }
      if (artifact.lifecycleState === input.state) {
        return { artifact, changed: false, event: null }
      }

      const now = Date.now()
      this.store.execute(
        'UPDATE artifacts SET lifecycle_state = ?, lifecycle_updated_at_ms = ? WHERE artifact_id = ?',
        [input.state, now, artifact.artifactId]
      )
      const updatedArtifact = this.readArtifact(artifact.artifactId)
      const event = this.appendEvent({
        sessionId: updatedArtifact.sessionId,
        runId: updatedArtifact.runId,
        attemptId: updatedArtifact.attemptId,
        type: 'artifact.lifecycle_updated',
        payload: {
          artifactId: updatedArtifact.artifactId,
          previousState: artifact.lifecycleState,
          state: updatedArtifact.lifecycleState,
          reason: input.reason ?? null,
          metadata: input.metadata ?? {},
          lifecycleUpdatedAtMs: now
        }
      })
      return { artifact: updatedArtifact, changed: true, event }
    })
  }

  persistArtifact(input: PersistArtifactInput): AgentArtifact {
    return this.withTransaction(() => this.persistArtifactInTransaction(input))
  }

  hasActiveExecutionForAdapter(adapterId: string): boolean {
    for (const active of this.activeExecutions.values()) {
      if (active.adapter.adapterId === adapterId) return true
    }
    return false
  }

  hasActiveExecutionForSessionAdapter(sessionId: string, adapterId: string): boolean {
    for (const active of this.activeExecutions.values()) {
      if (active.sessionId === sessionId && active.adapter.adapterId === adapterId) return true
    }
    return false
  }

  hasExecutionCapacityForAdapter(adapterId: string): boolean {
    if (!this.registry.has(adapterId)) return false
    let activeCount = 0
    for (const active of this.activeExecutions.values()) {
      if (active.adapter.adapterId === adapterId) activeCount += 1
    }
    return activeCount < this.registry.capacity(adapterId)
  }

  isAdapterRegistered(adapterId: string): boolean {
    return this.registry.has(adapterId)
  }

  defaultAdapterIdForSession(sessionId: string): string {
    return this.readSession(sessionId).defaultAdapterId
  }

  defaultAdapterIdForRun(runId: string): string {
    const run = this.readRun(runId)
    return this.readSession(run.sessionId).defaultAdapterId
  }
}
