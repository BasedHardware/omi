import type {
  AdapterAttemptResult,
  AdapterBindingHandle,
  CancelDispatchResult,
  OpenedBinding,
  RuntimeAdapter,
} from "../adapters/interface.js";
import type { OutboundMessage } from "../protocol.js";
import { AdapterRegistry } from "./adapter-registry.js";
import { AdapterRuntimeError, failureFromError } from "./failures.js";
import {
  clearOwnerSurfaceState,
  importLegacyMainChatSessions,
  resolveSurfaceSession,
  type LegacyMainChatSessionEntry,
  type LegacyMainChatSessionImportReceipt,
  type ResolveSurfaceSessionInput,
  type ResolveSurfaceSessionResult,
} from "./surface-session.js";
import type {
  AdapterBinding,
  AgentArtifact,
  AgentDelegation,
  AgentRun,
  AgentSession,
  AgentStore,
  AgentGrant,
  NewAgentArtifact,
  NewAgentGrant,
  RunAttempt,
  RunStatus,
  DelegationStatus,
  DesktopAttentionOverride,
  NewDesktopCoordinatorDispatch,
} from "./types.js";
import { buildDesktopActionQueue } from "./desktop-action-queue.js";
import { buildDesktopContextPacket, type DesktopContextPacketBuildInput } from "./desktop-context-packet.js";
import { OmiArtifactStorage } from "./artifact-storage.js";
import { writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import {
  ACTIVE_STATUSES,
  TERMINAL_STATUSES,
  DEFAULT_DELEGATION_MAX_DEPTH,
  HARD_DELEGATION_MAX_DEPTH,
  DEFAULT_DELEGATION_MAX_BUDGET_USD,
  HARD_DELEGATION_MAX_BUDGET_USD,
  requiresVerifiedContextDispatch,
  bindingMetadata,
  stableHash,
  stableJsonStringify,
  stableMcpServerConfig,
  stableJsonHash,
  parseJsonObject,
  placeholders,
  isStaleBindingError,
  messageFrom,
  boundedLimit,
  sessionFromRow,
  runFromRow,
  delegationFromRow,
  delegationValues,
  buildDelegatedPrompt,
  requiredChildSessionId,
  attemptFromRow,
  bindingFromRow,
  eventFromRow,
  artifactFromRow,
  desktopDispatchFromRow,
  desktopArtifactDeliveryFromRow,
  desktopMemoryCandidateFromRow,
  desktopTaskCandidateFromRow,
  desktopAttentionOverrideFromRow,
  dispatchToQueueInput,
  deliveryToQueueInput,
  memoryCandidateToQueueInput,
  taskCandidateToQueueInput,
  overrideToQueueInput,
  intentCandidateStatus,
  updateByColumns,
  queueRunGoalText,
  stringValue,
  numberValue,
  nullableString,
  nullableNumber,
  nullableText,
  text,
} from "./kernel-support.js";
import type {
  KernelSessionResolutionInput,
  ExecuteAgentRunInput,
  KernelRunResult,
  CancelRunResult,
  ListSessionsInput,
  KernelSessionSummary,
  GetRunInput,
  KernelRunDetails,
  InspectArtifactsInput,
  DesktopAwarenessSnapshotInput,
  DesktopAwarenessSnapshot,
  DesktopActionQueueInput,
  DesktopOpenLoopsInput,
  DesktopContextPacketPersistInput,
  ResolveDesktopDispatchInput,
  ResolveDesktopDispatchResult,
  UpdateArtifactLifecycleInput,
  UpdateArtifactLifecycleResult,
  PersistArtifactInput,
  InvalidateBindingsInput,
  InvalidateBindingsResult,
  StaleProcessLocalBindingsInput,
  StaleProcessLocalBindingsResult,
  SendAgentMessageInput,
  SpawnBackgroundAgentInput,
  SpawnBackgroundAgentResult,
  DelegateAgentInput,
  DelegateAgentResult,
  KernelEventSubscriber,
  AgentRuntimeKernelOptions,
} from "./kernel-types.js";
import { StaleAdapterBindingError } from "./kernel-types.js";

import { KernelArtifacts } from "./kernel-artifacts.js";
import {
  configureDefaultExecutionProfile,
  migrateSessionExecutionProfile,
  readDefaultExecutionProfilePreference,
  readSessionExecutionProfile,
  type MigrateSessionExecutionProfileInput,
  type MigrateSessionExecutionProfileResult,
} from "./session-execution-profile.js";
import type { DefaultExecutionProfilePreference, SessionExecutionProfile } from "./types.js";
import {
  buildContextSnapshot,
  updateContextSource,
  type ContextSourceUpdateInput,
  type ContextSourceUpdateResult,
} from "./context-snapshot.js";
import type { ContextSnapshotProjection } from "../protocol.js";
import type { ChatFirstCapabilityProjection } from "./chat-first-capability.js";
import {
  ensureAgentSpawnJournal,
  type EnsureAgentSpawnJournalInput,
  type EnsureAgentSpawnJournalResult,
} from "./agent-spawn-journal.js";
import { conversationIdForSession } from "./conversation-turns.js";
import type { AuthorizedRunToolInvocation } from "./run-tool-capability.js";

export class KernelSessions extends KernelArtifacts {
  /** Process-local only: never back this with SQLite or a user preference. */
  private readonly chatFirstCapabilities = new Map<string, ChatFirstCapabilityProjection>();

  private chatFirstCapability(sessionId: string, ownerId: string, surfaceKind?: string): ChatFirstCapabilityProjection | undefined {
    if (surfaceKind !== "main_chat") return undefined;
    return this.chatFirstCapabilities.get(`${ownerId}:${sessionId}`);
  }
  ownedSession(sessionId: string, ownerId: string): AgentSession {
    const session = this.readSession(sessionId);
    this.assertSessionOwner(session, ownerId);
    return session;
  }

  /**
   * T08 is not a model-tool invocation, but it still needs the same immutable
   * server-derived Main Chat capability that admitted rich blocks. Keeping the
   * check here avoids a second Swift or UI-side rollout gate.
   */
  assertChatFirstMainCapability(sessionId: string, ownerId: string, controlGeneration: number): void {
    this.ownedSession(sessionId, ownerId);
    const capability = this.chatFirstCapability(sessionId, ownerId, "main_chat");
    if (
      capability?.chatFirstUi !== true
      || capability.controlGeneration !== controlGeneration
    ) {
      throw new Error("Question interaction requires an enabled current main-Chat capability");
    }
  }

  /**
   * Background chat-first work is permitted only while this process has an
   * immutable, enabled Main Chat projection for the active owner. It is not a
   * persisted rollout flag: a fresh capability-off launch therefore leaves
   * deferral rows dormant instead of delivering feature work to a legacy user.
   */
  hasChatFirstMainCapability(ownerId: string): boolean {
    for (const [key, capability] of this.chatFirstCapabilities) {
      if (key.startsWith(`${ownerId}:`) && capability.chatFirstUi === true) return true;
    }
    return false;
  }

  defaultExecutionProfilePreference(ownerId: string): DefaultExecutionProfilePreference | undefined {
    return readDefaultExecutionProfilePreference(this.store, ownerId);
  }

  configureDefaultExecutionProfile(input: {
    ownerId: string;
    adapterId: string;
    modelProfile: string | null;
    workingDirectory: string;
    expectedPreferenceGeneration?: number;
  }): DefaultExecutionProfilePreference {
    return configureDefaultExecutionProfile(this.store, input, Date.now());
  }

  contextSnapshot(sessionId: string, ownerId: string, surfaceKind?: string): ContextSnapshotProjection {
    return buildContextSnapshot(
      this.store,
      sessionId,
      ownerId,
      Date.now(),
      surfaceKind,
      this.chatFirstCapability(sessionId, ownerId, surfaceKind),
    );
  }

  /**
   * Local/offline E2E admission for the real `render_chat_blocks` executor.
   * Session ownership and the ephemeral rollout projection both belong to this
   * session layer, so the probe cannot manufacture either one from its input.
   */
  beginChatFirstHarnessExecutor(input: {
    ownerId: string;
    sessionId: string;
    producingTurnId: string;
    controlGeneration: number;
    clientId: string;
    requestId: string;
    toolInput: Record<string, unknown>;
  }): AuthorizedRunToolInvocation {
    const session = this.ownedSession(input.sessionId, input.ownerId);
    if (session.surfaceKind !== "main_chat") {
      throw new Error("Chat-first E2E executor requires an existing main Chat session");
    }
    const admitted = this.contextSnapshot(input.sessionId, input.ownerId, "main_chat");
    if (
      admitted.capabilities.chatFirstUi !== true
      || admitted.capabilities.chatFirstControlGeneration !== input.controlGeneration
      || !admitted.capabilities.allowedToolNames.includes("render_chat_blocks")
    ) {
      throw new Error("Chat-first E2E executor requires the mounted server-derived capability");
    }
    const accepted = this.createAcceptedRun({
      sessionId: input.sessionId,
      ownerId: input.ownerId,
      surfaceKind: "main_chat",
      clientId: input.clientId,
      requestId: input.requestId,
      producingTurnId: input.producingTurnId,
      prompt: "Local Chat-first executor probe",
      mode: "ask",
      admittedContextSnapshot: admitted,
    });
    const conversationId = conversationIdForSession(this.store, accepted.session.sessionId);
    if (!conversationId) throw new Error("Chat-first E2E executor requires a canonical Chat conversation");
    const attempt = this.createAttempt({
      runId: accepted.run.runId,
      attemptNo: 1,
      adapterId: accepted.session.defaultAdapterId,
      retryReason: null,
      resumeFromAttemptId: null,
      producingTurn: {
        ownerId: accepted.session.ownerId,
        sessionId: accepted.session.sessionId,
        conversationId,
        turnId: input.producingTurnId,
      },
    });
    const capability = this.toolCapabilities.register({
      ownerId: accepted.session.ownerId,
      sessionId: accepted.session.sessionId,
      runId: accepted.run.runId,
      attemptId: attempt.attemptId,
    });
    const invocation = this.toolCapabilities.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: `chat_first_e2e_${accepted.run.runId}`,
      runId: accepted.run.runId,
      attemptId: attempt.attemptId,
      toolName: "render_chat_blocks",
      toolInput: input.toolInput,
      activeOwnerId: input.ownerId,
    });
    if (
      invocation.canonicalToolName !== "render_chat_blocks"
      || invocation.surfaceKind !== "main_chat"
      || invocation.chatFirstUi !== true
      || invocation.chatFirstControlGeneration !== input.controlGeneration
    ) {
      throw new Error("Chat-first E2E executor did not receive the authorized main-Chat tool");
    }
    this.markRunToolInvocationDispatched(invocation);
    return invocation;
  }

  completeChatFirstHarnessExecutor(input: {
    ownerId: string;
    sessionId: string;
    runId: string;
    attemptId: string;
    succeeded: boolean;
  }): void {
    const session = this.ownedSession(input.sessionId, input.ownerId);
    const run = this.readRun(input.runId);
    const attempt = this.readAttempt(input.attemptId);
    if (
      session.surfaceKind !== "main_chat"
      || run.sessionId !== session.sessionId
      || attempt.runId !== run.runId
      || this.readLatestAttempt(run.runId).attemptId !== attempt.attemptId
    ) {
      throw new Error("Chat-first E2E executor completion does not own the active run");
    }
    const pendingInvocations = Number(this.store.getRow(
      `SELECT COUNT(*) AS count FROM tool_invocation_ledger
       WHERE run_id = ? AND attempt_id = ? AND status IN ('prepared', 'dispatched')`,
      [input.runId, input.attemptId],
    ).count);
    if (pendingInvocations > 0) {
      throw new Error("Chat-first E2E executor cannot finish while its tool invocation is pending");
    }
    this.withTransaction(() => {
      this.finishAttemptAndRun({
        sessionId: input.sessionId,
        runId: input.runId,
        attemptId: input.attemptId,
        status: input.succeeded ? "succeeded" : "failed",
        finalText: null,
        errorCode: input.succeeded ? null : "chat_first_e2e_executor_failed",
        errorMessage: input.succeeded ? null : "Chat-first E2E executor failed",
      });
    });
  }

  contextSnapshotForExactSurface(
    ownerId: string,
    surface: { surfaceKind: string; externalRefKind: string; externalRefId: string },
  ): ContextSnapshotProjection {
    const mapping = this.store.getRow(
      `SELECT agent_session_id FROM surface_conversations
       WHERE owner_id = ? AND surface_kind = ? AND external_ref_kind = ? AND external_ref_id = ?`,
      [ownerId, surface.surfaceKind, surface.externalRefKind, surface.externalRefId],
    );
    const sessionId = String(mapping.agent_session_id);
    return buildContextSnapshot(
      this.store,
      sessionId,
      ownerId,
      Date.now(),
      surface.surfaceKind,
      this.chatFirstCapability(sessionId, ownerId, surface.surfaceKind),
    );
  }

  updateContextSource(input: ContextSourceUpdateInput): ContextSourceUpdateResult {
    return updateContextSource(this.store, {
      ...input,
      chatFirstCapability: this.chatFirstCapability(input.sessionId, input.ownerId, input.surfaceKind),
    });
  }

  ensureAgentSpawnJournal(input: EnsureAgentSpawnJournalInput): EnsureAgentSpawnJournalResult {
    return ensureAgentSpawnJournal(this.store, input);
  }

  sessionExecutionProfile(sessionId: string, ownerId: string): SessionExecutionProfile {
    const session = this.readSession(sessionId);
    this.assertSessionOwner(session, ownerId);
    return readSessionExecutionProfile(this.store, sessionId);
  }

  migrateSessionExecutionProfile(
    input: MigrateSessionExecutionProfileInput,
  ): MigrateSessionExecutionProfileResult {
    return this.withTransaction(() => {
      const result = migrateSessionExecutionProfile(this.store, input, Date.now());
      this.appendEvent({
        sessionId: input.sessionId,
        type: "session.execution_profile_migrated",
        payload: {
          previousGeneration: result.previous.generation,
          profileGeneration: result.profile.generation,
          adapterId: result.profile.adapterId,
          executionRole: result.profile.executionRole,
          staleBindingIds: result.staleBindingIds,
          reason: input.reason,
        },
      });
      return result;
    });
  }

  executionPolicyForSession(sessionId: string): Pick<AgentSession, "executionRole" | "providerBoundary" | "defaultAdapterId"> {
    const session = this.readSession(sessionId);
    return {
      executionRole: session.executionRole,
      providerBoundary: session.providerBoundary,
      defaultAdapterId: session.defaultAdapterId,
    };
  }

  executionPolicyForOwnedSession(
    sessionId: string,
    ownerId: string,
  ): Pick<AgentSession, "executionRole" | "providerBoundary" | "defaultAdapterId"> {
    const session = this.readSession(sessionId);
    this.assertSessionOwner(session, ownerId);
    return {
      executionRole: session.executionRole,
      providerBoundary: session.providerBoundary,
      defaultAdapterId: session.defaultAdapterId,
    };
  }

  listSessions(input: ListSessionsInput = {}): KernelSessionSummary[] {
    const where: string[] = [];
    const values: unknown[] = [];
    if (input.ownerId) {
      where.push("owner_id = ?");
      values.push(input.ownerId);
    }
    if (input.status) {
      where.push("status = ?");
      values.push(input.status);
    }
    if (input.surfaceKind) {
      where.push("surface_kind = ?");
      values.push(input.surfaceKind);
    }
    if (input.executionRole) {
      where.push("execution_role = ?");
      values.push(input.executionRole);
    }
    if (input.beforeUpdatedAtMs !== undefined) {
      where.push("updated_at_ms < ?");
      values.push(input.beforeUpdatedAtMs);
    }
    const limit = boundedLimit(input.limit, 50, 200);
    const sessions = this.store
      .allRows(
        `SELECT * FROM sessions
         ${where.length ? `WHERE ${where.join(" AND ")}` : ""}
         ORDER BY last_activity_at_ms DESC, created_at_ms DESC
         LIMIT ?`,
        [...values, limit],
      )
      .map((row) => this.readSession(String(row.session_id)));

    return sessions.map((session) => ({
      session,
      latestRun: this.readLatestRunForSession(session.sessionId),
      activeRun: this.readActiveRunForSession(session.sessionId),
      adapterBindings: this.readBindingsForSession(session.sessionId),
    }));
  }
  resolveSurfaceSession(input: ResolveSurfaceSessionInput & { chatFirstCapability?: ChatFirstCapabilityProjection }): ResolveSurfaceSessionResult {
    const capability = input.chatFirstCapability;
    const { chatFirstCapability: _ignored, ...sessionInput } = input;
    const resolved = resolveSurfaceSession(this.store, sessionInput, () => Date.now());
    if (input.surfaceRef.surfaceKind !== "main_chat") return resolved;
    if (capability && (!Number.isSafeInteger(capability.controlGeneration) || capability.controlGeneration < 0)) {
      throw new Error("chat-first capability requires a non-negative control generation");
    }
    // Capability-less lookups can happen while auth and root-shell control are
    // still converging (for example, a journal projection read during startup).
    // They remain capability-off for that read, but must not consume the one
    // immutable server-derived sample for the runtime session.
    if (capability === undefined) return resolved;
    const key = `${input.ownerId}:${resolved.agentSessionId}`;
    const previous = this.chatFirstCapabilities.get(key);
    const sampled: ChatFirstCapabilityProjection = capability;
    if (
      previous
      && (previous.chatFirstUi !== sampled.chatFirstUi || previous.controlGeneration !== sampled.controlGeneration)
    ) {
      throw new Error("chat-first capability is immutable for the runtime session");
    }
    if (!previous) this.chatFirstCapabilities.set(key, Object.freeze({ ...sampled }));
    return resolved;
  }

  importLegacyMainChatSessions(
    input: { ownerId: string; entries: LegacyMainChatSessionEntry[] },
  ): LegacyMainChatSessionImportReceipt {
    return importLegacyMainChatSessions(this.store, input, () => Date.now());
  }

  clearOwnerState(ownerId: string): { invalidatedBindingIds: string[] } {
    for (const key of this.chatFirstCapabilities.keys()) {
      if (key.startsWith(`${ownerId}:`)) this.chatFirstCapabilities.delete(key);
    }
    return clearOwnerSurfaceState(this.store, ownerId, () => Date.now());
  }

  invalidateBindings(input: InvalidateBindingsInput): InvalidateBindingsResult {
    const session = this.findExistingSession(input);
    const sessionIds = session ? [session.sessionId] : this.findInvalidationSessionIds(input);
    if (sessionIds.length === 0) {
      return { invalidatedBindingIds: [] };
    }

    const rows = this.store.allRows(
      `SELECT binding_id, session_id
       FROM adapter_bindings
       WHERE session_id IN (${placeholders(sessionIds.length)})
         AND status = ?
         ${input.adapterId ? "AND adapter_id = ?" : ""}`,
      input.adapterId ? [...sessionIds, "active", input.adapterId] : [...sessionIds, "active"],
    );
    const invalidatedBindingIds = rows.map((row) => String(row.binding_id));
    if (invalidatedBindingIds.length === 0) {
      return { sessionId: session?.sessionId, invalidatedBindingIds };
    }

    const now = Date.now();
    this.withTransaction(() => {
      for (const bindingId of invalidatedBindingIds) {
        this.updateBinding(bindingId, {
          status: "invalid",
          invalidatedAtMs: now,
          updatedAtMs: now,
        });
        this.appendEvent({
          sessionId: String(rows.find((row) => String(row.binding_id) === bindingId)?.session_id),
          runId: null,
          attemptId: null,
          type: "binding.stale",
          payload: {
            bindingId,
            adapterId: input.adapterId,
            reason: input.reason ?? "invalidate_session",
          },
        });
      }
    });

    return { sessionId: session?.sessionId, invalidatedBindingIds };
  }

  staleProcessLocalBindings(input: StaleProcessLocalBindingsInput): StaleProcessLocalBindingsResult {
    const rows = this.store.allRows(
      `SELECT binding_id, session_id
       FROM adapter_bindings
       WHERE adapter_id = ?
         AND resume_fidelity = ?
         AND status = ?`,
      [input.adapterId, "none", "active"],
    );
    const staleBindingIds = rows.map((row) => String(row.binding_id));
    if (staleBindingIds.length === 0) {
      return { staleBindingIds };
    }

    const now = Date.now();
    this.withTransaction(() => {
      for (const row of rows) {
        const bindingId = String(row.binding_id);
        this.updateBinding(bindingId, {
          status: "stale",
          invalidatedAtMs: now,
          updatedAtMs: now,
        });
        this.appendEvent({
          sessionId: String(row.session_id),
          runId: null,
          attemptId: null,
          type: "binding.stale",
          payload: {
            bindingId,
            adapterId: input.adapterId,
            reason: input.reason,
          },
        });
      }
    });

    return { staleBindingIds };
  }
}
