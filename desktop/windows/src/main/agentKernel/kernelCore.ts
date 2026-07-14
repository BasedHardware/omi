// KernelCore — Windows port of the macOS agent runtime's kernel-core.ts
// (desktop/macos/agent/src/runtime/kernel-core.ts).
//
// The bottom of the kernel class chain:
//   KernelCore -> KernelRuns -> KernelArtifacts -> KernelSessions -> AgentRuntimeKernel
//
// It owns the run/attempt/binding state machine — accepting a run, resolving (or
// opening, resuming, replacing) the adapter binding, assembling the turn prompt,
// dispatching the attempt to a pooled worker, and recording every terminal
// transition as a persisted event. Everything above it is API surface over these
// primitives.
//
// INV-AGENT: the Omi-owned `sessionId` and the adapter-owned
// `adapterNativeSessionId` are distinct throughout; `createAttempt` refuses a
// second active attempt on a run (single-active-run enforcement); and the
// provider boundary of a session is re-checked on every accepted run so a session
// can never be rerouted to a different credential scope.
//
// Windows delta: the kernel runs in-process in Electron main, so there is no
// JSONL/stdio transport — subscribers receive persisted AgentEvents directly.

import type {
  AdapterAttemptResult,
  AdapterBindingHandle,
  AdapterStreamEvent,
  RuntimeAdapter
} from '../codingAgent/interface'
import { AdapterRegistry } from './adapterRegistry'
import { failureFromError, type RuntimeFailure } from '../codingAgent/failures'
import { generateAgentId } from './store'
import { resolveSurfaceSession, type SurfaceRef } from './surfaceSession'
import { advanceBindingTurnDelivery, appendConversationTurn, conversationIdForSession } from './conversationTurns'
import {
  acknowledgeCompletionDelta,
  assembleTurnContext,
  bindingCarriesNativeHistory
} from './turnContext'
import type {
  AdapterBinding,
  AgentArtifact,
  AgentDelegation,
  AgentEvent,
  AgentRun,
  AgentSession,
  AgentStore,
  AttemptStatus,
  DelegationStatus,
  DesktopArtifactDelivery,
  DesktopAttentionOverride,
  DesktopCoordinatorDispatch,
  DesktopMemoryCandidate,
  DesktopTaskCandidate,
  NewAgentArtifact,
  RunAttempt,
  RunStatus
} from './types'
import type { QueueRunInput } from './desktopActionQueue'
import type { BuiltDesktopContextPacket, DesktopContextPacketBuildInput } from './desktopContextPacket'
import type {
  DesktopIntentRoute,
  DesktopIntentRouteInput,
  DesktopIntentSessionCandidate
} from './desktopIntentRouter'
import { OmiArtifactStorage } from './artifactStorage'
import {
  ACTIVE_STATUSES,
  DEFAULT_DELEGATION_MAX_BUDGET_USD,
  DEFAULT_DELEGATION_MAX_DEPTH,
  HARD_DELEGATION_MAX_BUDGET_USD,
  HARD_DELEGATION_MAX_DEPTH,
  KERNEL_MCP_PROTOCOL_VERSION,
  TERMINAL_STATUSES,
  artifactFromRow,
  attemptColumnMap,
  attemptFromRow,
  bindingColumnMap,
  bindingFromRow,
  bindingMetadata,
  boundedLimit,
  canonicalAdapterEventType,
  delegationFromRow,
  delegationValues,
  desktopArtifactDeliveryFromRow,
  desktopAttentionOverrideFromRow,
  desktopDispatchFromRow,
  desktopMemoryCandidateFromRow,
  desktopTaskCandidateFromRow,
  eventFromRow,
  intentCandidateStatus,
  isStaleBindingError,
  mcpServersForBinding,
  messageFrom,
  nullableNumber,
  nullableString,
  numberValue,
  parseJsonObject,
  placeholders,
  queueRunGoalText,
  refreshMcpAttemptContext,
  requiresVerifiedContextDispatch,
  runColumnMap,
  runFromRow,
  sessionFromRow,
  stableHash,
  stableJsonHash,
  stableMcpServerConfig,
  stringValue,
  updateByColumns
} from './kernelSupport'
import type {
  AgentRuntimeKernelOptions,
  DelegateAgentInput,
  DelegateAgentResult,
  ExecuteAgentRunInput,
  InspectArtifactsInput,
  KernelEventSubscriber,
  KernelRunResult,
  KernelSessionResolutionInput,
  KernelSessionSummary,
  ListSessionsInput,
  PersistArtifactInput,
  UpdateArtifactLifecycleInput
} from './kernelTypes'
import { StaleAdapterBindingError } from './kernelTypes'
import { providerBoundaryForAdapter, resolveAdapterWithinBoundary } from './executionPolicy'

interface ActiveExecution {
  adapter: RuntimeAdapter
  abortController: AbortController
  binding: AdapterBindingHandle
  attemptId: string
  sessionId: string
}

export class KernelCore {
  protected readonly store: AgentStore
  protected readonly registry: AdapterRegistry
  protected readonly runtimeNodeId: string
  protected readonly artifactStorage?: OmiArtifactStorage
  protected readonly recoverRunInput?: AgentRuntimeKernelOptions['recoverRunInput']
  protected readonly subscribers = new Set<KernelEventSubscriber>()
  protected readonly activeExecutions = new Map<string, ActiveExecution>()
  protected readonly bindingResolutionLocks = new Map<string, Promise<void>>()
  private transactionDepth = 0
  private pendingSubscriberEvents: AgentEvent[] = []

  constructor(options: AgentRuntimeKernelOptions) {
    this.store = options.store
    this.registry = options.registry
    this.runtimeNodeId = options.runtimeNodeId ?? 'desktop-local'
    this.artifactStorage = options.artifactStorage
    this.recoverRunInput = options.recoverRunInput
  }

  subscribe(subscriber: KernelEventSubscriber): () => void {
    this.subscribers.add(subscriber)
    return () => this.subscribers.delete(subscriber)
  }

  protected createAcceptedRun(input: ExecuteAgentRunInput): { session: AgentSession; run: AgentRun } {
    return this.withTransaction(() => {
      const session = this.resolveSession(input)
      resolveAdapterWithinBoundary({
        providerBoundary: session.providerBoundary,
        defaultAdapterId: session.defaultAdapterId,
        requestedAdapterId: input.adapterId ?? session.defaultAdapterId
      })
      const run = this.store.insertRun({
        sessionId: session.sessionId,
        parentRunId: input.parentRunId ?? null,
        clientId: input.clientId,
        requestId: input.requestId,
        status: 'queued',
        mode: input.mode ?? 'ask',
        inputJson: JSON.stringify({
          prompt: input.prompt,
          systemPrompt: input.systemPrompt ?? '',
          metadata: input.metadata ?? {}
        }),
        requestedModelId: input.model ?? null,
        cwd: input.cwd ?? session.defaultCwd
      })
      this.appendEvent({
        sessionId: session.sessionId,
        runId: run.runId,
        type: 'run.queued',
        payload: { runId: run.runId, requestId: run.requestId, clientId: run.clientId }
      })
      this.touchSession(session.sessionId)
      return { session, run }
    })
  }

