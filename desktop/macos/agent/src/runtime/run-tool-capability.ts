import { randomUUID } from "node:crypto";

import type { OmiToolAdapterId, OmiToolManifestEntry } from "./omi-tool-manifest.js";
import {
  buildToolAvailabilitySnapshot,
  normalizeOmiToolName,
  toolManifestEntry,
  toolsForAdapter,
} from "./omi-tool-manifest.js";
import { executionRoleAllowsTool, type AgentExecutionRole } from "./execution-policy.js";
import type { AgentEvent, AgentStore, AttemptStatus, RunStatus } from "./types.js";
import type { RunMode } from "./types.js";
import {
  canonicalInputHash,
  completeToolInvocation,
  markToolInvocationDispatched,
  markToolInvocationOutcomeUnknown,
  prepareToolInvocation,
  readToolInvocation,
  terminalizeRevokedToolInvocation,
  type ToolInvocationEffectClass,
  type ToolInvocationIdentity,
  type ToolInvocationRetryPolicy,
} from "./tool-invocation-ledger.js";

const ACTIVE_RUN_STATUSES = new Set<RunStatus>([
  "queued",
  "starting",
  "running",
  "waiting_input",
  "waiting_approval",
]);
const ACTIVE_ATTEMPT_STATUSES = new Set<AttemptStatus>([
  "queued",
  "starting",
  "running",
  "waiting_input",
  "waiting_approval",
]);

const TERMINAL_RUN_EVENTS = new Set([
  "run.succeeded",
  "run.failed",
  "run.cancelled",
  "run.timed_out",
  "run.orphaned",
]);
const TERMINAL_ATTEMPT_EVENTS = new Set([
  "attempt.succeeded",
  "attempt.failed",
  "attempt.cancelled",
  "attempt.timed_out",
  "attempt.orphaned",
]);

export type RunToolCapabilityRevocationReason =
  | "attempt_superseded"
  | "attempt_terminal"
  | "run_terminal"
  | "owner_changed"
  | "runtime_stopped"
  | "explicit";

export interface RunToolCapability {
  capabilityRef: string;
  ownerId: string;
  sessionId: string;
  runId: string;
  attemptId: string;
  adapterId: string;
  executionRole: AgentExecutionRole;
  surfaceKind: string;
  externalRefKind: string | null;
  externalRefId: string | null;
  originatingUserText: string;
  precedingAssistantText: string | null;
  runMode: RunMode;
  chatMode: string | null;
  profileGeneration: number;
  manifestVersion: number;
  manifestDigest: string;
  allowedToolNames: readonly string[];
  chatFirstUi: boolean;
  chatFirstControlGeneration: number | null;
  daemonBootEpoch: string;
  executionGeneration: number;
  registeredAtMs: number;
}

export type RunToolCapabilityRejectCode =
  | "capability_missing"
  | "capability_revoked"
  | "owner_mismatch"
  | "run_mismatch"
  | "attempt_mismatch"
  | "run_terminal"
  | "attempt_terminal"
  | "attempt_superseded"
  | "profile_changed"
  | "tool_not_manifested"
  | "tool_not_allowed"
  | "invocation_replayed";

export class RunToolCapabilityRejectedError extends Error {
  constructor(readonly code: RunToolCapabilityRejectCode, message: string) {
    super(message);
    this.name = "RunToolCapabilityRejectedError";
  }
}

export interface AuthorizedRunToolInvocation {
  invocationId: string;
  capabilityRef: string;
  ownerId: string;
  sessionId: string;
  runId: string;
  attemptId: string;
  adapterId: string;
  executionRole: AgentExecutionRole;
  profileGeneration: number;
  manifestVersion: number;
  manifestDigest: string;
  daemonBootEpoch: string;
  executionGeneration: number;
  inputHash: string;
  effectClass: ToolInvocationEffectClass;
  retryPolicy: ToolInvocationRetryPolicy;
  surfaceKind: string;
  externalRefKind: string | null;
  externalRefId: string | null;
  originatingUserText: string;
  precedingAssistantText: string | null;
  runMode: RunMode;
  chatMode: string | null;
  chatFirstUi: boolean;
  chatFirstControlGeneration: number | null;
  canonicalToolName: string;
  tool: OmiToolManifestEntry;
}

