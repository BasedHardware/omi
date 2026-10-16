import { randomUUID } from "node:crypto";

import type { OmiToolAdapterId, OmiToolManifestEntry } from "./omi-tool-manifest.js";
import {
  buildToolAvailabilitySnapshot,
  normalizeOmiToolName,
  toolManifestEntry,
  toolsForAdapter,
  toolsForSurface,
} from "./omi-tool-manifest.js";
import { executionRoleAllowsTool, type AgentExecutionRole } from "./execution-policy.js";
import { validateRuntimeContractSchema, type RuntimeContractSchema } from "./contract-schema.js";
import { normalizedUIAutomationBundleId } from "./ui-automation-safety-floor.js";
import {
  buildDesktopToolApprovalRequest,
  desktopToolPolicyInternals,
  evaluateDesktopToolPolicy,
  type DesktopCoordinatorBundle,
  type DesktopToolApprovalRequest,
  type DesktopToolGrant,
  type DesktopToolPolicyResult,
} from "./desktop-tool-policy.js";
import type { AgentEvent, AgentStore, AttemptStatus, DesktopCoordinatorDispatch, RunStatus } from "./types.js";
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
  type ToolInvocationLedgerRecord,
  type ToolInvocationRetryPolicy,
} from "./tool-invocation-ledger.js";

const REALTIME_VOICE_SURFACE_KINDS = new Set(["realtime", "realtime_voice"]);

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
  /** Kernel-derived adapter built-in policy; request metadata cannot widen it. */
  builtInToolPolicy: "default" | "read_only";
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
  | "approval_required"
  | "invalid_tool_input"
  | "input_too_large_to_approve"
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

/**
 * Relay authorization either admits the invocation or parks it behind one
 * durable approval dispatch. A parked invocation already holds its `prepared`
 * ledger row, so a restart fails it exactly like any other undispatched claim;
 * the broker refuses to dispatch it until the user resolves the dispatch.
 */
export type RunToolAuthorizationOutcome =
  | { kind: "authorized"; invocation: AuthorizedRunToolInvocation }
  | {
      kind: "approval_required";
      invocation: AuthorizedRunToolInvocation;
      dispatch: DesktopCoordinatorDispatch;
      request: DesktopToolApprovalRequest;
    };

/** Durable binding stored in the approval dispatch payload under `invocation`. */
export interface ToolApprovalInvocationBinding {
  invocationId: string;
  toolName: string;
  inputHash: string;
  daemonBootEpoch: string;
  executionGeneration: number;
  adapterId: string;
  surfaceKind: string;
}

export interface CancelledToolApproval {
  dispatchId: string;
  invocationId: string;
  sessionId: string;
  runId: string;
  attemptId: string;
  reason: RunToolCapabilityRevocationReason;
}

export type ToolApprovalDenialCode = "approval_denied" | "approval_expired" | "approval_cancelled";

/**
 * What `approveInvocation` / `denyInvocation` took out of the broker's memory.
 * The kernel hands it back through `restorePendingApproval` when the SQLite
 * transaction around the decision rolls back, so memory never says "decided"
 * while the dispatch row still says "pending".
 */
export interface ReleasedToolApproval {
  capabilityRef: string;
  invocationId: string;
  dispatchId: string;
  ledgerWasActive: boolean;
}

export interface RunToolCapabilityBrokerOptions {
  store: AgentStore;
  nowMs?: () => number;
  daemonBootEpoch?: string;
  onRejected?: (code: RunToolCapabilityRejectCode) => void;
  /**
   * Parked approvals the broker closed because their authority ended
   * (terminal run, owner change, runtime stop). The dispatch rows are already
   * cancelled when this fires; the kernel records the matching
   * `approval.resolved` so every card ends with exactly one resolution.
   */
  onApprovalsCancelled?: (cancelled: CancelledToolApproval[]) => void;
  /** Policy seam for tests; production always uses `evaluateDesktopToolPolicy`. */
  desktopToolPolicy?: typeof evaluateDesktopToolPolicy;
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
  /** invocationId → approval dispatchId for prepared invocations the user has not resolved. */
  pendingApprovals: Map<string, string>;
}

interface PendingApproval {
  capabilityRef: string;
  invocationId: string;
  dispatchId: string;
}

