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
  mergeFloatingChatIntoMainChat,
  resolveSurfaceSession,
  type LegacyMainChatSessionEntry,
  type ResolveSurfaceSessionInput,
  type ResolveSurfaceSessionResult,
  type SurfaceRef,
} from "./surface-session.js";
import {
  appendConversationTurn,
  clearOwnerMainChatTurns,
  conversationIdForSession,
  getMainChatTurnTail,
  importConversationTurnsForSurface,
  projectCrossSurfaceTurn,
  recordSurfaceTurn as persistSurfaceTurn,
  type ConversationTurnImportEntry,
  type RecordSurfaceTurnResult,
} from "./conversation-turns.js";
import {
  acknowledgeCompletionDelta,
  assembleTurnContext,
  bindingCarriesNativeHistory,
  getVoiceSeedContext,
  getVoiceSeedSnapshot,
} from "./turn-context.js";
import type {
  AdapterBinding,
  AgentArtifact,
  AgentDelegation,
  AgentRun,
  AgentSession,
  AgentStore,
  AgentGrant,
  ConversationTurn,
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
import { routeDesktopIntent } from "./desktop-intent-router.js";
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

export class KernelSessions extends KernelArtifacts {
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
      .map(sessionFromRow);

    return sessions.map((session) => ({
      session,
      latestRun: this.readLatestRunForSession(session.sessionId),
      activeRun: this.readActiveRunForSession(session.sessionId),
      adapterBindings: this.readBindingsForSession(session.sessionId),
    }));
  }
  resolveSurfaceSession(input: ResolveSurfaceSessionInput): ResolveSurfaceSessionResult {
    return resolveSurfaceSession(this.store, input, () => Date.now());
  }

  importLegacyMainChatSessions(input: { ownerId: string; entries: LegacyMainChatSessionEntry[] }): number {
    return importLegacyMainChatSessions(this.store, input, () => Date.now());
  }

  mergeFloatingChatIntoMainChat(input: { ownerId: string; chatId?: string }): {
    mergedTurns: number;
    removedFloatingMapping: boolean;
  } {
    return mergeFloatingChatIntoMainChat(this.store, input, () => Date.now());
  }

  importConversationTurns(input: {
    ownerId: string;
    surfaceRef: SurfaceRef;
    turns: ConversationTurnImportEntry[];
  }): number {
    return importConversationTurnsForSurface(this.store, {
      ownerId: input.ownerId,
      surfaceRef: input.surfaceRef,
      turns: input.turns,
      nowMs: () => Date.now(),
    });
  }

  recordSurfaceTurn(input: {
    ownerId: string;
    surfaceRef: SurfaceRef;
    userText: string;
    assistantText: string;
    origin: string;
    interrupted?: boolean;
    idempotencyKey?: string;
  }): RecordSurfaceTurnResult {
    return this.withTransaction(() =>
      persistSurfaceTurn(this.store, {
        ...input,
        nowMs: Date.now(),
      }),
    );
  }

  getVoiceSeedContext(input: { conversationId: string }): string {
    return getVoiceSeedContext(this.store, input.conversationId);
  }

  getVoiceSeedSnapshot(input: { conversationId: string }): {
    context: string;
    idempotencyKeys: string[];
  } {
    return getVoiceSeedSnapshot(this.store, input.conversationId);
  }

  getVoiceSeedContextForSurface(input: { ownerId: string; surfaceRef: SurfaceRef }): {
    conversationId: string;
    context: string;
    idempotencyKeys: string[];
  } {
    const resolved = resolveSurfaceSession(this.store, input, () => Date.now());
    const snapshot = getVoiceSeedSnapshot(this.store, resolved.conversationId);
    return {
      conversationId: resolved.conversationId,
      context: snapshot.context,
      idempotencyKeys: snapshot.idempotencyKeys,
    };
  }

  clearOwnerState(ownerId: string): { invalidatedBindingIds: string[] } {
    return clearOwnerSurfaceState(this.store, ownerId, () => Date.now());
  }

  clearOwnerMainChatTurns(ownerId: string, chatId = "default"): {
    conversationId: string | null;
    deletedTurns: number;
  } {
    return clearOwnerMainChatTurns(this.store, ownerId, chatId);
  }

  getMainChatTurnTail(ownerId: string, limit = 8, chatId = "default"): {
    conversationId: string | null;
    turns: ConversationTurn[];
  } {
    return getMainChatTurnTail(this.store, ownerId, limit, chatId);
  }

  projectCrossSurfaceTurn(input: {
    ownerId: string;
    targetSurfaceRef?: SurfaceRef;
    userText: string;
    assistantText: string;
    origin: string;
    idempotencyKey?: string;
  }): RecordSurfaceTurnResult {
    return this.withTransaction(() =>
      projectCrossSurfaceTurn(this.store, {
        ...input,
        nowMs: Date.now(),
      }),
    );
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