  protected async executeAcceptedRun(
    input: ExecuteAgentRunInput,
    accepted: { session: AgentSession; run: AgentRun }
  ): Promise<KernelRunResult> {
    const adapterId = input.adapterId ?? accepted.session.defaultAdapterId
    if (!input.recoverAfterError) {
      const recovery = this.recoverRunInput?.(adapterId)
      if (recovery) {
        input = {
          ...input,
          maxAttempts: input.maxAttempts ?? recovery.maxAttempts,
          recoverAfterError: recovery.recoverAfterError
        }
      }
    }
    const maxAttempts = Math.max(1, input.maxAttempts ?? 2)
    let retryReason: string | null = null
    let resumeFromAttemptId: string | null = null
    let lastAttempt: RunAttempt | undefined
    let completionDeltaArtifacts: AgentArtifact[] = []
    const surfaceRef = this.surfaceRefForInput(input)
    const conversationId = conversationIdForSession(this.store, accepted.session.sessionId)

    for (let attemptNo = 1; attemptNo <= maxAttempts; attemptNo += 1) {
      const attempt = this.createAttempt({
        runId: accepted.run.runId,
        attemptNo,
        adapterId,
        retryReason,
        resumeFromAttemptId
      })
      lastAttempt = attempt
      const attemptInput = this.inputWithManagedArtifactCwd(
        input,
        accepted.session,
        accepted.run.runId,
        attempt.attemptId
      )
      if (
        attemptInput.cwd &&
        attemptInput.cwd !== (input.cwd ?? accepted.session.defaultCwd ?? undefined)
      ) {
        this.withTransaction(() => {
          this.updateRun(accepted.run.runId, { cwd: attemptInput.cwd, updatedAtMs: Date.now() })
        })
      }

      if (!this.registry.has(adapterId)) {
        const failure: RuntimeFailure = {
          code: 'adapter_not_registered',
          source: 'runtime',
          adapterId,
          retryable: false,
          userMessage: `Adapter not registered: ${adapterId}`,
          technicalMessage: `Adapter not registered: ${adapterId}`
        }
        this.failAttemptBeforeExecution(
          attempt,
          'adapter_not_registered',
          failure.userMessage,
          false,
          failure
        )
        break
      }
      const pool = this.registry.get(adapterId)

      let binding: AdapterBinding
      let handle: AdapterBindingHandle
      let bindingResolutionProtectedBindingId: string | null = null
      try {
        const resolved = await this.withBindingResolutionLock(
          accepted.session.sessionId,
          adapterId,
          async () => {
            const existingBinding = this.readActiveBinding(accepted.session.sessionId, adapterId)
            const bindingQueueKey = existingBinding
              ? this.handleForExistingBinding(existingBinding)
              : undefined
            return pool.runExclusiveQueued(
              bindingQueueKey,
              `${attempt.attemptId}:binding`,
              async (worker) => {
                const resolved = await this.resolveBindingForAttempt({
                  input: attemptInput,
                  session: accepted.session,
                  adapter: worker.adapter,
                  attempt,
                  adapterId
                })
                if (worker.adapter.capabilities.requiresPinnedWorker) {
                  if (resolved.replacesBindingId) {
                    worker.replacePinnedBinding(resolved.replacesBindingId, resolved.handle)
                  } else {
                    worker.pinBinding(resolved.handle)
                  }
                }
                return resolved
              },
              {
                ...(bindingQueueKey
                  ? {}
                  : {
                      onIdlePinnedBindingEvicted: (evictedBindingId: string) => {
                        this.markEvictedBindingStale(evictedBindingId, 'pinned_worker_reassigned')
                      }
                    }),
                protectPinnedBindingAfterWork: true
              }
            )
          }
        )
        binding = resolved.binding
        handle = resolved.handle
        bindingResolutionProtectedBindingId = pool.requiresPinnedWorkers
          ? (handle.bindingId ?? null)
          : null
      } catch (error) {
        pool.unprotectPinnedBinding(bindingResolutionProtectedBindingId)
        if (isStaleBindingError(error)) {
          const failure = failureFromError(error, {
            code: 'stale_binding',
            source: 'adapter_process',
            adapterId: attempt.adapterId,
            retryable: attemptNo < maxAttempts
          })
          this.failAttemptBeforeExecution(
            attempt,
            'stale_binding',
            failure.userMessage,
            attemptNo < maxAttempts,
            failure
          )
          retryReason = 'stale_binding'
          resumeFromAttemptId = attempt.attemptId
          continue
        }
        if (
          await this.tryRecoverAttempt(input, attempt, error, 'binding_failed', attemptNo < maxAttempts)
        ) {
          retryReason = 'recoverable_error'
          resumeFromAttemptId = attempt.attemptId
          continue
        }
        const failure = failureFromError(error, {
          code: 'binding_failed',
          source: 'adapter_process',
          adapterId: attempt.adapterId,
          retryable: false
        })
        this.failAttemptBeforeExecution(attempt, 'binding_failed', failure.userMessage, false, failure)
        break
      }

      const abortController = new AbortController()
      const protectedPinnedBindingId = pool.requiresPinnedWorkers ? handle.bindingId : null
      pool.protectPinnedBinding(protectedPinnedBindingId)

      let effectivePrompt = attemptInput.prompt
      let effectivePromptBlocks = attemptInput.promptBlocks
      let acknowledgedCompletionDelta: {
        ids: string[]
        completedAtHighWaterMs?: number
      } | null = null
      if (surfaceRef && conversationId) {
        const assembled = assembleTurnContext({
          store: this.store,
          services: this.turnContextServices(),
          ownerId: input.ownerId,
          sessionId: accepted.session.sessionId,
          conversationId,
          surfaceRef,
          executionRole: accepted.session.executionRole,
          userText: input.prompt,
          attachmentMetadataJson: input.attachmentMetadataJson,
          surfaceContextJson: input.surfaceContextJson,
          imagePresent: Boolean(input.imagePresent),
          bindingCarriesNativeHistory: bindingCarriesNativeHistory(binding),
          lastDeliveredTurnCreatedAtMs: binding.lastDeliveredTurnCreatedAtMs,
          runId: accepted.run.runId
        })
        effectivePrompt = assembled.prompt
        effectivePromptBlocks = attemptInput.promptBlocks
          ? attemptInput.promptBlocks.map((block) =>
              block.type === 'text' ? { ...block, text: assembled.prompt } : block
            )
          : undefined
        completionDeltaArtifacts = assembled.completionDeltaArtifacts
        if (assembled.acknowledgedCompletionDeltaIds.length > 0) {
          acknowledgedCompletionDelta = {
            ids: assembled.acknowledgedCompletionDeltaIds,
            completedAtHighWaterMs:
              assembled.completionDeltaArtifacts
                .map((artifact) => artifact.createdAtMs)
                .reduce((max, value) => Math.max(max, value), 0) || undefined
          }
        }
      }

      if (conversationId && surfaceRef && attemptNo === 1) {
        appendConversationTurn(this.store, {
          conversationId,
          role: 'user',
          surfaceKind: surfaceRef.surfaceKind,
          content: input.prompt,
          createdAtMs: Date.now(),
          metadataJson: JSON.stringify({ runId: accepted.run.runId })
        })
        advanceBindingTurnDelivery(this.store, binding.bindingId, conversationId)
      }

      try {
        const result = await pool.runExclusiveQueued(handle, attempt.attemptId, async (worker) => {
          if (this.runStatus(accepted.run.runId) === 'cancelling') {
            throw new Error('cancelled_before_adapter_dispatch')
          }
          this.activeExecutions.set(accepted.run.runId, {
            adapter: worker.adapter,
            abortController,
            binding: handle,
            attemptId: attempt.attemptId,
            sessionId: accepted.session.sessionId
          })
          refreshMcpAttemptContext(
            mcpServersForBinding(
              input.mcpServers ?? [],
              accepted.session.sessionId,
              adapterId,
              this.runtimeNodeId
            ),
            {
              ownerId: input.ownerId,
              requestId: accepted.run.requestId,
              clientId: accepted.run.clientId,
              protocolVersion: KERNEL_MCP_PROTOCOL_VERSION,
              sessionId: accepted.session.sessionId,
              runId: accepted.run.runId,
              attemptId: attempt.attemptId,
              adapterSessionId: handle.adapterNativeSessionId
            }
          )
          this.markAttemptRunning(attempt, binding)
          return worker.adapter.executeAttempt(
            {
              sessionId: accepted.session.sessionId,
              ownerId: input.ownerId,
              requestId: accepted.run.requestId,
              clientId: accepted.run.clientId,
              runId: accepted.run.runId,
              attemptId: attempt.attemptId,
              binding: handle,
              prompt: effectivePromptBlocks ?? [{ type: 'text', text: effectivePrompt }],
              mode: input.mode ?? 'ask',
              model: input.model,
              tools: input.tools ?? [],
              metadata: input.metadata
            },
            (event) =>
              this.persistAdapterEvent(
                accepted.session.sessionId,
                accepted.run.runId,
                attempt.attemptId,
                event
              ),
            abortController.signal
          )
        })
        this.activeExecutions.delete(accepted.run.runId)
        if (acknowledgedCompletionDelta && surfaceRef) {
          acknowledgeCompletionDelta(this.store, {
            ownerId: input.ownerId,
            surfaceRef,
            ids: acknowledgedCompletionDelta.ids,
            completedAtHighWaterMs: acknowledgedCompletionDelta.completedAtHighWaterMs ?? null
          })
        }
        const completed = this.completeAttemptAndRun(
          accepted.session,
          accepted.run.runId,
          attempt,
          binding,
          result,
          {
            conversationId,
            surfaceKind: surfaceRef?.surfaceKind ?? accepted.session.surfaceKind
          }
        )
        return { ...completed, completionDeltaArtifacts }
      } catch (error) {
        this.activeExecutions.delete(accepted.run.runId)
        if (isStaleBindingError(error)) {
          this.markBindingStale(binding, attempt, messageFrom(error))
          const failure = failureFromError(error, {
            code: 'stale_binding',
            source: 'adapter_execution',
            adapterId: attempt.adapterId,
            retryable: attemptNo < maxAttempts
          })
          this.failAttemptBeforeExecution(
            attempt,
            'stale_binding',
            failure.userMessage,
            attemptNo < maxAttempts,
            failure
          )
          retryReason = 'stale_binding'
          resumeFromAttemptId = attempt.attemptId
          continue
        }
        if (
          await this.tryRecoverAttempt(
            input,
            attempt,
            error,
            'adapter_execution_failed',
            attemptNo < maxAttempts
          )
        ) {
          retryReason = 'recoverable_error'
          resumeFromAttemptId = attempt.attemptId
          continue
        }
        const wasCancelling = this.runStatus(accepted.run.runId) === 'cancelling'
        const status: AttemptStatus = wasCancelling ? 'cancelled' : 'failed'
        const failure = wasCancelling
          ? null
          : failureFromError(error, {
              code: 'adapter_execution_failed',
              source: 'adapter_execution',
              adapterId: attempt.adapterId,
              retryable: false
            })
        this.finishAttemptAndRun({
          sessionId: accepted.session.sessionId,
          runId: accepted.run.runId,
          attemptId: attempt.attemptId,
          status,
          finalText: null,
          errorCode: wasCancelling ? null : 'adapter_execution_failed',
          errorMessage: failure?.userMessage ?? null,
          failure
        })
        break
      } finally {
        pool.unprotectPinnedBinding(protectedPinnedBindingId)
      }
    }

    const finalRun = this.readRun(accepted.run.runId)
    const attempt = lastAttempt ?? this.readLatestAttempt(accepted.run.runId)
    return {
      session: accepted.session,
      run: finalRun,
      attempt,
      artifacts: this.readArtifacts({ runId: accepted.run.runId, limit: 50 }),
      adapterSessionId: null,
      terminalStatus: finalRun.status === 'cancelled' ? 'cancelled' : 'failed',
      text: finalRun.finalText ?? '',
      completionDeltaArtifacts
    }
  }