export interface RunToolExecutionLease {
  readonly signal: AbortSignal;
  assertCurrentAuthority(): void;
  release(): void;
}

export interface RunToolCapabilityBrokerOptions {
  store: AgentStore;
  nowMs?: () => number;
  daemonBootEpoch?: string;
  onRejected?: (code: RunToolCapabilityRejectCode) => void;
  /**
   * Profiles are authoritative once the profile migration is installed. This
   * seam keeps the broker independently testable and makes legacy session
   * columns a write-only projection rather than a second reader.
   */
  profileForSession: (sessionId: string) => {
    generation: number;
    adapterId: string;
    executionRole: AgentExecutionRole;
  };
}

interface CapabilityState {
  capability: RunToolCapability;
  revoked: boolean;
  revocationReason: RunToolCapabilityRevocationReason | null;
  activeInvocationIds: Set<string>;
  completedInvocationIds: Set<string>;
  executionLeases: Map<string, AbortController>;
}

function rejectCodeForRevocation(reason: RunToolCapabilityRevocationReason): RunToolCapabilityRejectCode {
  switch (reason) {
    case "owner_changed": return "owner_mismatch";
    case "run_terminal": return "run_terminal";
    case "attempt_terminal": return "attempt_terminal";
    case "attempt_superseded": return "attempt_superseded";
    case "runtime_stopped":
    case "explicit":
      return "capability_revoked";
  }
}

function relayAdapterId(adapterId: string): OmiToolAdapterId {
  switch (adapterId) {
    case "pi-mono":
      return "pi-mono";
    case "acp":
    case "hermes":
    case "openclaw":
      return "omi-tools-stdio";
    default:
      throw new Error(`Unknown canonical session adapter ${adapterId}`);
  }
}

