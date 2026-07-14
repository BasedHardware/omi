// KernelRuns — Windows port of the macOS agent runtime's kernel-runs.ts
// (desktop/macos/agent/src/runtime/kernel-runs.ts).
//
// The run entry points: executeRun, sendAgentMessage, spawnBackgroundAgent,
// delegateAgent, cancelRun. Everything here is a thin composition over
// KernelCore's state machine.
//
// INV-AGENT leaf-role guard lives here: a leaf session may not spawn a background
// agent or delegate, and an agent-originated spawn must present a coordinator
// caller session (only trusted user/desktop control may spawn without one).

import type { CancelDispatchResult } from '../codingAgent/interface'
import { KernelCore } from './kernelCore'
import {
  DEFAULT_DELEGATION_MAX_BUDGET_USD,
  DEFAULT_DELEGATION_MAX_DEPTH,
  TERMINAL_STATUSES,
  buildDelegatedPrompt,
  messageFrom,
  requiredChildSessionId
} from './kernelSupport'
import type {
  CancelRunResult,
  DelegateAgentInput,
  DelegateAgentResult,
  ExecuteAgentRunInput,
  KernelRunResult,
  SendAgentMessageInput,
  SpawnBackgroundAgentInput,
  SpawnBackgroundAgentResult
} from './kernelTypes'

export class KernelRuns extends KernelCore {
  async executeRun(input: ExecuteAgentRunInput): Promise<KernelRunResult> {
    const accepted = this.createAcceptedRun(input)
    return this.executeAcceptedRun(input, accepted)
  }

  async sendAgentMessage(input: SendAgentMessageInput): Promise<KernelRunResult> {
    const session = this.readSession(input.sessionId)
    return this.executeRun({
      ownerId: input.ownerId,
      sessionId: input.sessionId,
      surfaceKind: session.surfaceKind,
      defaultAdapterId: session.defaultAdapterId,
      clientId: input.clientId,
      requestId: input.requestId,
      prompt: input.prompt,
      promptBlocks: input.promptBlocks,
      mode: input.mode,
      adapterId: input.adapterId ?? session.defaultAdapterId,
      cwd: input.cwd ?? session.defaultCwd ?? undefined,
      model: input.model,
      mcpServers: input.mcpServers,
      maxAttempts: input.maxAttempts,
      recoverAfterError: input.recoverAfterError,
      metadata: input.metadata
    })
  }

  async spawnBackgroundAgent(
    input: SpawnBackgroundAgentInput
  ): Promise<SpawnBackgroundAgentResult> {
    if (input.callerSessionId) {
      const callerSession = this.readSession(input.callerSessionId)
      this.assertSessionOwner(callerSession, input.ownerId)
      if (callerSession.executionRole === 'leaf') {
        throw new Error('Leaf workers cannot create background agents.')
      }
    } else if (!input.trustedUserSpawn) {
      throw new Error('Background agent spawn requires a coordinator caller session.')
    }
    const runInput: ExecuteAgentRunInput = {
      ownerId: input.ownerId,
      surfaceKind: input.surfaceKind ?? 'floating_bar',
      executionRole: 'leaf',
      externalRefKind: input.externalRefKind,
      externalRefId: input.externalRefId,
      title: input.title ?? `Background: ${input.prompt.slice(0, 80)}`,
      defaultAdapterId: input.defaultAdapterId ?? input.adapterId,
      adapterId: input.adapterId ?? input.defaultAdapterId,
      clientId: input.clientId,
      requestId: input.requestId,
      prompt: input.prompt,
      mode: input.mode ?? 'act',
      cwd: input.cwd,
      model: input.model,
      mcpServers: input.mcpServers,
      maxAttempts: input.maxAttempts,
      recoverAfterError: input.recoverAfterError,
      metadata: {
        ...(input.metadata ?? {}),
        spawnKind: 'background_agent'
      }
    }
    const accepted = this.createAcceptedRun(runInput)
    void this.executeAcceptedRun(runInput, accepted).catch(() => {
      // executeAcceptedRun records the failed run/attempt and emits events.
    })
    return {
      session: accepted.session,
      run: accepted.run
    }
  }