  /**
   * The `this`-cast service host that lets turn-context call back up the class
   * chain. `listSessions` lands on KernelSessions, `inspectArtifacts` on
   * KernelArtifacts, and `persistDesktopContextPacket` / `routeDesktopIntent` on
   * AgentRuntimeKernel — none of which exist at this level. Ported from macOS
   * as-is; the recursion is real and resolves at construction time because only a
   * fully-built AgentRuntimeKernel is ever instantiated.
   */
  protected turnContextServices() {
    const host = this as unknown as KernelCore & {
      persistDesktopContextPacket(
        packetInput: DesktopContextPacketBuildInput
      ): BuiltDesktopContextPacket
      routeDesktopIntent(
        routeInput: Omit<DesktopIntentRouteInput, 'nowMs' | 'actionQueue' | 'sessionCandidates'> & {
          ownerId?: string
        }
      ): DesktopIntentRoute
      listSessions(listInput: ListSessionsInput): KernelSessionSummary[]
      inspectArtifacts(inspectInput: InspectArtifactsInput): AgentArtifact[]
    }
    return {
      persistDesktopContextPacket: (packetInput: DesktopContextPacketBuildInput) =>
        host.persistDesktopContextPacket(packetInput),
      routeDesktopIntent: (routeInput: Parameters<typeof host.routeDesktopIntent>[0]) =>
        host.routeDesktopIntent(routeInput),
      listSessions: (listInput: ListSessionsInput) => host.listSessions(listInput),
      inspectArtifacts: (inspectInput: InspectArtifactsInput) => host.inspectArtifacts(inspectInput)
    }
  }

  protected surfaceRefForInput(input: ExecuteAgentRunInput): SurfaceRef | null {
    if (!input.surfaceKind || !input.externalRefKind || !input.externalRefId) return null
    return {
      surfaceKind: input.surfaceKind,
      externalRefKind: input.externalRefKind,
      externalRefId: input.externalRefId
    }
  }

  protected validateSensitiveContextDispatches(input: DesktopContextPacketBuildInput): void {
    for (const snippet of input.snippets) {
      if (snippet.selected === false || !requiresVerifiedContextDispatch(snippet)) continue
      const dispatchId = snippet.dispatchId?.trim()
      if (!dispatchId) {
        throw new Error(`Sensitive context snippet ${snippet.snippetId} requires a dispatch id`)
      }
      const row = this.store.getOptionalRow(
        'SELECT * FROM desktop_dispatches WHERE dispatch_id = ? AND owner_id = ?',
        [dispatchId, input.ownerId]
      )
      if (!row) {
        throw new Error(`Sensitive context dispatch ${dispatchId} was not found for owner`)
      }
      const dispatch = desktopDispatchFromRow(row)
      const resolution = parseJsonObject(dispatch.resolutionJson)
      if (!['approval', 'screen_context'].includes(dispatch.kind)) {
        throw new Error(`Sensitive context dispatch ${dispatchId} has invalid kind`)
      }
      if (dispatch.status !== 'resolved' || resolution.decision !== 'allow') {
        throw new Error(`Sensitive context dispatch ${dispatchId} is not approved`)
      }
      if (dispatch.operation && dispatch.operation !== snippet.operation) {
        throw new Error(`Sensitive context dispatch ${dispatchId} operation does not match snippet`)
      }
    }
  }