function text(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

function number(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/**
 * Ephemeral capability authority for Swift-backed/runtime-control tools.
 *
 * Capabilities deliberately are never restored from SQLite. Startup
 * reconciliation orphans active attempts, and a subsequent durable-session
 * follow-up receives a newly minted capability. Every invocation re-reads the
 * persisted run/attempt/session/profile state; possession of the opaque ref is
 * not authorization by itself.
 */
export class RunToolCapabilityBroker {
  private readonly store: AgentStore;
  private readonly nowMs: () => number;
  readonly daemonBootEpoch: string;
  private readonly onRejected: (code: RunToolCapabilityRejectCode) => void;
  private readonly profileForSession: RunToolCapabilityBrokerOptions["profileForSession"];
  private readonly states = new Map<string, CapabilityState>();
  private readonly activeByAttempt = new Map<string, string>();
  private readonly activeByRun = new Map<string, Set<string>>();
  private executionGeneration = 0;

  constructor(options: RunToolCapabilityBrokerOptions) {
    this.store = options.store;
    this.nowMs = options.nowMs ?? Date.now;
    this.daemonBootEpoch = options.daemonBootEpoch ?? `boot_${randomUUID().replaceAll("-", "")}`;
    this.onRejected = options.onRejected ?? (() => undefined);
    if (typeof options.profileForSession !== "function") {
      throw new Error("Run tool capability broker requires a canonical session profile reader");
    }
    this.profileForSession = options.profileForSession;
  }

  activeCapabilityForProposal(capabilityRef: string, activeOwnerId: string): RunToolCapability {
    const state = this.states.get(capabilityRef);
    if (!state) this.reject("capability_missing", "Unknown run tool capability");
    if (state.revoked) this.reject("capability_revoked", "Run tool capability has been revoked");
    if (state.capability.ownerId !== activeOwnerId) {
      this.reject("owner_mismatch", "Run tool capability does not belong to the active owner");
    }
    return state.capability;
  }

  register(input: { ownerId: string; sessionId: string; runId: string; attemptId: string }): RunToolCapability {
    const persisted = this.persistedState(input.runId, input.attemptId);
    if (persisted.ownerId !== input.ownerId) {
      this.reject("owner_mismatch", "Capability owner does not own the persisted session");
    }
    if (persisted.sessionId !== input.sessionId) {
      this.reject("run_mismatch", "Capability session does not own the persisted run");
    }
    if (!ACTIVE_RUN_STATUSES.has(persisted.runStatus)) {
      this.reject("run_terminal", "Cannot register a capability for a terminal run");
    }
    if (!ACTIVE_ATTEMPT_STATUSES.has(persisted.attemptStatus)) {
      this.reject("attempt_terminal", "Cannot register a capability for a terminal attempt");
    }
    if (persisted.currentAttemptId !== input.attemptId) {
      this.reject("attempt_superseded", "Cannot register a capability for a superseded attempt");
    }

    const previousRef = this.activeByAttempt.get(input.attemptId);
    if (previousRef) {
      const previous = this.states.get(previousRef);
      if (previous && !previous.revoked) return previous.capability;
    }
    this.revokeRunCapabilities(input.runId, "attempt_superseded", input.attemptId);

    const adapterProjection = relayAdapterId(persisted.profile.adapterId);
    const projectionContext = {
      executionRole: persisted.profile.executionRole,
      screenContext: persisted.screenContext,
      surfaceKind: persisted.surfaceKind,
      chatFirstUi: persisted.chatFirstUi,
      controlGeneration: persisted.chatFirstControlGeneration,
    };
    const snapshot = buildToolAvailabilitySnapshot(adapterProjection, projectionContext);
    const allowedToolNames = toolsForAdapter(adapterProjection, projectionContext)
      .filter((tool) => executionRoleAllowsTool(persisted.profile.executionRole, tool.name))
      .map((tool) => tool.name)
      .sort();
    const capability: RunToolCapability = Object.freeze({
      capabilityRef: `cap_${randomUUID().replaceAll("-", "")}`,
      ownerId: input.ownerId,
      sessionId: input.sessionId,
      runId: input.runId,
      attemptId: input.attemptId,
      adapterId: persisted.profile.adapterId,
      executionRole: persisted.profile.executionRole,
      surfaceKind: persisted.surfaceKind,
      externalRefKind: persisted.externalRefKind,
      externalRefId: persisted.externalRefId,
      originatingUserText: persisted.originatingUserText,
      precedingAssistantText: persisted.precedingAssistantText,
      runMode: persisted.runMode,
      chatMode: persisted.chatMode,
      profileGeneration: persisted.profile.generation,
      manifestVersion: snapshot.manifestVersion,
      manifestDigest: snapshot.manifestDigest,
      allowedToolNames: Object.freeze(allowedToolNames),
      chatFirstUi: persisted.chatFirstUi,
      chatFirstControlGeneration: persisted.chatFirstControlGeneration,
      daemonBootEpoch: this.daemonBootEpoch,
      executionGeneration: ++this.executionGeneration,
      registeredAtMs: this.nowMs(),
    });
    this.states.set(capability.capabilityRef, {
      capability,
      revoked: false,
      revocationReason: null,
      activeInvocationIds: new Set(),
      completedInvocationIds: new Set(),
      executionLeases: new Map(),
    });
    this.activeByAttempt.set(capability.attemptId, capability.capabilityRef);
    const runRefs = this.activeByRun.get(capability.runId) ?? new Set<string>();
    runRefs.add(capability.capabilityRef);
    this.activeByRun.set(capability.runId, runRefs);
    return capability;
  }

  authorize(input: {
    capabilityRef: string;
    invocationId: string;
    runId: string;
    attemptId: string;
    toolName: string;
    toolInput: Record<string, unknown>;
    activeOwnerId: string;
  }): AuthorizedRunToolInvocation {
    const state = this.states.get(input.capabilityRef);
    if (!state) this.reject("capability_missing", "Unknown run tool capability");
    if (state.revoked) this.reject("capability_revoked", "Run tool capability has been revoked");
    const capability = state.capability;
    if (capability.ownerId !== input.activeOwnerId) {
      this.reject("owner_mismatch", "Run tool capability does not belong to the active owner");
    }
    if (capability.runId !== input.runId) {
      this.reject("run_mismatch", "Run tool capability does not match the invocation run");
    }
    if (capability.attemptId !== input.attemptId) {
      this.reject("attempt_mismatch", "Run tool capability does not match the invocation attempt");
    }
    if (state.activeInvocationIds.has(input.invocationId) || state.completedInvocationIds.has(input.invocationId)) {
      this.reject("invocation_replayed", "Tool invocation id has already been used for this capability");
    }

    const persisted = this.persistedState(input.runId, input.attemptId);
    if (persisted.ownerId !== capability.ownerId) {
      this.reject("owner_mismatch", "Persisted run owner no longer matches the capability");
    }
    if (!ACTIVE_RUN_STATUSES.has(persisted.runStatus)) {
      this.revoke(capability.capabilityRef, "run_terminal");
      this.reject("run_terminal", "Tool invocation rejected because the run is terminal");
    }
    if (!ACTIVE_ATTEMPT_STATUSES.has(persisted.attemptStatus)) {
      this.revoke(capability.capabilityRef, "attempt_terminal");
      this.reject("attempt_terminal", "Tool invocation rejected because the attempt is terminal");
    }
    if (persisted.currentAttemptId !== capability.attemptId) {
      this.revoke(capability.capabilityRef, "attempt_superseded");
      this.reject("attempt_superseded", "Tool invocation rejected because the attempt was superseded");
    }
    if (
      persisted.profile.generation !== capability.profileGeneration
      || persisted.profile.adapterId !== capability.adapterId
      || persisted.profile.executionRole !== capability.executionRole
    ) {
      this.revoke(capability.capabilityRef, "explicit");
      this.reject("profile_changed", "Session execution profile changed after capability registration");
    }

    const projection = relayAdapterId(capability.adapterId);
    const normalized = normalizeOmiToolName(projection, input.toolName).canonicalName;
    const tool = toolManifestEntry(normalized);
    if (!tool) this.reject("tool_not_manifested", "Tool is absent from the canonical Omi manifest");
    if (!capability.allowedToolNames.includes(tool.name)) {
      this.reject("tool_not_allowed", "Tool is unavailable for this run execution profile");
    }
    if (!executionRoleAllowsTool(capability.executionRole, tool.name)) {
      this.reject("tool_not_allowed", "Execution role cannot invoke this tool");
    }

    const inputHash = canonicalInputHash(input.toolInput);
    const effectClass: ToolInvocationEffectClass = tool.annotations.readOnlyHint === true
      ? "read_only"
      : tool.annotations.idempotentHint === true
        ? "idempotent_write"
        : "non_idempotent_write";
    const retryPolicy: ToolInvocationRetryPolicy = effectClass === "non_idempotent_write"
      ? "never_auto_retry"
      : "safe_retry";
    try {
      prepareToolInvocation(this.store, {
        invocationId: input.invocationId,
        ownerId: capability.ownerId,
        sessionId: capability.sessionId,
        runId: capability.runId,
        attemptId: capability.attemptId,
        profileGeneration: capability.profileGeneration,
        manifestVersion: capability.manifestVersion,
        manifestDigest: capability.manifestDigest,
        daemonBootEpoch: capability.daemonBootEpoch,
        executionGeneration: capability.executionGeneration,
        toolName: tool.name,
        inputHash,
        effectClass,
        retryPolicy,
        nowMs: this.nowMs(),
      });
    } catch (error) {
      this.reject("invocation_replayed", error instanceof Error ? error.message : "Tool invocation was already used");
    }
    state.activeInvocationIds.add(input.invocationId);
    return {
      invocationId: input.invocationId,
      capabilityRef: capability.capabilityRef,
      ownerId: capability.ownerId,
      sessionId: capability.sessionId,
      runId: capability.runId,
      attemptId: capability.attemptId,
      adapterId: capability.adapterId,
      executionRole: capability.executionRole,
      profileGeneration: capability.profileGeneration,
      manifestVersion: capability.manifestVersion,
      manifestDigest: capability.manifestDigest,
      daemonBootEpoch: capability.daemonBootEpoch,
      executionGeneration: capability.executionGeneration,
      inputHash,
      effectClass,
      retryPolicy,
      surfaceKind: capability.surfaceKind,
      externalRefKind: capability.externalRefKind,
      externalRefId: capability.externalRefId,
      originatingUserText: capability.originatingUserText,
      precedingAssistantText: capability.precedingAssistantText,
      runMode: capability.runMode,
      chatMode: capability.chatMode,
      chatFirstUi: capability.chatFirstUi,
      chatFirstControlGeneration: capability.chatFirstControlGeneration,
      canonicalToolName: tool.name,
      tool,
    };
  }

  authorizeRelayInvocation(input: {
    capabilityRef: string;
    invocationId: string;
    toolName: string;
    toolInput: Record<string, unknown>;
    activeOwnerId: string;
  }): AuthorizedRunToolInvocation {
    const state = this.states.get(input.capabilityRef);
    if (!state) this.reject("capability_missing", "Unknown run tool capability");
    return this.authorize({
      ...input,
      runId: state.capability.runId,
      attemptId: state.capability.attemptId,
    });
  }

  markInvocationDispatched(invocation: AuthorizedRunToolInvocation): void {
    markToolInvocationDispatched(this.store, this.ledgerIdentity(invocation), this.nowMs());
  }

  acquireExecutionLease(
    invocation: AuthorizedRunToolInvocation,
    activeOwnerId: () => string,
  ): RunToolExecutionLease {
    this.assertCurrentExecutionAuthority(invocation, activeOwnerId());
    const state = this.states.get(invocation.capabilityRef)!;
    const existing = state.executionLeases.get(invocation.invocationId);
    if (existing) this.reject("invocation_replayed", "Tool invocation already has an execution lease");
    const controller = new AbortController();
    state.executionLeases.set(invocation.invocationId, controller);
    let released = false;
    return {
      signal: controller.signal,
      assertCurrentAuthority: () => {
        if (released) this.reject("capability_revoked", "Tool execution lease has been released");
        this.assertCurrentExecutionAuthority(invocation, activeOwnerId());
      },
      release: () => {
        if (released) return;
        released = true;
        const active = this.states.get(invocation.capabilityRef);
        if (active?.executionLeases.get(invocation.invocationId) === controller) {
          active.executionLeases.delete(invocation.invocationId);
        }
      },
    };
  }

  completeInvocation(input: ToolInvocationIdentity & {
    capabilityRef: string;
    activeOwnerId: string;
    outcome: "succeeded" | "failed";
    result: string;
  }): void {
    const state = this.states.get(input.capabilityRef);
    if (!state) this.reject("capability_missing", "Unknown run tool capability at completion");
    if (state.revoked) {
      const code = rejectCodeForRevocation(state.revocationReason ?? "explicit");
      this.reject(code, `Run tool completion authority was revoked: ${state.revocationReason ?? "explicit"}`);
    }
    if (!state.activeInvocationIds.has(input.invocationId)) {
      this.reject("invocation_replayed", "Run tool invocation is no longer active at completion");
    }
    this.assertLiveCapabilityAuthority(state, input.activeOwnerId);
    completeToolInvocation(this.store, { ...input, nowMs: this.nowMs() });
    state.activeInvocationIds.delete(input.invocationId);
    state.completedInvocationIds.add(input.invocationId);
    state.executionLeases.delete(input.invocationId);
  }

  markInvocationOutcomeUnknown(
    invocation: AuthorizedRunToolInvocation,
    errorCode: string,
  ): void {
    markToolInvocationOutcomeUnknown(this.store, this.ledgerIdentity(invocation), errorCode, this.nowMs());
    const state = this.states.get(invocation.capabilityRef);
    state?.activeInvocationIds.delete(invocation.invocationId);
    state?.completedInvocationIds.add(invocation.invocationId);
    state?.executionLeases.delete(invocation.invocationId);
  }

  revoke(capabilityRef: string, reason: RunToolCapabilityRevocationReason = "explicit"): boolean {
    const state = this.states.get(capabilityRef);
    if (!state || state.revoked) return false;
    state.revoked = true;
    state.revocationReason = reason;
    for (const controller of state.executionLeases.values()) {
      controller.abort(new RunToolCapabilityRejectedError(
        rejectCodeForRevocation(reason),
        `Run tool execution authority was revoked: ${reason}`,
      ));
    }
    state.executionLeases.clear();
    for (const invocationId of state.activeInvocationIds) {
      const invocation = readToolInvocation(this.store, invocationId);
      if (invocation.status === "prepared" || invocation.status === "dispatched") {
        terminalizeRevokedToolInvocation(
          this.store,
          invocation,
          `run_tool_${reason}`,
          this.nowMs(),
        );
      }
      state.completedInvocationIds.add(invocationId);
    }
    state.activeInvocationIds.clear();
    if (this.activeByAttempt.get(state.capability.attemptId) === capabilityRef) {
      this.activeByAttempt.delete(state.capability.attemptId);
    }
    const runRefs = this.activeByRun.get(state.capability.runId);
    runRefs?.delete(capabilityRef);
    if (runRefs?.size === 0) this.activeByRun.delete(state.capability.runId);
    return true;
  }

  revokeForOwner(ownerId: string, reason: RunToolCapabilityRevocationReason = "owner_changed"): number {
    return this.revokeMatching((capability) => capability.ownerId === ownerId, reason);
  }

  revokeAll(reason: RunToolCapabilityRevocationReason = "runtime_stopped"): number {
    return this.revokeMatching(() => true, reason);
  }

  handleKernelEvent(event: AgentEvent): void {
    if (event.type === "attempt.created" && event.runId && event.attemptId) {
      this.revokeRunCapabilities(event.runId, "attempt_superseded", event.attemptId);
      return;
    }
    if (event.attemptId && TERMINAL_ATTEMPT_EVENTS.has(event.type)) {
      const ref = this.activeByAttempt.get(event.attemptId);
      if (ref) this.revoke(ref, "attempt_terminal");
      return;
    }
    if (event.runId && TERMINAL_RUN_EVENTS.has(event.type)) {
      this.revokeRunCapabilities(event.runId, "run_terminal");
    }
  }

  activeCapabilityForAttempt(attemptId: string): RunToolCapability | undefined {
    const ref = this.activeByAttempt.get(attemptId);
    const state = ref ? this.states.get(ref) : undefined;
    return state && !state.revoked ? state.capability : undefined;
  }

  /** Verify a live capability without consuming its one-use tool invocation. */
  assertLiveCapability(capabilityRef: string, activeOwnerId: string): RunToolCapability {
    const state = this.states.get(capabilityRef);
    if (!state) this.reject("capability_missing", "Unknown run tool capability");
    if (state.revoked) {
      const code = rejectCodeForRevocation(state.revocationReason ?? "explicit");
      this.reject(code, "Run tool capability has been revoked");
    }
    this.assertLiveCapabilityAuthority(state, activeOwnerId);
    return state.capability;
  }

  private revokeRunCapabilities(
    runId: string,
    reason: RunToolCapabilityRevocationReason,
    exceptAttemptId?: string,
  ): number {
    const refs = [...(this.activeByRun.get(runId) ?? [])];
    let count = 0;
    for (const ref of refs) {
      const state = this.states.get(ref);
      if (!state || state.revoked || state.capability.attemptId === exceptAttemptId) continue;
      if (this.revoke(ref, reason)) count += 1;
    }
    return count;
  }

  private revokeMatching(
    predicate: (capability: RunToolCapability) => boolean,
    reason: RunToolCapabilityRevocationReason,
  ): number {
    let count = 0;
    for (const [ref, state] of this.states) {
      if (!state.revoked && predicate(state.capability) && this.revoke(ref, reason)) count += 1;
    }
    return count;
  }

  private assertCurrentExecutionAuthority(
    invocation: AuthorizedRunToolInvocation,
    activeOwnerId: string,
  ): void {
    const state = this.states.get(invocation.capabilityRef);
    if (!state) this.reject("capability_missing", "Unknown run tool capability");
    if (state.revoked) {
      const code = rejectCodeForRevocation(state.revocationReason ?? "explicit");
      this.reject(code, `Run tool execution authority was revoked: ${state.revocationReason ?? "explicit"}`);
    }
    if (!state.activeInvocationIds.has(invocation.invocationId)) {
      this.reject("invocation_replayed", "Run tool invocation is no longer active");
    }
    this.assertLiveCapabilityAuthority(state, activeOwnerId);
  }

  private assertLiveCapabilityAuthority(
    state: CapabilityState,
    activeOwnerId: string,
  ): void {
    const capability = state.capability;
    if (capability.ownerId !== activeOwnerId) {
      this.revoke(capability.capabilityRef, "owner_changed");
      this.reject("owner_mismatch", "Run tool execution no longer belongs to the active owner");
    }
    const persisted = this.persistedState(capability.runId, capability.attemptId);
    if (persisted.ownerId !== capability.ownerId) {
      this.revoke(capability.capabilityRef, "owner_changed");
      this.reject("owner_mismatch", "Persisted run owner no longer matches the execution lease");
    }
    if (!ACTIVE_RUN_STATUSES.has(persisted.runStatus)) {
      this.revoke(capability.capabilityRef, "run_terminal");
      this.reject("run_terminal", "Run became terminal during tool execution");
    }
    if (!ACTIVE_ATTEMPT_STATUSES.has(persisted.attemptStatus)) {
      this.revoke(capability.capabilityRef, "attempt_terminal");
      this.reject("attempt_terminal", "Attempt became terminal during tool execution");
    }
    if (persisted.currentAttemptId !== capability.attemptId) {
      this.revoke(capability.capabilityRef, "attempt_superseded");
      this.reject("attempt_superseded", "Attempt was superseded during tool execution");
    }
    if (
      persisted.profile.generation !== capability.profileGeneration
      || persisted.profile.adapterId !== capability.adapterId
      || persisted.profile.executionRole !== capability.executionRole
    ) {
      this.revoke(capability.capabilityRef, "explicit");
      this.reject("profile_changed", "Execution profile changed during tool execution");
    }
  }

  private persistedState(runId: string, attemptId: string): {
    ownerId: string;
    sessionId: string;
    runStatus: RunStatus;
    attemptStatus: AttemptStatus;
    currentAttemptId: string;
    profile: { generation: number; adapterId: string; executionRole: AgentExecutionRole };
    surfaceKind: string;
    externalRefKind: string | null;
    externalRefId: string | null;
    originatingUserText: string;
    precedingAssistantText: string | null;
    runMode: RunMode;
    chatMode: string | null;
    screenContext: boolean;
    chatFirstUi: boolean;
    chatFirstControlGeneration: number | null;
  } {
    const row = this.store.getRow(
      `SELECT s.*, r.session_id AS authoritative_session_id, r.status AS authoritative_run_status,
              r.input_json, r.mode, a.status AS authoritative_attempt_status
       FROM run_attempts a
       JOIN runs r ON r.run_id = a.run_id
       JOIN sessions s ON s.session_id = r.session_id
       WHERE a.attempt_id = ? AND a.run_id = ?`,
      [attemptId, runId],
    );
    const latest = this.store.getRow(
      "SELECT attempt_id FROM run_attempts WHERE run_id = ? ORDER BY attempt_no DESC LIMIT 1",
      [runId],
    );
    const sessionId = text(row.authoritative_session_id);
    let runInput: Record<string, unknown> = {};
    try {
      const parsed = JSON.parse(text(row.input_json));
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        runInput = parsed as Record<string, unknown>;
      }
    } catch {
      runInput = {};
    }
    const metadata = runInput.metadata && typeof runInput.metadata === "object" && !Array.isArray(runInput.metadata)
      ? runInput.metadata as Record<string, unknown>
      : {};
    const externalSurface = metadata.externalSurface
      && typeof metadata.externalSurface === "object"
      && !Array.isArray(metadata.externalSurface)
      ? metadata.externalSurface as Record<string, unknown>
      : null;
    const admitted = runInput.admittedContextSnapshot
      && typeof runInput.admittedContextSnapshot === "object"
      && !Array.isArray(runInput.admittedContextSnapshot)
      ? runInput.admittedContextSnapshot as Record<string, unknown>
      : {};
    const admittedCapabilities = admitted.capabilities
      && typeof admitted.capabilities === "object"
      && !Array.isArray(admitted.capabilities)
      ? admitted.capabilities as Record<string, unknown>
      : {};
    const chatFirstUi = admittedCapabilities.chatFirstUi === true && text(row.surface_kind) === "main_chat";
    const controlGeneration = Number(admittedCapabilities.chatFirstControlGeneration);
    return {
      ownerId: text(row.owner_id),
      sessionId,
      runStatus: text(row.authoritative_run_status) as RunStatus,
      attemptStatus: text(row.authoritative_attempt_status) as AttemptStatus,
      currentAttemptId: text(latest.attempt_id),
      profile: this.profileForSession(sessionId),
      surfaceKind: externalSurface?.authority === "swift_realtime" ? "realtime_voice" : text(row.surface_kind),
      externalRefKind: row.external_ref_kind === null ? null : text(row.external_ref_kind),
      externalRefId: row.external_ref_id === null ? null : text(row.external_ref_id),
      originatingUserText: typeof runInput.prompt === "string" ? runInput.prompt : "",
      precedingAssistantText: admittedPrecedingAssistantText(runInput),
      runMode: text(row.mode) === "act" ? "act" : "ask",
      chatMode: typeof metadata.chatMode === "string" ? metadata.chatMode : null,
      screenContext: admittedScreenContext(runInput),
      chatFirstUi,
      chatFirstControlGeneration: chatFirstUi && Number.isSafeInteger(controlGeneration) && controlGeneration >= 0
        ? controlGeneration
        : null,
    };
  }

  private reject(code: RunToolCapabilityRejectCode, message: string): never {
    this.onRejected(code);
    throw new RunToolCapabilityRejectedError(code, message);
  }

  private ledgerIdentity(invocation: AuthorizedRunToolInvocation): ToolInvocationIdentity {
    return {
      invocationId: invocation.invocationId,
      ownerId: invocation.ownerId,
      sessionId: invocation.sessionId,
      runId: invocation.runId,
      attemptId: invocation.attemptId,
      profileGeneration: invocation.profileGeneration,
      manifestVersion: invocation.manifestVersion,
      manifestDigest: invocation.manifestDigest,
      daemonBootEpoch: invocation.daemonBootEpoch,
      executionGeneration: invocation.executionGeneration,
      inputHash: invocation.inputHash,
    };
  }
}

function admittedScreenContext(runInput: Record<string, unknown>): boolean {
  const admitted = runInput.admittedContextSnapshot;
  if (!admitted || typeof admitted !== "object" || Array.isArray(admitted)) return false;
  const sourceOutcomes = (admitted as Record<string, unknown>).sourceOutcomes;
  if (!Array.isArray(sourceOutcomes)) return false;
  return sourceOutcomes.some((source) =>
    source !== null
    && typeof source === "object"
    && !Array.isArray(source)
    && (source as Record<string, unknown>).source === "screen"
    && (source as Record<string, unknown>).outcome === "available",
  );
}

function admittedPrecedingAssistantText(runInput: Record<string, unknown>): string | null {
  const admitted = runInput.admittedContextSnapshot;
  if (!admitted || typeof admitted !== "object" || Array.isArray(admitted)) return null;
  const recentTurns = (admitted as Record<string, unknown>).recentTurns;
  if (!Array.isArray(recentTurns)) return null;
  for (let index = recentTurns.length - 1; index >= 0; index -= 1) {
    const turn = recentTurns[index];
    if (!turn || typeof turn !== "object" || Array.isArray(turn)) continue;
    const record = turn as Record<string, unknown>;
    if (record.role === "assistant" && typeof record.content === "string") {
      return record.content;
    }
  }
  return null;
}