interface EvaluatedInvocation {
  state: CapabilityState;
  tool: OmiToolManifestEntry;
  inputHash: string;
  effectClass: ToolInvocationEffectClass;
  retryPolicy: ToolInvocationRetryPolicy;
  approval: { policy: DesktopToolPolicyResult; resourceRef: string | undefined } | null;
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
 * Tools the broker parks behind a per-invocation approval card. A test holds
 * this set to every relay-callable tool the policy classifies into a sensitive
 * bundle, so a new sensitive tool cannot ship ungated by omission.
 */
export const DESKTOP_APPROVAL_TOOLS: ReadonlySet<string> = new Set([
  "list_message_chats",
  "read_message_history",
  "list_mail_messages",
  "send_message",
  "run_applescript",
  "capture_screen",
  "ui_snapshot",
]);

/** Bundles whose `grants` rows the broker reads; any other capability is ignored. */
const DESKTOP_GRANT_BUNDLES: readonly DesktopCoordinatorBundle[] = [
  "desktop.messaging.read",
  "desktop.mail.read",
  "desktop.messaging.send",
  "desktop.automation.act",
  "desktop.automation.observe",
];

/**
 * The resource a scoped grant is matched against, derived only from the
 * fields the tool actually acts on. The model never names the resource
 * itself: a caller-supplied ref would let one approval cover a different
 * recipient or script. Tools without a natural target get a stable ref so an
 * `allow_session` grant can name exactly that surface; the legacy `*` pattern
 * keeps matching them too.
 */
function toolResourceRef(toolName: string, input: Record<string, unknown>): string | undefined {
  if (toolName === "send_message") {
    const recipient = typeof input.to === "string" ? input.to.trim() : "";
    return recipient || undefined;
  }
  if (toolName === "run_applescript") {
    const script = typeof input.script === "string" ? input.script : "";
    return script || undefined;
  }
  if (toolName === "read_message_history") {
    const chatId = typeof input.chat_id === "string" || typeof input.chat_id === "number"
      ? String(input.chat_id)
      : "";
    const handle = typeof input.handle === "string" ? input.handle.trim() : "";
    return chatId || handle || undefined;
  }
  if (toolName === "list_message_chats") return "messages:chats";
  if (toolName === "list_mail_messages") return "mail:inbox";
  if (toolName === "capture_screen") return "screen";
  // One grant per app, whatever case the model spelled the bundle id in.
  if (toolName === "ui_snapshot") return normalizedUIAutomationBundleId(input.bundle_id);
  return undefined;
}

/**
 * Approval-gated tools are held to their manifest schema at the kernel
 * boundary. Neither relay validates inputs, so without this an unknown key
 * would ride into the ledger hash and the approval preview unexamined.
 */
function gatedToolInputErrors(tool: OmiToolManifestEntry, toolInput: Record<string, unknown>): string[] {
  return validateRuntimeContractSchema(toolInput, tool.inputSchema as RuntimeContractSchema);
}

export function toolApprovalInvocationBinding(dispatch: Pick<DesktopCoordinatorDispatch, "kind" | "payloadJson">): ToolApprovalInvocationBinding | null {
  if (dispatch.kind !== "approval") return null;
  let payload: unknown;
  try {
    payload = JSON.parse(dispatch.payloadJson);
  } catch {
    return null;
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  const binding = (payload as Record<string, unknown>).invocation;
  if (!binding || typeof binding !== "object" || Array.isArray(binding)) return null;
  const record = binding as Record<string, unknown>;
  if (
    typeof record.invocationId !== "string" || !record.invocationId
    || typeof record.toolName !== "string" || !record.toolName
    || typeof record.inputHash !== "string" || !record.inputHash
    || typeof record.daemonBootEpoch !== "string" || !record.daemonBootEpoch
    || !Number.isSafeInteger(record.executionGeneration)
    || typeof record.adapterId !== "string"
    || typeof record.surfaceKind !== "string"
  ) {
    return null;
  }
  return {
    invocationId: record.invocationId,
    toolName: record.toolName,
    inputHash: record.inputHash,
    daemonBootEpoch: record.daemonBootEpoch,
    executionGeneration: record.executionGeneration as number,
    adapterId: record.adapterId,
    surfaceKind: record.surfaceKind,
  };
}

/**
 * Whether the card for a bound tool approval offered "Allow for This Chat".
 * The broker writes the offered options into the dispatch payload when it
 * parks the call; a grant the card never offered (a live screenshot, a thread
 * read with no exact resource) is refused rather than minted.
 */
export function toolApprovalOffersSessionGrant(dispatch: Pick<DesktopCoordinatorDispatch, "payloadJson">): boolean {
  let payload: unknown;
  try {
    payload = JSON.parse(dispatch.payloadJson);
  } catch {
    return false;
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return false;
  const options = (payload as Record<string, unknown>).options;
  return Array.isArray(options) && options.some((option) =>
    !!option && typeof option === "object" && (option as Record<string, unknown>).id === "allow_session");
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
  private readonly onApprovalsCancelled: (cancelled: CancelledToolApproval[]) => void;
  private readonly desktopToolPolicy: typeof evaluateDesktopToolPolicy;
  private readonly profileForSession: RunToolCapabilityBrokerOptions["profileForSession"];
  private readonly states = new Map<string, CapabilityState>();
  private readonly activeByAttempt = new Map<string, string>();
  private readonly activeByRun = new Map<string, Set<string>>();
  /** dispatchId → parked invocation; process-local like the capabilities themselves. */
  private readonly pendingApprovalsByDispatch = new Map<string, PendingApproval>();
  private executionGeneration = 0;

  constructor(options: RunToolCapabilityBrokerOptions) {
    this.store = options.store;
    this.nowMs = options.nowMs ?? Date.now;
    this.daemonBootEpoch = options.daemonBootEpoch ?? `boot_${randomUUID().replaceAll("-", "")}`;
    this.onRejected = options.onRejected ?? (() => undefined);
    this.onApprovalsCancelled = options.onApprovalsCancelled ?? (() => undefined);
    this.desktopToolPolicy = options.desktopToolPolicy ?? evaluateDesktopToolPolicy;
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
      jitKnowledgeToolsEnabled: persisted.jitKnowledgeToolsEnabled,
      jitProactivity: persisted.jitProactivity,
      surfaceKind: persisted.surfaceKind,
      chatFirstUi: persisted.chatFirstUi,
      controlGeneration: persisted.chatFirstControlGeneration,
    };
    const snapshot = buildToolAvailabilitySnapshot(adapterProjection, projectionContext);
    // Realtime-voice runs invoke Swift-executed voice tools that no chat
    // adapter advertises (think_deeper, point_click, …). Authorize the
    // run's surface projection alongside the adapter projection so the
    // allowlist matches the tools the surface actually offers the provider.
    const surfaceTools = REALTIME_VOICE_SURFACE_KINDS.has(persisted.surfaceKind)
      ? toolsForSurface("realtime_voice")
      : [];
    const allowedToolNames = [
      ...new Set(
        [...toolsForAdapter(adapterProjection, projectionContext), ...surfaceTools]
          .filter((tool) => executionRoleAllowsTool(persisted.profile.executionRole, tool.name))
          .map((tool) => tool.name)
          .filter(
            (name) =>
              persisted.toolPolicyAllowedToolNames === null || persisted.toolPolicyAllowedToolNames.includes(name),
          ),
      ),
    ].sort();
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
      // Ask-mode service turns are non-interactive system work. Derive this
      // from persisted run/surface authority, never an external-ref prefix or
      // caller metadata, so choosing a label cannot grant mutation tools.
      builtInToolPolicy:
        persisted.runMode === "ask" && persisted.surfaceKind === "service"
          ? "read_only"
          : "default",
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
      pendingApprovals: new Map(),
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
    const evaluated = this.evaluate(input);
    if (evaluated.approval) {
      this.reject("approval_required", `Desktop tool approval was not granted: ${evaluated.approval.policy.reason}`);
    }
    return this.prepare(evaluated, input);
  }

  /**
   * Relay authorization that parks a sensitive invocation instead of rejecting
   * it. The ledger row and the approval dispatch are written together so a
   * restart cannot observe one without the other; the caller commits the
   * run/attempt transition and the lifecycle events in the same transaction.
   */
  authorizeRelayInvocationOrRequestApproval(input: {
    capabilityRef: string;
    invocationId: string;
    toolName: string;
    toolInput: Record<string, unknown>;
    activeOwnerId: string;
  }): RunToolAuthorizationOutcome {
    const state = this.states.get(input.capabilityRef);
    if (!state) this.reject("capability_missing", "Unknown run tool capability");
    const scoped = { ...input, runId: state.capability.runId, attemptId: state.capability.attemptId };
    const evaluated = this.evaluate(scoped);
    if (!evaluated.approval) return { kind: "authorized", invocation: this.prepare(evaluated, scoped) };

    const nowMs = this.nowMs();
    const request = buildDesktopToolApprovalRequest({
      toolName: evaluated.tool.name,
      toolInput: input.toolInput,
      policy: evaluated.approval.policy,
      resourceRef: evaluated.approval.resourceRef,
      nowMs,
    });
    // The user approves what the card shows. If the card cannot show all of
    // it, nothing is prepared: the model is told to shorten the input.
    if (request.previewTruncated) {
      this.reject(
        "input_too_large_to_approve",
        "The tool input is too large to show in an approval card; shorten it and call again",
      );
    }
    const invocation = this.prepare(evaluated, scoped);
    const binding: ToolApprovalInvocationBinding = {
      invocationId: invocation.invocationId,
      toolName: invocation.canonicalToolName,
      inputHash: invocation.inputHash,
      daemonBootEpoch: invocation.daemonBootEpoch,
      executionGeneration: invocation.executionGeneration,
      adapterId: invocation.adapterId,
      surfaceKind: invocation.surfaceKind,
    };
    const dispatch = this.store.insertDesktopDispatch({
      ownerId: invocation.ownerId,
      kind: "approval",
      priority: 100,
      title: request.title,
      decisionPrompt: request.decisionPrompt,
      recommendedDefault: request.defaultOptionId,
      sourceSessionId: invocation.sessionId,
      sourceRunId: invocation.runId,
      sourceAttemptId: invocation.attemptId,
      capability: request.capability,
      operation: request.operation,
      resourceRef: request.resourceRef,
      payloadJson: JSON.stringify({
        policy: request.policy,
        invocation: binding,
        preview: request.preview,
        previewTruncated: request.previewTruncated,
        options: request.options,
        defaultOptionId: request.defaultOptionId,
        reason: request.reason,
        requestedAtMs: request.requestedAtMs,
      }),
      createdAtMs: nowMs,
      expiresAtMs: request.expiresAtMs,
    });
    state.pendingApprovals.set(invocation.invocationId, dispatch.dispatchId);
    this.pendingApprovalsByDispatch.set(dispatch.dispatchId, {
      capabilityRef: state.capability.capabilityRef,
      invocationId: invocation.invocationId,
      dispatchId: dispatch.dispatchId,
    });
    return { kind: "approval_required", invocation, dispatch, request };
  }

  private evaluate(input: {
    capabilityRef: string;
    invocationId: string;
    runId: string;
    attemptId: string;
    toolName: string;
    toolInput: Record<string, unknown>;
    activeOwnerId: string;
  }): EvaluatedInvocation {
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
    if (capability.builtInToolPolicy === "read_only" && tool.annotations.readOnlyHint !== true) {
      this.reject("tool_not_allowed", "Ask-mode service runs have hard read-only tool authority");
    }
    if (!capability.allowedToolNames.includes(tool.name)) {
      this.reject("tool_not_allowed", "Tool is unavailable for this run execution profile");
    }
    if (!executionRoleAllowsTool(capability.executionRole, tool.name)) {
      this.reject("tool_not_allowed", "Execution role cannot invoke this tool");
    }

    let approval: EvaluatedInvocation["approval"] = null;
    if (DESKTOP_APPROVAL_TOOLS.has(tool.name)) {
      const inputErrors = gatedToolInputErrors(tool, input.toolInput);
      if (inputErrors.length > 0) {
        this.reject("invalid_tool_input", `Tool input does not match the ${tool.name} schema: ${inputErrors[0]!.slice(0, 200)}`);
      }
      const descriptor = desktopToolPolicyInternals.descriptorFromToolName(tool.name);
      if (!descriptor) this.reject("tool_not_manifested", "Desktop approval metadata is missing");
      const grants = this.desktopToolGrants(capability.sessionId, capability.runId);
      const resourceRef = toolResourceRef(tool.name, input.toolInput);
      const policy = this.desktopToolPolicy({
        toolName: tool.name,
        selectedBundles: descriptor.bundles,
        operation: tool.name,
        resourceRef,
        grants,
        nowMs: this.nowMs(),
      });
      // A hard policy deny is not something the user can approve away, so it
      // keeps the pre-existing rejection instead of parking the invocation.
      if (policy.decision === "deny") {
        this.reject("approval_required", `Desktop tool approval was not granted: ${policy.reason}`);
      }
      if (policy.decision === "dispatch_required") approval = { policy, resourceRef };
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
    return { state, tool, inputHash, effectClass, retryPolicy, approval };
  }

  private prepare(
    evaluated: EvaluatedInvocation,
    input: { invocationId: string },
  ): AuthorizedRunToolInvocation {
    const { state, tool, inputHash, effectClass, retryPolicy } = evaluated;
    const capability = state.capability;
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

  private desktopToolGrants(sessionId: string, runId: string): DesktopToolGrant[] {
    return this.store.allRows(
      `SELECT capability, operation, resource_pattern, effect, expires_at_ms
         FROM grants
        WHERE session_id = ?
          AND (run_id IS NULL OR run_id = ?)
          AND revoked_at_ms IS NULL`,
      [sessionId, runId],
    ).flatMap((row) => {
      const capability = typeof row.capability === "string" ? row.capability : "";
      const bundle = capability as DesktopCoordinatorBundle;
      if (!DESKTOP_GRANT_BUNDLES.includes(bundle)) return [];
      return [{
        bundle,
        operation: typeof row.operation === "string" ? row.operation : undefined,
        resourceRef: typeof row.resource_pattern === "string" && row.resource_pattern !== "*"
          ? row.resource_pattern
          : undefined,
        expiresAtMs: typeof row.expires_at_ms === "number" ? row.expires_at_ms : Number.POSITIVE_INFINITY,
        effect: row.effect === "allow" ? "allow" : "deny",
      }];
    });
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
    this.assertNotAwaitingApproval(invocation);
    markToolInvocationDispatched(this.store, this.ledgerIdentity(invocation), this.nowMs());
  }

  /**
   * Admit a parked invocation after the user allowed its dispatch. The caller
   * has already moved the dispatch row out of `pending`; this re-reads the
   * ledger and live run authority so a stale or tampered dispatch cannot admit
   * a different invocation, and the invocation stays single use.
   */
  approveInvocation(input: {
    dispatchId: string;
    binding: ToolApprovalInvocationBinding;
    activeOwnerId: string;
  }): { record: ToolInvocationLedgerRecord; released: ReleasedToolApproval } {
    const { state, record, pending } = this.readPendingApproval(input.dispatchId, input.binding);
    // Revalidate before forgetting the parking: a failure here may revoke the
    // capability, and revocation must still find and close the dispatch row.
    this.assertLiveCapabilityAuthority(state, input.activeOwnerId);
    return { record, released: this.releasePendingApproval(state, pending, false) };
  }

  /**
   * Everything `approveInvocation` checks, without taking anything. The kernel
   * runs this before it opens the transaction that resolves the dispatch, so a
   * revocation triggered by a stale owner, run, or attempt commits on its own
   * instead of being rolled back together with the failed resolution.
   */
  assertApprovalAuthority(input: {
    dispatchId: string;
    binding: ToolApprovalInvocationBinding;
    activeOwnerId: string;
  }): void {
    const { state } = this.readPendingApproval(input.dispatchId, input.binding);
    this.assertLiveCapabilityAuthority(state, input.activeOwnerId);
  }

  /** Fail a parked invocation closed; it never crossed the dispatch boundary, so it is `failed`, never `outcome_unknown`. */
  denyInvocation(input: {
    dispatchId: string;
    binding: ToolApprovalInvocationBinding;
    code: ToolApprovalDenialCode;
  }): { record: ToolInvocationLedgerRecord; released: ReleasedToolApproval } {
    const { state, record, pending } = this.readPendingApproval(input.dispatchId, input.binding);
    const terminal = terminalizeRevokedToolInvocation(this.store, record, input.code, this.nowMs());
    const released = this.releasePendingApproval(state, pending, state.activeInvocationIds.has(record.invocationId));
    state.activeInvocationIds.delete(record.invocationId);
    state.completedInvocationIds.add(record.invocationId);
    return { record: terminal, released };
  }

  /** Undo a release whose surrounding transaction rolled back; a revoked capability already closed its dispatch durably. */
  restorePendingApproval(released: ReleasedToolApproval): void {
    const state = this.states.get(released.capabilityRef);
    if (!state || state.revoked) return;
    state.pendingApprovals.set(released.invocationId, released.dispatchId);
    this.pendingApprovalsByDispatch.set(released.dispatchId, {
      capabilityRef: released.capabilityRef,
      invocationId: released.invocationId,
      dispatchId: released.dispatchId,
    });
    if (released.ledgerWasActive) {
      state.completedInvocationIds.delete(released.invocationId);
      state.activeInvocationIds.add(released.invocationId);
    }
  }

  hasPendingApprovals(runId: string): boolean {
    for (const ref of this.activeByRun.get(runId) ?? []) {
      const state = this.states.get(ref);
      if (state && !state.revoked && state.pendingApprovals.size > 0) return true;
    }
    return false;
  }

  private readPendingApproval(
    dispatchId: string,
    binding: ToolApprovalInvocationBinding,
  ): { state: CapabilityState; record: ToolInvocationLedgerRecord; pending: PendingApproval } {
    const pending = this.pendingApprovalsByDispatch.get(dispatchId);
    const state = pending ? this.states.get(pending.capabilityRef) : undefined;
    if (!pending || !state || state.pendingApprovals.get(pending.invocationId) !== dispatchId) {
      this.reject("capability_revoked", "Approval dispatch is not bound to a live pending invocation");
    }
    if (pending.invocationId !== binding.invocationId) {
      this.reject("invocation_replayed", "Approval dispatch binding names a different invocation");
    }
    const record = readToolInvocation(this.store, pending.invocationId);
    if (
      record.status !== "prepared"
      || record.inputHash !== binding.inputHash
      || record.toolName !== binding.toolName
      || record.daemonBootEpoch !== binding.daemonBootEpoch
      || record.daemonBootEpoch !== this.daemonBootEpoch
      || record.executionGeneration !== binding.executionGeneration
      || record.runId !== state.capability.runId
      || record.attemptId !== state.capability.attemptId
    ) {
      this.reject("invocation_replayed", "Approval dispatch binding does not match the prepared invocation");
    }
    return { state, record, pending };
  }

  private releasePendingApproval(
    state: CapabilityState,
    pending: PendingApproval,
    ledgerWasActive: boolean,
  ): ReleasedToolApproval {
    state.pendingApprovals.delete(pending.invocationId);
    this.pendingApprovalsByDispatch.delete(pending.dispatchId);
    return {
      capabilityRef: state.capability.capabilityRef,
      invocationId: pending.invocationId,
      dispatchId: pending.dispatchId,
      ledgerWasActive,
    };
  }

  private assertNotAwaitingApproval(invocation: AuthorizedRunToolInvocation): void {
    const state = this.states.get(invocation.capabilityRef);
    if (state?.pendingApprovals.has(invocation.invocationId)) {
      this.reject("approval_required", "Tool invocation is waiting for user approval");
    }
  }

  acquireExecutionLease(
    invocation: AuthorizedRunToolInvocation,
    activeOwnerId: () => string,
  ): RunToolExecutionLease {
    this.assertNotAwaitingApproval(invocation);
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
    const cancelledApprovals: CancelledToolApproval[] = [];
    state.revoked = true;
    state.revocationReason = reason;
    for (const controller of state.executionLeases.values()) {
      controller.abort(new RunToolCapabilityRejectedError(
        rejectCodeForRevocation(reason),
        `Run tool execution authority was revoked: ${reason}`,
      ));
    }
    state.executionLeases.clear();
    // A parked approval cannot outlive the authority it would admit. Close the
    // dispatch row here, before the ledger row below becomes `failed`, so no
    // later resolution can find a pending card for a dead invocation.
    const nowMs = this.nowMs();
    for (const [invocationId, dispatchId] of state.pendingApprovals) {
      this.store.execute(
        `UPDATE desktop_dispatches
         SET status = 'cancelled', resolved_at_ms = ?, resolved_by = 'system', resolution_json = ?
         WHERE dispatch_id = ? AND status = 'pending'`,
        [nowMs, JSON.stringify({ decision: "cancelled", reason: `run_tool_${reason}` }), dispatchId],
      );
      this.pendingApprovalsByDispatch.delete(dispatchId);
      cancelledApprovals.push({
        dispatchId,
        invocationId,
        sessionId: state.capability.sessionId,
        runId: state.capability.runId,
        attemptId: state.capability.attemptId,
        reason,
      });
    }
    state.pendingApprovals.clear();
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
    if (cancelledApprovals.length > 0) this.onApprovalsCancelled(cancelledApprovals);
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
    jitKnowledgeToolsEnabled: boolean;
    jitProactivity: boolean;
    chatFirstUi: boolean;
    chatFirstControlGeneration: number | null;
    /** Spawn-time child tool restriction; null = no policy, [] = no tools (fail closed). */
    toolPolicyAllowedToolNames: string[] | null;
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
    // The run's surface, falling back to the session's for runs admitted before
    // it was recorded. `s.surface_kind` is where the session was first
    // registered — for a shared shell that can be `floating_chat` while main
    // Chat runs on it, and gating chat-first on that rejected the tool the
    // model had just been offered.
    const runSurfaceKind = typeof runInput.surfaceKind === "string" && runInput.surfaceKind.trim()
      ? runInput.surfaceKind.trim()
      : text(row.surface_kind);
    const chatFirstUi = admittedCapabilities.chatFirstUi === true && runSurfaceKind === "main_chat";
    const controlGeneration = Number(admittedCapabilities.chatFirstControlGeneration);
    return {
      ownerId: text(row.owner_id),
      sessionId,
      runStatus: text(row.authoritative_run_status) as RunStatus,
      attemptStatus: text(row.authoritative_attempt_status) as AttemptStatus,
      currentAttemptId: text(latest.attempt_id),
      profile: this.profileForSession(sessionId),
      // Also the run's surface: Swift re-validates an authorized invocation with
      // `surfaceKind == "main_chat"` before it will execute a chat-first tool,
      // and selects the manifest digest from the same field.
      surfaceKind: externalSurface?.authority === "swift_realtime" ? "realtime_voice" : runSurfaceKind,
      externalRefKind: row.external_ref_kind === null ? null : text(row.external_ref_kind),
      externalRefId: row.external_ref_id === null ? null : text(row.external_ref_id),
      originatingUserText: typeof runInput.prompt === "string" ? runInput.prompt : "",
      precedingAssistantText: admittedPrecedingAssistantText(runInput),
      runMode: text(row.mode) === "act" ? "act" : "ask",
      chatMode: typeof metadata.chatMode === "string" ? metadata.chatMode : null,
      screenContext: admittedScreenContext(runInput),
      jitKnowledgeToolsEnabled: metadata.jitKnowledgeToolsEnabled === true,
      jitProactivity: metadata.jitBudget !== undefined,
      chatFirstUi,
      chatFirstControlGeneration: chatFirstUi && Number.isSafeInteger(controlGeneration) && controlGeneration >= 0
        ? controlGeneration
        : null,
      toolPolicyAllowedToolNames: admittedToolPolicyAllowedToolNames(metadata),
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

function admittedToolPolicyAllowedToolNames(metadata: Record<string, unknown>): string[] | null {
  const rawToolPolicy = metadata.toolPolicy;
  if (rawToolPolicy === undefined) return null;
  // Present-but-malformed policy fails closed to an empty allowlist.
  if (
    rawToolPolicy === null
    || typeof rawToolPolicy !== "object"
    || Array.isArray(rawToolPolicy)
    || !Array.isArray((rawToolPolicy as Record<string, unknown>).allowedToolNames)
  ) {
    return [];
  }
  return ((rawToolPolicy as Record<string, unknown>).allowedToolNames as unknown[]).filter(
    (name): name is string => typeof name === "string",
  );
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