  async delegateAgent(input: DelegateAgentInput): Promise<DelegateAgentResult> {
    this.assertDelegationConstraints(input)
    const parentRun = this.readRun(input.parentRunId)
    const parentSession = this.readSession(parentRun.sessionId)
    if (parentSession.executionRole === 'leaf') {
      throw new Error('Leaf workers cannot create delegated agents.')
    }
    if (input.ownerId && parentSession.ownerId !== input.ownerId) {
      throw new Error(`Parent run ${input.parentRunId} does not belong to owner ${input.ownerId}`)
    }
    const ownerId = input.ownerId ?? parentSession.ownerId
    const childPrompt = buildDelegatedPrompt(input.objective, input.context)
    const childRunInput: ExecuteAgentRunInput = {
      ownerId,
      sessionId:
        input.mode === 'continue'
          ? requiredChildSessionId(input.childSessionId)
          : input.childSessionId,
      surfaceKind: input.childSurfaceKind ?? 'delegated_agent',
      executionRole: 'leaf',
      providerBoundary: parentSession.providerBoundary,
      externalRefKind: input.childExternalRefKind,
      externalRefId: input.childExternalRefId,
      title: input.childTitle ?? `Delegated: ${input.objective.slice(0, 80)}`,
      defaultAdapterId:
        input.defaultAdapterId ?? input.adapterId ?? parentSession.defaultAdapterId,
      adapterId: input.adapterId ?? input.defaultAdapterId ?? parentSession.defaultAdapterId,
      clientId: input.clientId,
      requestId: input.requestId,
      prompt: childPrompt,
      mode: input.runMode ?? 'ask',
      cwd: input.cwd ?? parentRun.cwd ?? parentSession.defaultCwd ?? undefined,
      model: input.model,
      mcpServers: input.mcpServers,
      maxAttempts: input.maxAttempts,
      recoverAfterError: input.recoverAfterError,
      parentRunId: parentRun.runId,
      metadata: {
        ...(input.metadata ?? {}),
        delegationMode: input.mode,
        parentRunId: parentRun.runId,
        maxDepth: input.maxDepth ?? DEFAULT_DELEGATION_MAX_DEPTH,
        maxBudgetUsd: input.maxBudgetUsd ?? DEFAULT_DELEGATION_MAX_BUDGET_USD
      }
    }
    const created = this.createDelegatedRun(parentSession, parentRun, childRunInput, input)

    if (input.mode === 'spawn') {
      const runningDelegation = this.updateDelegationStatus(created.delegation, 'running')
      void this.executeDelegationAsync(
        childRunInput,
        { ...created, delegation: runningDelegation },
        false
      ).catch((error) => {
        this.updateDelegationStatus(runningDelegation, 'failed', messageFrom(error))
      })
      return {
        delegation: runningDelegation,
        childSession: created.session,
        childRun: created.run
      }
    }

    return this.executeDelegationAsync(childRunInput, created)
  }

  async cancelRun(runId: string, input: { ownerId?: string } = {}): Promise<CancelRunResult> {
    const active = this.activeExecutions.get(runId)
    const run = this.readRun(runId)
    if (input.ownerId) {
      this.assertRunOwner(run, input.ownerId)
    }
    if (TERMINAL_STATUSES.includes(run.status)) {
      return {
        accepted: false,
        dispatchAttempted: false,
        adapterAcknowledged: false,
        runId
      }
    }
    const attempt = this.readActiveAttempt(runId)
    const requestedAt = Date.now()

    this.withTransaction(() => {
      this.updateRun(runId, { status: 'cancelling', updatedAtMs: requestedAt })
      if (attempt) {
        this.updateAttempt(attempt.attemptId, {
          status: 'cancelling',
          cancellationRequestedAtMs: requestedAt,
          updatedAtMs: requestedAt
        })
      }
      this.appendEvent({
        sessionId: run.sessionId,
        runId,
        attemptId: attempt?.attemptId ?? null,
        type: 'run.cancellation_requested',
        payload: { runId, attemptId: attempt?.attemptId ?? null }
      })
      this.appendEvent({
        sessionId: run.sessionId,
        runId,
        attemptId: attempt?.attemptId ?? null,
        type: 'run.cancelling',
        payload: { runId, attemptId: attempt?.attemptId ?? null }
      })
    })

    let dispatchAttempted = false
    let adapterAcknowledged = false
    if (active && attempt) {
      let dispatch: CancelDispatchResult = {
        accepted: true,
        dispatchAttempted: false,
        adapterAcknowledged: false,
        message: undefined as string | undefined
      }
      try {
        dispatch = await active.adapter.cancelAttempt({
          sessionId: active.sessionId,
          ownerId: this.readSession(run.sessionId).ownerId,
          requestId: run.requestId,
          clientId: run.clientId,
          runId,
          attemptId: attempt.attemptId,
          binding: active.binding
        })
      } catch (error) {
        dispatch = {
          accepted: true,
          dispatchAttempted: true,
          adapterAcknowledged: false,
          message: messageFrom(error)
        }
      } finally {
        active.abortController.abort()
      }
      dispatchAttempted = dispatch.dispatchAttempted
      adapterAcknowledged = dispatch.adapterAcknowledged
      const now = Date.now()
      this.withTransaction(() => {
        this.updateAttempt(attempt.attemptId, {
          cancellationDispatchedAtMs: dispatch.dispatchAttempted ? now : null,
          cancellationAcknowledgedAtMs: dispatch.adapterAcknowledged ? now : null,
          updatedAtMs: now
        })
        this.appendEvent({
          sessionId: run.sessionId,
          runId,
          attemptId: attempt.attemptId,
          type: 'attempt.cancel_dispatch',
          payload: dispatch
        })
      })
    }

    return {
      accepted: true,
      dispatchAttempted,
      adapterAcknowledged,
      runId,
      attemptId: attempt?.attemptId
    }
  }
}