  protected createDelegatedRun(
    parentSession: AgentSession,
    parentRun: AgentRun,
    childRunInput: ExecuteAgentRunInput,
    input: DelegateAgentInput
  ): { session: AgentSession; run: AgentRun; delegation: AgentDelegation } {
    return this.withTransaction(() => {
      const session = this.resolveSession(childRunInput)
      if (session.sessionId === parentSession.sessionId) {
        throw new Error('Delegated child session must be distinct from parent session')
      }
      const run = this.store.insertRun({
        sessionId: session.sessionId,
        parentRunId: parentRun.runId,
        clientId: childRunInput.clientId,
        requestId: childRunInput.requestId,
        status: 'queued',
        mode: childRunInput.mode ?? 'ask',
        inputJson: JSON.stringify({
          prompt: childRunInput.prompt,
          systemPrompt: childRunInput.systemPrompt ?? '',
          metadata: childRunInput.metadata ?? {}
        }),
        requestedModelId: childRunInput.model ?? null,
        cwd: childRunInput.cwd ?? session.defaultCwd
      })
      const now = Date.now()
      const delegation: AgentDelegation = {
        delegationId: generateAgentId('delegation'),
        parentSessionId: parentSession.sessionId,
        parentRunId: parentRun.runId,
        childSessionId: session.sessionId,
        childRunId: run.runId,
        mode: input.mode,
        status: 'pending',
        objective: input.objective,
        requestJson: JSON.stringify({
          mode: input.mode,
          objective: input.objective,
          contextProvided: Boolean(input.context),
          childSurfaceKind: childRunInput.surfaceKind,
          childExternalRefKind: childRunInput.externalRefKind ?? null,
          childExternalRefId: childRunInput.externalRefId ?? null,
          maxDepth: input.maxDepth ?? DEFAULT_DELEGATION_MAX_DEPTH,
          maxBudgetUsd: input.maxBudgetUsd ?? DEFAULT_DELEGATION_MAX_BUDGET_USD
        }),
        resultArtifactId: null,
        createdAtMs: now,
        completedAtMs: null
      }
      this.store.execute(
        `INSERT INTO delegations (
          delegation_id, parent_session_id, parent_run_id, child_session_id, child_run_id,
          mode, status, objective, request_json, result_artifact_id, created_at_ms, completed_at_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        delegationValues(delegation)
      )
      this.appendEvent({
        sessionId: parentSession.sessionId,
        runId: parentRun.runId,
        type: 'delegation.created',
        payload: {
          delegationId: delegation.delegationId,
          mode: delegation.mode,
          childSessionId: session.sessionId,
          childRunId: run.runId
        }
      })
      this.appendEvent({
        sessionId: session.sessionId,
        runId: run.runId,
        type: 'run.queued',
        payload: {
          runId: run.runId,
          requestId: run.requestId,
          clientId: run.clientId,
          parentRunId: parentRun.runId,
          delegationId: delegation.delegationId
        }
      })
      this.touchSession(session.sessionId)
      return { session, run, delegation }
    })
  }

  protected async executeDelegationAsync(
    childRunInput: ExecuteAgentRunInput,
    created: { session: AgentSession; run: AgentRun; delegation: AgentDelegation },
    markRunning = true
  ): Promise<DelegateAgentResult> {
    if (markRunning) {
      created = { ...created, delegation: this.updateDelegationStatus(created.delegation, 'running') }
    }
    const result = await this.executeAcceptedRun(childRunInput, {
      session: created.session,
      run: created.run
    })
    const status = result.terminalStatus === 'succeeded' ? 'succeeded' : result.terminalStatus
    const delegation = this.updateDelegationStatus(created.delegation, status)
    const artifacts = this.readArtifacts({ runId: result.run.runId, limit: 50 })
    return {
      delegation,
      childSession: result.session,
      childRun: result.run,
      childAttempt: result.attempt,
      adapterSessionId: result.adapterSessionId,
      terminalStatus: result.terminalStatus,
      result: {
        summary: result.text,
        artifacts,
        verifiedEffects: [],
        openQuestions: [],
        usage: {
          inputTokens: result.run.inputTokens,
          outputTokens: result.run.outputTokens,
          cacheReadTokens: result.run.cacheReadTokens,
          cacheWriteTokens: result.run.cacheWriteTokens,
          costUsd: result.run.costUsd
        }
      }
    }
  }

  protected updateDelegationStatus(
    delegation: AgentDelegation,
    status: DelegationStatus,
    errorMessage?: string
  ): AgentDelegation {
    const now = Date.now()
    this.withTransaction(() => {
      this.store.execute(
        `UPDATE delegations
         SET status = ?, completed_at_ms = ?, result_artifact_id = result_artifact_id
         WHERE delegation_id = ?`,
        [status, status === 'running' || status === 'pending' ? null : now, delegation.delegationId]
      )
      if (status !== 'running') {
        this.appendEvent({
          sessionId: delegation.parentSessionId,
          runId: delegation.parentRunId,
          type: 'delegation.completed',
          payload: {
            delegationId: delegation.delegationId,
            childSessionId: delegation.childSessionId,
            childRunId: delegation.childRunId,
            status,
            errorMessage
          }
        })
      }
    })
    return this.readDelegation(delegation.delegationId)
  }

  protected assertDelegationConstraints(input: DelegateAgentInput): void {
    const maxDepth = input.maxDepth ?? DEFAULT_DELEGATION_MAX_DEPTH
    if (!Number.isInteger(maxDepth) || maxDepth < 1 || maxDepth > HARD_DELEGATION_MAX_DEPTH) {
      throw new Error(`Delegation maxDepth must be between 1 and ${HARD_DELEGATION_MAX_DEPTH}`)
    }
    const maxBudgetUsd = input.maxBudgetUsd ?? DEFAULT_DELEGATION_MAX_BUDGET_USD
    if (
      !Number.isFinite(maxBudgetUsd) ||
      maxBudgetUsd <= 0 ||
      maxBudgetUsd > HARD_DELEGATION_MAX_BUDGET_USD
    ) {
      throw new Error(
        `Delegation maxBudgetUsd must be greater than 0 and at most ${HARD_DELEGATION_MAX_BUDGET_USD}`
      )
    }
    const parentDepth = this.delegationDepth(input.parentRunId)
    if (parentDepth + 1 > maxDepth) {
      throw new Error(`Delegation depth ${parentDepth + 1} exceeds maxDepth ${maxDepth}`)
    }
  }

  protected resolveSession(input: KernelSessionResolutionInput): AgentSession {
    // An explicit canonical session is authoritative even when the caller also
    // supplies a new surface reference. This is how one long-running thread can
    // move between task scopes without silently forking its runtime identity.
    if (input.sessionId) {
      const existing = this.findExistingSession(input)
      if (existing) return existing
    }
    if (input.surfaceKind && input.externalRefKind && input.externalRefId) {
      const resolved = resolveSurfaceSession(
        this.store,
        {
          ownerId: input.ownerId,
          surfaceRef: {
            surfaceKind: input.surfaceKind,
            externalRefKind: input.externalRefKind,
            externalRefId: input.externalRefId
          },
          defaultAdapterId: input.defaultAdapterId,
          executionRole: input.executionRole,
          providerBoundary: input.providerBoundary,
          title: input.title ?? null
        },
        () => Date.now()
      )
      const session = this.readSession(resolved.agentSessionId)
      const hasCreationEvent = this.store.getOptionalRow(
        "SELECT event_id FROM events WHERE session_id = ? AND type = 'session.created' LIMIT 1",
        [session.sessionId]
      )
      if (!hasCreationEvent) {
        this.appendEvent({
          sessionId: session.sessionId,
          type: 'session.created',
          payload: {
            sessionId: session.sessionId,
            ownerId: session.ownerId,
            surfaceKind: session.surfaceKind
          }
        })
      }
      return session
    }
    const existing = this.findExistingSession(input)
    if (existing) return existing
    const session = this.store.insertSession({
      ownerId: input.ownerId,
      surfaceKind: input.surfaceKind,
      externalRefKind: input.externalRefKind ?? null,
      externalRefId: input.externalRefId ?? null,
      title: input.title ?? null,
      defaultAdapterId: input.defaultAdapterId ?? 'acp',
      executionRole: input.executionRole ?? 'coordinator',
      providerBoundary:
        input.providerBoundary ?? providerBoundaryForAdapter(input.defaultAdapterId ?? 'acp')
    })
    this.appendEvent({
      sessionId: session.sessionId,
      type: 'session.created',
      payload: {
        sessionId: session.sessionId,
        ownerId: session.ownerId,
        surfaceKind: session.surfaceKind
      }
    })
    return session
  }

  protected findExistingSession(input: KernelSessionResolutionInput): AgentSession | undefined {
    if (input.sessionId) {
      const session = this.readSession(input.sessionId)
      if (session.ownerId !== input.ownerId) {
        throw new Error(`Session ${input.sessionId} does not belong to owner ${input.ownerId}`)
      }
      return session
    }
    if (input.surfaceKind && input.externalRefKind && input.externalRefId) {
      const mapped = this.store.getOptionalRow(
        `SELECT agent_session_id FROM surface_conversations
         WHERE owner_id = ? AND surface_kind = ? AND external_ref_kind = ? AND external_ref_id = ?`,
        [input.ownerId, input.surfaceKind, input.externalRefKind, input.externalRefId]
      )
      if (mapped) {
        return this.readSession(String(mapped.agent_session_id))
      }
    }
    if (input.externalRefKind && input.externalRefId) {
      const row = this.store.getOptionalRow(
        'SELECT * FROM sessions WHERE owner_id = ? AND external_ref_kind = ? AND external_ref_id = ?',
        [input.ownerId, input.externalRefKind, input.externalRefId]
      )
      if (row) return sessionFromRow(row)
      return undefined
    }
    return undefined
  }

  protected findInvalidationSessionIds(input: KernelSessionResolutionInput): string[] {
    if (input.sessionId || input.externalRefKind || input.externalRefId) {
      return []
    }
    return this.store
      .allRows('SELECT session_id FROM sessions WHERE owner_id = ?', [input.ownerId])
      .map((row) => String(row.session_id))
  }

  protected createAttempt(input: {
    runId: string
    attemptNo: number
    adapterId: string
    retryReason: string | null
    resumeFromAttemptId: string | null
  }): RunAttempt {
    return this.withTransaction(() => {
      const active = this.readActiveAttempt(input.runId)
      if (active) {
        throw new Error(`Run ${input.runId} already has active attempt ${active.attemptId}`)
      }
      this.updateRun(input.runId, {
        status: 'starting',
        startedAtMs: input.attemptNo === 1 ? Date.now() : undefined,
        updatedAtMs: Date.now()
      })
      const attempt = this.store.insertAttempt({
        runId: input.runId,
        attemptNo: input.attemptNo,
        status: 'starting',
        adapterId: input.adapterId,
        adapterInstanceId: '',
        runtimeNodeId: this.runtimeNodeId,
        retryReason: input.retryReason,
        resumeFromAttemptId: input.resumeFromAttemptId,
        retryable: input.retryReason ? 1 : 0
      })
      const run = this.readRun(input.runId)
      this.appendEvent({
        sessionId: run.sessionId,
        runId: input.runId,
        type: 'run.starting',
        payload: { runId: input.runId, attemptNo: input.attemptNo }
      })
      this.appendEvent({
        sessionId: run.sessionId,
        runId: input.runId,
        attemptId: attempt.attemptId,
        type: 'attempt.created',
        payload: {
          attemptId: attempt.attemptId,
          attemptNo: attempt.attemptNo,
          retryReason: input.retryReason,
          resumeFromAttemptId: input.resumeFromAttemptId
        }
      })
      return attempt
    })
  }

  protected async resolveBindingForAttempt(input: {
    input: ExecuteAgentRunInput
    session: AgentSession
    adapter: RuntimeAdapter
    attempt: RunAttempt
    adapterId: string
  }): Promise<{ binding: AdapterBinding; handle: AdapterBindingHandle; replacesBindingId?: string }> {
    const active = this.readActiveBinding(input.session.sessionId, input.adapterId)
    if (active) {
      const handle = await this.resumeOrReplaceBinding(active, input)
      return {
        binding: this.readBinding(handle.bindingId!),
        handle,
        replacesBindingId: handle.replacesBindingId
      }
    }

    const nextGeneration = this.nextBindingGeneration(input.session.sessionId, input.adapterId)
    const previousBinding =
      nextGeneration > 1
        ? this.readLatestBinding(input.session.sessionId, input.adapterId)
        : undefined
    return this.openNewBinding(input, nextGeneration, previousBinding?.bindingId ?? null)
  }

  protected handleForExistingBinding(binding: AdapterBinding): AdapterBindingHandle {
    return {
      bindingId: binding.bindingId,
      sessionId: binding.sessionId,
      adapterId: binding.adapterId,
      adapterNativeSessionId: binding.adapterNativeSessionId ?? '',
      resumeFidelity: binding.resumeFidelity,
      cwd: binding.cwd ?? process.cwd(),
      model: binding.modelId ?? undefined
    }
  }

  protected isBindingCompatible(
    binding: AdapterBinding,
    input: {
      input: ExecuteAgentRunInput
      session: AgentSession
      adapter?: RuntimeAdapter
    }
  ): boolean {
    const requestedCwd = input.input.cwd ?? input.session.defaultCwd ?? process.cwd()
    const bindingCwd = binding.cwd ?? process.cwd()
    if (bindingCwd !== requestedCwd) {
      return false
    }
    if (input.input.model !== undefined && binding.modelId !== input.input.model) {
      return false
    }
    const requestedSystemPromptHash = stableHash(input.input.systemPrompt)
    if (binding.systemPromptHash !== null && binding.systemPromptHash !== requestedSystemPromptHash) {
      return false
    }
    const metadata = parseJsonObject(binding.metadataJson)
    const effectiveMcpServers = input.adapter?.effectiveMcpServers
      ? input.adapter.effectiveMcpServers(input.input.mcpServers ?? [])
      : (input.input.mcpServers ?? [])
    const expectedMcpServersHash = stableJsonHash(stableMcpServerConfig(effectiveMcpServers))
    if (metadata.mcpServersHash === undefined) {
      return true
    }
    return metadata.mcpServersHash === expectedMcpServersHash
  }

  protected async resumeOrReplaceBinding(
    binding: AdapterBinding,
    input: {
      input: ExecuteAgentRunInput
      session: AgentSession
      adapter: RuntimeAdapter
      attempt: RunAttempt
      adapterId: string
    }
  ): Promise<AdapterBindingHandle & { replacesBindingId?: string }> {
    if (!this.isBindingCompatible(binding, input)) {
      this.markBindingStale(binding, input.attempt, 'binding_context_changed')
      const opened = await this.openNewBinding(input, binding.bindingGeneration + 1, binding.bindingId)
      return { ...opened.handle, replacesBindingId: opened.replacesBindingId }
    }
    const canUseProcessLocalBinding =
      binding.adapterInstanceId === this.runtimeNodeId &&
      binding.adapterNativeSessionId &&
      binding.resumeFidelity === 'none'
    if (
      !binding.adapterNativeSessionId ||
      (!input.adapter.capabilities.supportsNativeResume && !canUseProcessLocalBinding)
    ) {
      this.markBindingStale(binding, input.attempt, 'binding_not_resumable')
      const opened = await this.openNewBinding(input, binding.bindingGeneration + 1, binding.bindingId)
      return { ...opened.handle, replacesBindingId: opened.replacesBindingId }
    }
    try {
      const resumed = await input.adapter.resumeBinding({
        sessionId: input.session.sessionId,
        adapterNativeSessionId: binding.adapterNativeSessionId,
        cwd: input.input.cwd ?? binding.cwd ?? input.session.defaultCwd ?? process.cwd(),
        model: input.input.model ?? binding.modelId ?? undefined,
        systemPrompt: input.input.systemPrompt,
        mcpServers: mcpServersForBinding(
          input.input.mcpServers ?? [],
          input.session.sessionId,
          input.adapterId,
          this.runtimeNodeId
        ),
        metadata: {
          ...(input.input.metadata ?? {}),
          executionRole: input.session.executionRole,
          providerBoundary: input.session.providerBoundary
        }
      })
      this.withTransaction(() => {
        this.updateBinding(binding.bindingId, {
          adapterInstanceId: this.runtimeNodeId,
          cwd: input.input.cwd ?? binding.cwd ?? input.session.defaultCwd ?? null,
          modelId: input.input.model ?? binding.modelId ?? null,
          systemPromptHash: stableHash(input.input.systemPrompt),
          metadataJson: bindingMetadata(input.input, input.adapter),
          lastUsedAtMs: Date.now(),
          updatedAtMs: Date.now()
        })
        this.appendEvent({
          sessionId: input.session.sessionId,
          runId: input.attempt.runId,
          attemptId: input.attempt.attemptId,
          type: 'binding.resumed',
          payload: {
            bindingId: binding.bindingId,
            adapterId: input.adapterId,
            bindingGeneration: binding.bindingGeneration
          }
        })
      })
      return {
        ...resumed,
        bindingId: binding.bindingId,
        sessionId: input.session.sessionId,
        adapterId: input.adapterId
      }
    } catch (error) {
      this.markBindingStale(binding, input.attempt, messageFrom(error))
      throw new StaleAdapterBindingError(messageFrom(error))
    }
  }

  protected async openNewBinding(
    input: {
      input: ExecuteAgentRunInput
      session: AgentSession
      adapter: RuntimeAdapter
      attempt: RunAttempt
      adapterId: string
    },
    generation: number,
    replacesBindingId: string | null
  ): Promise<{ binding: AdapterBinding; handle: AdapterBindingHandle; replacesBindingId?: string }> {
    const opened = await input.adapter.openBinding({
      sessionId: input.session.sessionId,
      cwd: input.input.cwd ?? input.session.defaultCwd ?? process.cwd(),
      model: input.input.model,
      systemPrompt: input.input.systemPrompt,
      mcpServers: mcpServersForBinding(
        input.input.mcpServers ?? [],
        input.session.sessionId,
        input.adapterId,
        this.runtimeNodeId
      ),
      metadata: {
        ...(input.input.metadata ?? {}),
        executionRole: input.session.executionRole,
        providerBoundary: input.session.providerBoundary
      }
    })
    const binding = this.withTransaction(() => {
      this.closeConflictingNativeBinding(
        input.adapterId,
        opened.adapterNativeSessionId,
        input.attempt,
        'native_session_reused'
      )
      const created = this.store.insertAdapterBinding({
        sessionId: input.session.sessionId,
        adapterId: input.adapterId,
        bindingGeneration: generation,
        adapterNativeSessionId: opened.adapterNativeSessionId,
        adapterInstanceId: this.runtimeNodeId,
        resumeFidelity: opened.resumeFidelity,
        status: 'active',
        cwd: opened.cwd,
        modelId: opened.model ?? input.input.model ?? null,
        systemPromptHash: stableHash(input.input.systemPrompt),
        metadataJson: bindingMetadata(input.input, input.adapter),
        lastUsedAtMs: Date.now()
      })
      this.appendEvent({
        sessionId: input.session.sessionId,
        runId: input.attempt.runId,
        attemptId: input.attempt.attemptId,
        type: replacesBindingId ? 'binding.replaced' : 'binding.created',
        payload: {
          bindingId: created.bindingId,
          replacesBindingId,
          bindingGeneration: created.bindingGeneration,
          adapterId: input.adapterId,
          resumeFidelity: created.resumeFidelity
        }
      })
      return created
    })
    return {
      binding,
      replacesBindingId: replacesBindingId ?? undefined,
      handle: {
        ...opened,
        bindingId: binding.bindingId,
        sessionId: input.session.sessionId,
        adapterId: input.adapterId
      }
    }
  }

  protected markAttemptRunning(attempt: RunAttempt, binding: AdapterBinding): void {
    const run = this.readRun(attempt.runId)
    this.withTransaction(() => {
      this.updateRun(attempt.runId, { status: 'running', updatedAtMs: Date.now() })
      this.updateAttempt(attempt.attemptId, {
        status: 'running',
        bindingId: binding.bindingId,
        adapterInstanceId: this.runtimeNodeId,
        startedAtMs: Date.now(),
        updatedAtMs: Date.now()
      })
      this.appendEvent({
        sessionId: run.sessionId,
        runId: attempt.runId,
        attemptId: attempt.attemptId,
        type: 'attempt.started',
        payload: { attemptId: attempt.attemptId, bindingId: binding.bindingId }
      })
      this.appendEvent({
        sessionId: run.sessionId,
        runId: attempt.runId,
        attemptId: attempt.attemptId,
        type: 'run.running',
        payload: { runId: attempt.runId, attemptId: attempt.attemptId }
      })
    })
  }

  protected completeAttemptAndRun(
    session: AgentSession,
    runId: string,
    attempt: RunAttempt,
    binding: AdapterBinding,
    result: AdapterAttemptResult,
    turnRecord?: { conversationId: string | null; surfaceKind: string }
  ): KernelRunResult {
    const status = result.terminalStatus
    this.withTransaction(() => {
      this.updateBinding(binding.bindingId, {
        adapterNativeSessionId: result.adapterSessionId,
        lastUsedAtMs: Date.now(),
        updatedAtMs: Date.now()
      })
      const emittedArtifacts = result.artifacts ?? []
      const existingArtifacts = this.readArtifacts({ sessionId: session.sessionId, limit: 500 })
      const artifacts = [
        ...emittedArtifacts,
        ...(this.artifactStorage?.discoverRunArtifacts(
          {
            ownerId: session.ownerId,
            sessionId: session.sessionId,
            runId,
            attemptId: attempt.attemptId
          },
          [...emittedArtifacts, ...existingArtifacts]
        ) ?? [])
      ]
      for (const rawArtifact of artifacts) {
        const artifact =
          this.artifactStorage?.normalizeArtifact(rawArtifact, {
            ownerId: session.ownerId,
            sessionId: session.sessionId,
            runId,
            attemptId: attempt.attemptId
          }) ?? rawArtifact
        this.persistArtifactInTransaction({
          sessionId: session.sessionId,
          runId,
          attemptId: attempt.attemptId,
          kind: artifact.kind,
          role: artifact.role,
          uri: artifact.uri,
          displayName: artifact.displayName,
          mimeType: artifact.mimeType,
          contentHash: artifact.contentHash,
          sizeBytes: artifact.sizeBytes,
          metadata: artifact.metadata
        })
      }
      this.finishAttemptAndRun({
        sessionId: session.sessionId,
        runId,
        attemptId: attempt.attemptId,
        status,
        finalText: result.text,
        result,
        errorCode: status === 'failed' ? (result.failure?.code ?? 'adapter_execution_failed') : null,
        errorMessage: status === 'failed' ? (result.failure?.userMessage ?? null) : null,
        failure: result.failure
      })
      if (status === 'succeeded' && turnRecord?.conversationId && result.text.trim()) {
        appendConversationTurn(this.store, {
          conversationId: turnRecord.conversationId,
          role: 'assistant',
          surfaceKind: turnRecord.surfaceKind,
          content: result.text,
          createdAtMs: Date.now(),
          metadataJson: JSON.stringify({ runId })
        })
      }
    })
    return {
      session,
      run: this.readRun(runId),
      attempt: this.readAttempt(attempt.attemptId),
      artifacts: this.readArtifacts({ runId, limit: 50 }),
      adapterSessionId: result.adapterSessionId,
      terminalStatus: status,
      text: result.text
    }
  }

  protected inputWithManagedArtifactCwd(
    input: ExecuteAgentRunInput,
    session: AgentSession,
    runId: string,
    attemptId: string
  ): ExecuteAgentRunInput {
    if (!this.artifactStorage) {
      return input
    }
    const requestedCwd = input.cwd ?? session.defaultCwd
    if (requestedCwd && !this.artifactStorage.isRootDirectory(requestedCwd)) {
      return input
    }
    const cwd = this.artifactStorage.prepareRunDirectory({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId,
      attemptId
    })
    return { ...input, cwd }
  }

  protected finishAttemptAndRun(input: {
    sessionId: string
    runId: string
    attemptId: string
    status: AttemptStatus
    finalText: string | null
    result?: AdapterAttemptResult
    errorCode?: string | null
    errorMessage?: string | null
    failure?: RuntimeFailure | null
  }): void {
    const now = Date.now()
    const completedStatus = input.status
    this.updateAttempt(input.attemptId, {
      status: completedStatus,
      completedAtMs: now,
      errorCode: input.errorCode ?? null,
      errorMessage: input.errorMessage ?? null,
      updatedAtMs: now
    })
    this.updateRun(input.runId, {
      status: completedStatus,
      finalText: input.finalText,
      resultJson: input.result
        ? JSON.stringify(input.result)
        : input.failure
          ? JSON.stringify({ failure: input.failure })
          : null,
      errorCode: input.errorCode ?? null,
      errorMessage: input.errorMessage ?? null,
      inputTokens: input.result?.inputTokens ?? null,
      outputTokens: input.result?.outputTokens ?? null,
      cacheReadTokens: input.result?.cacheReadTokens ?? null,
      cacheWriteTokens: input.result?.cacheWriteTokens ?? null,
      costUsd: input.result?.costUsd ?? null,
      completedAtMs: now,
      updatedAtMs: now
    })
    if (completedStatus === 'failed' || completedStatus === 'cancelled') {
      this.appendEvent({
        sessionId: input.sessionId,
        runId: input.runId,
        attemptId: input.attemptId,
        type: completedStatus === 'failed' ? 'attempt.failed' : 'attempt.cancelled',
        payload: {
          attemptId: input.attemptId,
          status: completedStatus,
          failure: input.failure ?? input.result?.failure
        }
      })
    }
    if (completedStatus === 'succeeded') {
      this.appendEvent({
        sessionId: input.sessionId,
        runId: input.runId,
        attemptId: input.attemptId,
        type: 'message.completed',
        payload: { text: input.finalText ?? '' }
      })
      this.appendEvent({
        sessionId: input.sessionId,
        runId: input.runId,
        attemptId: input.attemptId,
        type: 'usage.updated',
        payload: {
          inputTokens: input.result?.inputTokens ?? null,
          outputTokens: input.result?.outputTokens ?? null,
          cacheReadTokens: input.result?.cacheReadTokens ?? null,
          cacheWriteTokens: input.result?.cacheWriteTokens ?? null,
          costUsd: input.result?.costUsd ?? null
        }
      })
    }
    this.appendEvent({
      sessionId: input.sessionId,
      runId: input.runId,
      attemptId: input.attemptId,
      type: `run.${completedStatus}`,
      payload: {
        runId: input.runId,
        status: completedStatus,
        failure: input.failure ?? input.result?.failure
      }
    })
  }

  protected failAttemptBeforeExecution(
    attempt: RunAttempt,
    errorCode: string,
    errorMessage: string,
    retryable: boolean,
    failure?: RuntimeFailure
  ): void {
    const run = this.readRun(attempt.runId)
    this.withTransaction(() => {
      this.updateAttempt(attempt.attemptId, {
        status: 'failed',
        retryable: retryable ? 1 : 0,
        completedAtMs: Date.now(),
        errorCode,
        errorMessage,
        updatedAtMs: Date.now()
      })
      if (!retryable) {
        this.updateRun(attempt.runId, {
          status: 'failed',
          errorCode,
          errorMessage,
          resultJson: failure ? JSON.stringify({ failure }) : null,
          completedAtMs: Date.now(),
          updatedAtMs: Date.now()
        })
        this.appendEvent({
          sessionId: run.sessionId,
          runId: attempt.runId,
          attemptId: attempt.attemptId,
          type: 'run.failed',
          payload: { runId: attempt.runId, errorCode, errorMessage, failure }
        })
      }
      this.appendEvent({
        sessionId: run.sessionId,
        runId: attempt.runId,
        attemptId: attempt.attemptId,
        type: 'attempt.failed',
        payload: { attemptId: attempt.attemptId, errorCode, errorMessage, retryable, failure }
      })
    })
  }

  protected async tryRecoverAttempt(
    input: ExecuteAgentRunInput,
    attempt: RunAttempt,
    error: unknown,
    errorCode: string,
    canRetry: boolean
  ): Promise<boolean> {
    if (!canRetry || !input.recoverAfterError) {
      return false
    }
    let recovered = false
    try {
      recovered = await input.recoverAfterError(error)
    } catch {
      return false
    }
    if (!recovered) {
      return false
    }
    const failure = failureFromError(error, {
      code: errorCode,
      source: 'adapter_process',
      adapterId: attempt.adapterId,
      retryable: true
    })
    this.failAttemptBeforeExecution(attempt, errorCode, failure.userMessage, true, failure)
    return true
  }

  protected persistAdapterEvent(
    sessionId: string,
    runId: string,
    attemptId: string,
    event: AdapterStreamEvent
  ): void {
    if (this.isTerminalAttempt(attemptId) || this.isTerminalRun(runId)) {
      return
    }
    const eventType = canonicalAdapterEventType(event)
    if (!eventType) {
      return
    }
    this.withTransaction(() => {
      if (this.isTerminalAttempt(attemptId) || this.isTerminalRun(runId)) {
        return
      }
      this.appendEvent({
        sessionId,
        runId,
        attemptId,
        type: eventType,
        retentionClass:
          event.type === 'text_delta' || event.type === 'thinking_delta' ? 'transient' : 'core',
        payload: event
      })
    })
  }

  protected closeConflictingNativeBinding(
    adapterId: string,
    adapterNativeSessionId: string | null | undefined,
    attempt: RunAttempt,
    reason: string
  ): void {
    if (!adapterNativeSessionId) {
      return
    }
    const row = this.store.getOptionalRow(
      `SELECT binding_id, session_id, status
       FROM adapter_bindings
       WHERE adapter_id = ? AND adapter_native_session_id = ? AND status NOT IN ('active', 'closed')
       ORDER BY updated_at_ms DESC
       LIMIT 1`,
      [adapterId, adapterNativeSessionId]
    )
    if (!row) {
      return
    }
    const now = Date.now()
    const bindingId = String(row.binding_id)
    this.updateBinding(bindingId, {
      status: 'closed',
      invalidatedAtMs: now,
      updatedAtMs: now
    })
    this.appendEvent({
      sessionId: String(row.session_id),
      runId: attempt.runId,
      attemptId: attempt.attemptId,
      type: 'binding.stale',
      payload: { bindingId, adapterId, adapterNativeSessionId, reason }
    })
  }

  protected markBindingStale(binding: AdapterBinding, attempt: RunAttempt, reason: string): void {
    const run = this.readRun(attempt.runId)
    this.withTransaction(() => {
      this.updateBinding(binding.bindingId, {
        status: 'stale',
        invalidatedAtMs: Date.now(),
        updatedAtMs: Date.now()
      })
      this.appendEvent({
        sessionId: run.sessionId,
        runId: attempt.runId,
        attemptId: attempt.attemptId,
        type: 'binding.stale',
        payload: { bindingId: binding.bindingId, reason }
      })
    })
  }

  protected markEvictedBindingStale(bindingId: string, reason: string): void {
    const binding = this.readBinding(bindingId)
    this.withTransaction(() => {
      this.updateBinding(binding.bindingId, {
        status: 'stale',
        invalidatedAtMs: Date.now(),
        updatedAtMs: Date.now()
      })
      this.appendEvent({
        sessionId: binding.sessionId,
        runId: null,
        attemptId: null,
        type: 'binding.stale',
        payload: { bindingId: binding.bindingId, reason }
      })
    })
  }

  protected persistArtifactInTransaction(input: PersistArtifactInput): AgentArtifact {
    const scope = this.resolveArtifactScope(input)
    const artifactInput: NewAgentArtifact = {
      artifactId: input.artifactId,
      sessionId: scope.sessionId,
      runId: scope.runId,
      attemptId: scope.attemptId,
      kind: input.kind,
      role: input.role,
      uri: input.uri,
      displayName: input.displayName ?? null,
      mimeType: input.mimeType ?? null,
      contentHash: input.contentHash ?? null,
      sizeBytes: input.sizeBytes ?? null,
      metadataJson: input.metadataJson ?? JSON.stringify(input.metadata ?? {}),
      createdAtMs: input.createdAtMs
    }
    const artifact = this.store.insertArtifact(artifactInput)
    this.appendEvent({
      sessionId: artifact.sessionId,
      runId: artifact.runId,
      attemptId: artifact.attemptId,
      type: 'artifact.created',
      payload: {
        artifactId: artifact.artifactId,
        kind: artifact.kind,
        role: artifact.role,
        uri: artifact.uri,
        displayName: artifact.displayName,
        mimeType: artifact.mimeType,
        contentHash: artifact.contentHash,
        sizeBytes: artifact.sizeBytes,
        lifecycleState: artifact.lifecycleState
      }
    })
    return artifact
  }

  protected resolveArtifactScope(input: PersistArtifactInput): {
    sessionId: string
    runId: string | null
    attemptId: string | null
  } {
    let sessionId = input.sessionId ?? null
    let runId = input.runId ?? null
    const attemptId = input.attemptId ?? null

    if (attemptId) {
      const attempt = this.readAttempt(attemptId)
      if (runId && runId !== attempt.runId) {
        throw new Error(
          `Artifact attempt ${attemptId} belongs to run ${attempt.runId}, not ${runId}`
        )
      }
      runId = attempt.runId
    }

    if (runId) {
      const run = this.readRun(runId)
      if (sessionId && sessionId !== run.sessionId) {
        throw new Error(
          `Artifact run ${runId} belongs to session ${run.sessionId}, not ${sessionId}`
        )
      }
      sessionId = run.sessionId
    }

    if (!sessionId) {
      throw new Error('Artifact persistence requires sessionId, runId, or attemptId')
    }

    return { sessionId, runId, attemptId }
  }

  protected appendEvent(input: {
    sessionId: string
    type: string
    runId?: string | null
    attemptId?: string | null
    retentionClass?: 'core' | 'transient'
    visibility?: 'ui' | 'internal'
    payload?: unknown
  }): AgentEvent {
    const event = this.store.appendEvent({
      sessionId: input.sessionId,
      runId: input.runId ?? null,
      attemptId: input.attemptId ?? null,
      type: input.type,
      retentionClass: input.retentionClass ?? 'core',
      visibility: input.visibility ?? 'ui',
      payloadJson: JSON.stringify(input.payload ?? {})
    })
    if (this.transactionDepth > 0) {
      this.pendingSubscriberEvents.push(event)
      return event
    }
    this.notifySubscribers(event)
    return event
  }

  protected withTransaction<T>(work: () => T): T {
    const pendingStart = this.pendingSubscriberEvents.length
    this.transactionDepth += 1
    let committed = false
    try {
      const result = this.store.withTransaction(work)
      committed = true
      return result
    } finally {
      this.transactionDepth -= 1
      if (!committed) {
        this.pendingSubscriberEvents.splice(pendingStart)
      }
      if (this.transactionDepth === 0) {
        const events = this.pendingSubscriberEvents
        this.pendingSubscriberEvents = []
        for (const event of events) {
          this.notifySubscribers(event)
        }
      }
    }
  }

  protected notifySubscribers(event: AgentEvent): void {
    for (const subscriber of this.subscribers) {
      try {
        subscriber(event)
      } catch {
        // Subscribers are observers; event persistence must not be rolled back
        // by UI/projection listener failures.
      }
    }
  }

  protected async withBindingResolutionLock<T>(
    sessionId: string,
    adapterId: string,
    work: () => Promise<T>
  ): Promise<T> {
    const key = `${sessionId}:${adapterId}`
    const previous = this.bindingResolutionLocks.get(key)
    let release!: () => void
    const current = new Promise<void>((resolve) => {
      release = resolve
    })
    const tail = previous ? previous.then(() => current, () => current) : current
    this.bindingResolutionLocks.set(key, tail)
    try {
      if (previous) {
        await previous.catch(() => undefined)
      }
      return await work()
    } finally {
      release()
      if (this.bindingResolutionLocks.get(key) === tail) {
        this.bindingResolutionLocks.delete(key)
      }
    }
  }

  protected readSession(sessionId: string): AgentSession {
    return sessionFromRow(
      this.store.getRow('SELECT * FROM sessions WHERE session_id = ?', [sessionId])
    )
  }

  protected readRun(runId: string): AgentRun {
    return runFromRow(this.store.getRow('SELECT * FROM runs WHERE run_id = ?', [runId]))
  }

  protected assertSessionOwner(session: AgentSession, ownerId: string): void {
    if (session.ownerId !== ownerId) {
      throw new Error('Agent session is not visible to the active owner')
    }
  }

  protected assertRunOwner(run: AgentRun, ownerId: string): void {
    this.assertSessionOwner(this.readSession(run.sessionId), ownerId)
  }

  protected assertAttemptOwner(attempt: RunAttempt, ownerId: string): void {
    this.assertRunOwner(this.readRun(attempt.runId), ownerId)
  }

  protected assertArtifactSelectorOwner(input: InspectArtifactsInput, ownerId: string): void {
    if (input.artifactId) {
      this.assertSessionOwner(
        this.readSession(this.readArtifact(input.artifactId).sessionId),
        ownerId
      )
    }
    if (input.sessionId) {
      this.assertSessionOwner(this.readSession(input.sessionId), ownerId)
    }
    if (input.runId) {
      this.assertRunOwner(this.readRun(input.runId), ownerId)
    }
    if (input.attemptId) {
      this.assertAttemptOwner(this.readAttempt(input.attemptId), ownerId)
    }
  }

  protected readLatestRunForSession(sessionId: string): AgentRun | undefined {
    const row = this.store.getOptionalRow(
      'SELECT * FROM runs WHERE session_id = ? ORDER BY created_at_ms DESC LIMIT 1',
      [sessionId]
    )
    return row ? runFromRow(row) : undefined
  }

  protected readActiveRunForSession(sessionId: string): AgentRun | undefined {
    const row = this.store.getOptionalRow(
      `SELECT * FROM runs WHERE session_id = ? AND status IN (${placeholders(ACTIVE_STATUSES.length)}) ORDER BY created_at_ms DESC LIMIT 1`,
      [sessionId, ...ACTIVE_STATUSES]
    )
    return row ? runFromRow(row) : undefined
  }

  protected readAttempt(attemptId: string): RunAttempt {
    return attemptFromRow(
      this.store.getRow('SELECT * FROM run_attempts WHERE attempt_id = ?', [attemptId])
    )
  }

  protected readLatestAttempt(runId: string): RunAttempt {
    return attemptFromRow(
      this.store.getRow(
        'SELECT * FROM run_attempts WHERE run_id = ? ORDER BY attempt_no DESC LIMIT 1',
        [runId]
      )
    )
  }

  protected readAttemptsForRun(runId: string): RunAttempt[] {
    return this.store
      .allRows('SELECT * FROM run_attempts WHERE run_id = ? ORDER BY attempt_no ASC', [runId])
      .map(attemptFromRow)
  }

  protected readActiveAttempt(runId: string): RunAttempt | undefined {
    const row = this.store.getOptionalRow(
      `SELECT * FROM run_attempts WHERE run_id = ? AND status IN (${placeholders(ACTIVE_STATUSES.length)}) ORDER BY attempt_no DESC LIMIT 1`,
      [runId, ...ACTIVE_STATUSES]
    )
    return row ? attemptFromRow(row) : undefined
  }

  protected readBinding(bindingId: string): AdapterBinding {
    return bindingFromRow(
      this.store.getRow('SELECT * FROM adapter_bindings WHERE binding_id = ?', [bindingId])
    )
  }

  protected readActiveBinding(sessionId: string, adapterId: string): AdapterBinding | undefined {
    const row = this.store.getOptionalRow(
      'SELECT * FROM adapter_bindings WHERE session_id = ? AND adapter_id = ? AND status = ?',
      [sessionId, adapterId, 'active']
    )
    return row ? bindingFromRow(row) : undefined
  }

  protected readLatestBinding(sessionId: string, adapterId: string): AdapterBinding | undefined {
    const row = this.store.getOptionalRow(
      'SELECT * FROM adapter_bindings WHERE session_id = ? AND adapter_id = ? ORDER BY binding_generation DESC LIMIT 1',
      [sessionId, adapterId]
    )
    return row ? bindingFromRow(row) : undefined
  }

  protected readBindingsForSession(sessionId: string): AdapterBinding[] {
    return this.store
      .allRows(
        'SELECT * FROM adapter_bindings WHERE session_id = ? ORDER BY adapter_id ASC, binding_generation DESC',
        [sessionId]
      )
      .map(bindingFromRow)
  }

  protected readEventsForRun(runId: string, limit: number): AgentEvent[] {
    return this.store
      .allRows('SELECT * FROM events WHERE run_id = ? ORDER BY event_seq ASC LIMIT ?', [
        runId,
        limit
      ])
      .map(eventFromRow)
  }

  protected readArtifacts(input: InspectArtifactsInput): AgentArtifact[] {
    const where: string[] = []
    const values: unknown[] = []
    if (input.artifactId) {
      where.push('artifact_id = ?')
      values.push(input.artifactId)
    }
    if (input.sessionId) {
      where.push('session_id = ?')
      values.push(input.sessionId)
    }
    if (input.runId) {
      where.push('run_id = ?')
      values.push(input.runId)
    }
    if (input.attemptId) {
      where.push('attempt_id = ?')
      values.push(input.attemptId)
    }
    if (input.role) {
      where.push('role = ?')
      values.push(input.role)
    }
    const limit = boundedLimit(input.limit, 50, 200)
    return this.store
      .allRows(
        `SELECT * FROM artifacts
         ${where.length ? `WHERE ${where.join(' AND ')}` : ''}
         ORDER BY created_at_ms DESC
         LIMIT ?`,
        [...values, limit]
      )
      .map(artifactFromRow)
  }

  protected readArtifact(artifactId: string): AgentArtifact {
    return artifactFromRow(
      this.store.getRow('SELECT * FROM artifacts WHERE artifact_id = ?', [artifactId])
    )
  }

  protected assertArtifactScope(
    artifact: AgentArtifact,
    input: Pick<UpdateArtifactLifecycleInput, 'sessionId' | 'runId' | 'attemptId'>
  ): void {
    if (input.sessionId && input.sessionId !== artifact.sessionId) {
      throw new Error(
        `Artifact ${artifact.artifactId} belongs to session ${artifact.sessionId}, not ${input.sessionId}`
      )
    }
    if (input.runId && input.runId !== artifact.runId) {
      throw new Error(
        `Artifact ${artifact.artifactId} belongs to run ${artifact.runId ?? 'none'}, not ${input.runId}`
      )
    }
    if (input.attemptId && input.attemptId !== artifact.attemptId) {
      throw new Error(
        `Artifact ${artifact.artifactId} belongs to attempt ${artifact.attemptId ?? 'none'}, not ${input.attemptId}`
      )
    }
  }

  protected readDelegation(delegationId: string): AgentDelegation {
    return delegationFromRow(
      this.store.getRow('SELECT * FROM delegations WHERE delegation_id = ?', [delegationId])
    )
  }

  protected readParentDelegationsForRun(runId: string): AgentDelegation[] {
    return this.store
      .allRows('SELECT * FROM delegations WHERE parent_run_id = ? ORDER BY created_at_ms ASC', [
        runId
      ])
      .map(delegationFromRow)
  }

  protected readChildDelegationsForRun(runId: string): AgentDelegation[] {
    return this.store
      .allRows('SELECT * FROM delegations WHERE child_run_id = ? ORDER BY created_at_ms ASC', [
        runId
      ])
      .map(delegationFromRow)
  }

  protected readDesktopDispatches(ownerId: string, limit: number): DesktopCoordinatorDispatch[] {
    return this.store
      .allRows(
        `SELECT * FROM desktop_dispatches
         WHERE owner_id = ?
         ORDER BY status = 'pending' DESC, priority DESC, created_at_ms DESC
         LIMIT ?`,
        [ownerId, limit]
      )
      .map(desktopDispatchFromRow)
  }

  protected readDesktopArtifactDeliveries(
    ownerId: string,
    limit: number
  ): DesktopArtifactDelivery[] {
    return this.store
      .allRows(
        `SELECT * FROM desktop_artifact_deliveries
         WHERE owner_id = ?
         ORDER BY updated_at_ms DESC
         LIMIT ?`,
        [ownerId, limit]
      )
      .map(desktopArtifactDeliveryFromRow)
  }

  protected readDesktopMemoryCandidates(ownerId: string, limit: number): DesktopMemoryCandidate[] {
    return this.store
      .allRows(
        `SELECT * FROM desktop_memory_candidates
         WHERE owner_id = ?
         ORDER BY status = 'pending' DESC, created_at_ms DESC
         LIMIT ?`,
        [ownerId, limit]
      )
      .map(desktopMemoryCandidateFromRow)
  }

  protected readDesktopTaskCandidates(ownerId: string, limit: number): DesktopTaskCandidate[] {
    return this.store
      .allRows(
        `SELECT * FROM desktop_task_candidates
         WHERE owner_id = ?
         ORDER BY status = 'pending' DESC, created_at_ms DESC
         LIMIT ?`,
        [ownerId, limit]
      )
      .map(desktopTaskCandidateFromRow)
  }

  protected readDesktopAttentionOverrides(ownerId: string): DesktopAttentionOverride[] {
    return this.store
      .allRows('SELECT * FROM desktop_attention_overrides WHERE owner_id = ?', [ownerId])
      .map(desktopAttentionOverrideFromRow)
  }

  protected readDesktopQueueRuns(ownerId: string, limit: number): QueueRunInput[] {
    return this.store
      .allRows(
        `SELECT r.*, s.owner_id, s.title, s.external_ref_kind, s.external_ref_id
         FROM runs r
         JOIN sessions s ON s.session_id = r.session_id
         WHERE s.owner_id = ?
         ORDER BY r.updated_at_ms DESC
         LIMIT ?`,
        [ownerId, limit]
      )
      .map((row) => ({
        runId: stringValue(row.run_id),
        sessionId: stringValue(row.session_id),
        ownerId: stringValue(row.owner_id),
        status: stringValue(row.status) as RunStatus,
        title: nullableString(row.title),
        goalText: queueRunGoalText(row),
        completedAtMs: nullableNumber(row.completed_at_ms),
        updatedAtMs: numberValue(row.updated_at_ms),
        createdAtMs: numberValue(row.created_at_ms),
        visibleUserGoal: true,
        reusable:
          stringValue(row.status) === 'succeeded' || stringValue(row.status) === 'cancelled'
      }))
  }

  protected desktopIntentSessionCandidates(
    ownerId: string,
    surfaceKind: string,
    taskId: string | null
  ): DesktopIntentSessionCandidate[] {
    const rows = this.store.allRows(
      `SELECT s.*, r.run_id, r.status AS run_status, r.updated_at_ms AS run_updated_at_ms
       FROM sessions s
       LEFT JOIN runs r ON r.run_id = (
         SELECT run_id FROM runs latest
         WHERE latest.session_id = s.session_id
         ORDER BY latest.updated_at_ms DESC
         LIMIT 1
       )
       WHERE s.owner_id = ?
       ORDER BY s.last_activity_at_ms DESC
       LIMIT 50`,
      [ownerId]
    )
    return rows.map((row) => {
      const candidateTaskId =
        nullableString(row.external_ref_kind) === 'task' ? nullableString(row.external_ref_id) : null
      const runStatus = nullableString(row.run_status)
      const runUpdatedAtMs = numberValue(row.run_updated_at_ms)
      const staleAfterMs = 30 * 60 * 1000
      const relevance =
        taskId && candidateTaskId === taskId
          ? 1
          : stringValue(row.surface_kind) === surfaceKind
            ? 0.7
            : 0.2
      return {
        sessionId: stringValue(row.session_id),
        runId: nullableString(row.run_id),
        surfaceKind: stringValue(row.surface_kind),
        taskId: candidateTaskId,
        title: nullableString(row.title),
        status: intentCandidateStatus(runStatus, runUpdatedAtMs, Date.now(), staleAfterMs),
        relevance,
        lastActivityAtMs: numberValue(row.last_activity_at_ms)
      }
    })
  }

  protected delegationDepth(parentRunId: string): number {
    const row = this.store.getRow(
      `WITH RECURSIVE ancestors(run_id, depth) AS (
         SELECT ?, 0
         UNION ALL
         SELECT r.parent_run_id, ancestors.depth + 1
         FROM runs r
         JOIN ancestors ON r.run_id = ancestors.run_id
         WHERE r.parent_run_id IS NOT NULL
       )
       SELECT COALESCE(MAX(depth), 0) AS depth FROM ancestors`,
      [parentRunId]
    )
    return Number(row.depth)
  }

  protected nextBindingGeneration(sessionId: string, adapterId: string): number {
    const row = this.store.getRow(
      'SELECT COALESCE(MAX(binding_generation), 0) AS max_generation FROM adapter_bindings WHERE session_id = ? AND adapter_id = ?',
      [sessionId, adapterId]
    )
    return Number(row.max_generation) + 1
  }

  protected runStatus(runId: string): RunStatus {
    return String(
      this.store.getRow('SELECT status FROM runs WHERE run_id = ?', [runId]).status
    ) as RunStatus
  }

  protected isTerminalRun(runId: string): boolean {
    return TERMINAL_STATUSES.includes(this.runStatus(runId))
  }

  protected isTerminalAttempt(attemptId: string): boolean {
    const status = String(
      this.store.getRow('SELECT status FROM run_attempts WHERE attempt_id = ?', [attemptId]).status
    ) as AttemptStatus
    return TERMINAL_STATUSES.includes(status)
  }

  protected touchSession(sessionId: string): void {
    this.store.execute(
      'UPDATE sessions SET updated_at_ms = ?, last_activity_at_ms = ? WHERE session_id = ?',
      [Date.now(), Date.now(), sessionId]
    )
    this.appendEvent({
      sessionId,
      type: 'session.updated',
      payload: { sessionId }
    })
  }

  protected updateRun(runId: string, patch: Partial<AgentRun>): void {
    updateByColumns(this.store, 'runs', 'run_id', runId, runColumnMap, patch)
  }

  protected updateAttempt(attemptId: string, patch: Partial<RunAttempt>): void {
    updateByColumns(this.store, 'run_attempts', 'attempt_id', attemptId, attemptColumnMap, patch)
  }

  protected updateBinding(bindingId: string, patch: Partial<AdapterBinding>): void {
    updateByColumns(this.store, 'adapter_bindings', 'binding_id', bindingId, bindingColumnMap, patch)
  }
}
