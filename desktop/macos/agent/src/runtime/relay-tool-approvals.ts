import type { OutboundMessageDraft } from "../protocol.js";
import type { DesktopToolApprovalRequest } from "./desktop-tool-policy.js";
import type { AuthorizedRunToolInvocation } from "./run-tool-capability.js";
import type { AgentEvent, DesktopCoordinatorDispatch } from "./types.js";

/**
 * The relay side of a parked device tool call.
 *
 * The kernel owns every decision: dispatch row, ledger row, run status, and
 * the `approval.resolved` event that ends a card. This module only remembers
 * which relay client is waiting for which invocation and turns the kernel's
 * resolution into exactly one of two things: the ordinary Swift dispatch
 * (`authorized_tool_execution`, once) or a failed `tool_result` for the model.
 * It also mirrors every request and resolution to Swift as a frame.
 *
 * Nothing here survives a daemon restart on purpose: startup reconciliation
 * fails the prepared ledger row and expires the dispatch, so a parked call is
 * never replayed.
 */

export type RelayToolOutcome = "succeeded" | "failed";

export interface PendingSwiftToolCall<TClient> {
  client: TClient;
  callId: string;
  invocation: AuthorizedRunToolInvocation;
  timeout: unknown;
}

export interface RelayToolApprovalKernel {
  markRunToolInvocationDispatched(invocation: AuthorizedRunToolInvocation): void;
  markRunToolInvocationOutcomeUnknown(invocation: AuthorizedRunToolInvocation, errorCode: string): void;
  terminateDesktopToolApproval(input: { dispatchId: string; status: "expired" | "cancelled"; reason: string }): unknown;
}

export interface RelayToolApprovalsOptions<TClient extends object> {
  kernel: RelayToolApprovalKernel;
  /** Writes an outbound frame to Swift. */
  send(message: OutboundMessageDraft): void;
  /** Writes a finalized `tool_result` back to the relay client that asked. */
  writeRelayToolResult(
    client: TClient,
    callId: string,
    result: string,
    invocation?: AuthorizedRunToolInvocation,
    outcome?: RelayToolOutcome,
  ): void;
  /** Swift executions in flight, shared with the daemon's result handler. */
  pendingSwiftCalls: Map<string, PendingSwiftToolCall<TClient>>;
  activeOwnerId(): string;
  log(message: string): void;
  nowMs?(): number;
  setTimer?(callback: () => void, delayMs: number): unknown;
  clearTimer?(handle: unknown): void;
  /** How long Swift may take to return one authorized execution. */
  swiftTimeoutMs?: number;
}

interface ParkedRelayCall<TClient> {
  approvalId: string;
  client: TClient;
  callId: string;
  invocation: AuthorizedRunToolInvocation;
  toolInput: Record<string, unknown>;
  expiry: unknown;
}

const TERMINAL_RUN_TOOL_EVENTS = new Set([
  "run.succeeded",
  "run.failed",
  "run.cancelled",
  "run.timed_out",
  "run.orphaned",
  "attempt.succeeded",
  "attempt.failed",
  "attempt.cancelled",
  "attempt.timed_out",
  "attempt.orphaned",
]);

const APPROVAL_DECISIONS = new Set(["allow", "deny", "expired", "cancelled"]);

export function relayToolError(code: string, message: string, extra: Record<string, unknown> = {}): string {
  return JSON.stringify({ ok: false, error: { code, message, ...extra } });
}

export class RelayToolApprovals<TClient extends object> {
  private readonly kernel: RelayToolApprovalKernel;
  private readonly send: RelayToolApprovalsOptions<TClient>["send"];
  private readonly writeRelayToolResult: RelayToolApprovalsOptions<TClient>["writeRelayToolResult"];
  private readonly pendingSwiftCalls: Map<string, PendingSwiftToolCall<TClient>>;
  private readonly activeOwnerId: () => string;
  private readonly log: (message: string) => void;
  private readonly nowMs: () => number;
  private readonly setTimer: (callback: () => void, delayMs: number) => unknown;
  private readonly clearTimer: (handle: unknown) => void;
  private readonly swiftTimeoutMs: number;
  private readonly parked = new Map<string, ParkedRelayCall<TClient>>();

  constructor(options: RelayToolApprovalsOptions<TClient>) {
    this.kernel = options.kernel;
    this.send = options.send;
    this.writeRelayToolResult = options.writeRelayToolResult;
    this.pendingSwiftCalls = options.pendingSwiftCalls;
    this.activeOwnerId = options.activeOwnerId;
    this.log = options.log;
    this.nowMs = options.nowMs ?? Date.now;
    this.setTimer = options.setTimer ?? ((callback, delayMs) => setTimeout(callback, delayMs));
    this.clearTimer = options.clearTimer ?? ((handle) => clearTimeout(handle as ReturnType<typeof setTimeout>));
    this.swiftTimeoutMs = options.swiftTimeoutMs ?? 120_000;
  }

  isPending(invocationId: string): boolean {
    return this.parked.has(invocationId) || this.pendingSwiftCalls.has(invocationId);
  }

  /**
   * Hold a relay call until the user answers its approval dispatch. The kernel
   * already committed the dispatch, the prepared ledger row and the
   * `waiting_approval` transition; this arms the expiry and shows the card.
   */
  park(input: {
    client: TClient;
    callId: string;
    invocation: AuthorizedRunToolInvocation;
    toolInput: Record<string, unknown>;
    dispatch: Pick<DesktopCoordinatorDispatch, "dispatchId" | "expiresAtMs">;
    request: DesktopToolApprovalRequest;
  }): void {
    const { invocation, dispatch, request } = input;
    const key = invocation.invocationId;
    if (this.isPending(key)) {
      this.writeRelayToolResult(
        input.client,
        input.callId,
        relayToolError("invocation_replayed", "Duplicate tool invocation"),
        invocation,
        "failed",
      );
      return;
    }
    const expiresAtMs = dispatch.expiresAtMs ?? request.expiresAtMs;
    const expiry = this.setTimer(() => this.expire(key, dispatch.dispatchId), Math.max(0, expiresAtMs - this.nowMs()));
    this.parked.set(key, {
      approvalId: dispatch.dispatchId,
      client: input.client,
      callId: input.callId,
      invocation,
      toolInput: input.toolInput,
      expiry,
    });
    this.send({
      type: "approval_requested",
      approvalId: dispatch.dispatchId,
      ownerId: invocation.ownerId,
      sessionId: invocation.sessionId,
      runId: invocation.runId,
      attemptId: invocation.attemptId,
      invocationId: invocation.invocationId,
      adapterId: invocation.adapterId,
      surfaceKind: invocation.surfaceKind,
      policy: request.policy,
      toolName: invocation.canonicalToolName,
      capability: request.capability,
      operation: request.operation,
      resourceRef: request.resourceRef,
      inputHash: invocation.inputHash,
      effectClass: invocation.effectClass,
      title: request.title,
      decisionPrompt: request.decisionPrompt,
      preview: request.preview,
      previewTruncated: request.previewTruncated,
      reason: request.reason,
      options: request.options.map((option) => ({ ...option })),
      defaultOptionId: request.defaultOptionId,
      requestedAtMs: request.requestedAtMs,
      expiresAtMs,
    });
  }

  /** Hand an authorized relay invocation to Swift and wait for its single result. */
  dispatchToSwift(
    client: TClient,
    callId: string,
    invocation: AuthorizedRunToolInvocation,
    toolInput: Record<string, unknown>,
  ): void {
    const key = invocation.invocationId;
    if (this.isPending(key)) {
      this.writeRelayToolResult(client, callId, relayToolError("invocation_replayed", "Duplicate tool invocation"), invocation, "failed");
      return;
    }
    try {
      // The broker refuses this while the invocation is still awaiting approval.
      this.kernel.markRunToolInvocationDispatched(invocation);
    } catch (error) {
      const code = error && typeof error === "object" && "code" in error
        ? String((error as { code: unknown }).code)
        : "capability_rejected";
      this.writeRelayToolResult(
        client,
        callId,
        relayToolError(code, error instanceof Error ? error.message : "Tool dispatch rejected"),
        invocation,
        "failed",
      );
      return;
    }
    const timeout = this.setTimer(() => {
      const pending = this.pendingSwiftCalls.get(key);
      if (!pending) return;
      this.pendingSwiftCalls.delete(key);
      try {
        this.kernel.markRunToolInvocationOutcomeUnknown(pending.invocation, "swift_tool_timeout");
      } catch (error) {
        this.log(`Failed to mark timed-out tool invocation outcome unknown: ${error}`);
      }
      this.writeRelayToolResult(
        pending.client,
        pending.callId,
        relayToolError("swift_tool_timeout", "Timed out waiting for the Swift tool executor"),
        pending.invocation,
        "failed",
      );
    }, this.swiftTimeoutMs);
    this.pendingSwiftCalls.set(key, { client, callId, invocation, timeout });
    this.send({
      type: "authorized_tool_execution",
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
      capabilityRef: invocation.capabilityRef,
      toolName: invocation.canonicalToolName,
      input: toolInput,
      inputHash: invocation.inputHash,
      effectClass: invocation.effectClass,
      retryPolicy: invocation.retryPolicy,
      surfaceKind: invocation.surfaceKind,
      externalRefKind: invocation.externalRefKind,
      externalRefId: invocation.externalRefId,
      originatingUserText: invocation.originatingUserText,
      precedingAssistantText: invocation.precedingAssistantText,
      runMode: invocation.runMode,
      chatMode: invocation.chatMode,
      ...(invocation.chatFirstControlGeneration !== null
        ? { chatFirstControlGeneration: invocation.chatFirstControlGeneration }
        : {}),
    });
  }

  /**
   * Every approval ends with exactly one `approval.resolved`, whoever ended it
   * (user, expiry, cancellation, run termination, owner change). Swift gets
   * the matching frame; a parked call dispatches once or fails closed.
   */
  handleKernelEvent(event: AgentEvent): void {
    if (TERMINAL_RUN_TOOL_EVENTS.has(event.type)) {
      this.rejectForTerminalEvent(event);
      return;
    }
    if (event.type !== "approval.resolved") return;
    const payload = parseObject(event.payloadJson);
    const invocationId = typeof payload?.invocationId === "string" ? payload.invocationId : "";
    const approvalId = typeof payload?.approvalId === "string" ? payload.approvalId : "";
    if (!payload || !invocationId || !approvalId || !event.runId || !event.attemptId) return;
    const decision = typeof payload.decision === "string" && APPROVAL_DECISIONS.has(payload.decision)
      ? (payload.decision as "allow" | "deny" | "expired" | "cancelled")
      : "deny";
    const pending = this.parked.get(invocationId);
    this.send({
      type: "approval_resolved",
      approvalId,
      ownerId: pending?.invocation.ownerId ?? this.activeOwnerId(),
      sessionId: event.sessionId,
      runId: event.runId,
      attemptId: event.attemptId,
      invocationId,
      toolName: typeof payload.toolName === "string" ? payload.toolName : pending?.invocation.canonicalToolName ?? "",
      decision,
      selectedOptionId: typeof payload.selectedOptionId === "string" ? payload.selectedOptionId : null,
      grantId: typeof payload.grantId === "string" ? payload.grantId : null,
      resolvedBy: typeof payload.resolvedBy === "string" ? payload.resolvedBy : "system",
      resolvedAtMs: typeof payload.resolvedAtMs === "number" ? payload.resolvedAtMs : event.createdAtMs,
      automatic: payload.automatic === true,
    });
    if (!pending || pending.approvalId !== approvalId) return;
    this.parked.delete(invocationId);
    this.clearTimer(pending.expiry);
    if (decision === "allow") {
      this.dispatchToSwift(pending.client, pending.callId, pending.invocation, pending.toolInput);
      return;
    }
    const message = decision === "deny"
      ? "The user declined this action."
      : decision === "expired"
        ? "The approval request expired before the user answered."
        : "The approval request was cancelled before the user answered.";
    this.writeRelayToolResult(
      pending.client,
      pending.callId,
      relayToolError("approval_denied", message, { reason: decision }),
      pending.invocation,
      "failed",
    );
  }

  /** The owner changed or the runtime is stopping: parked calls fail like any other pending call. */
  rejectForOwner(ownerId: string, code: string, message: string): void {
    for (const [key, pending] of this.parked) {
      if (pending.invocation.ownerId !== ownerId) continue;
      this.parked.delete(key);
      this.clearTimer(pending.expiry);
      this.writeRelayToolResult(pending.client, pending.callId, relayToolError(code, message), pending.invocation, "failed");
    }
  }

  /**
   * The relay client that was waiting went away. Nobody can receive the
   * answer, so the kernel closes the card and fails the invocation; there is
   * no client left to write a result to.
   */
  rejectForClient(client: TClient): void {
    for (const [key, pending] of this.parked) {
      if (pending.client !== client) continue;
      this.parked.delete(key);
      this.clearTimer(pending.expiry);
      try {
        this.kernel.terminateDesktopToolApproval({
          dispatchId: pending.approvalId,
          status: "cancelled",
          reason: "relay_client_disconnected",
        });
      } catch (error) {
        this.log(`Failed to cancel approval ${pending.approvalId} for disconnected relay client: ${error}`);
      }
    }
  }

  private rejectForTerminalEvent(event: AgentEvent): void {
    if (!event.runId) return;
    const code = event.type.startsWith("attempt.") ? "attempt_terminal" : "run_terminal";
    for (const [key, pending] of this.parked) {
      if (pending.invocation.runId !== event.runId) continue;
      if (event.attemptId && pending.invocation.attemptId !== event.attemptId) continue;
      // The broker already cancelled the dispatch row and failed the prepared
      // ledger row; the kernel's derived approval.resolved follows this event.
      this.parked.delete(key);
      this.clearTimer(pending.expiry);
      this.writeRelayToolResult(
        pending.client,
        pending.callId,
        relayToolError(code, "Run tool authority ended before the user answered the approval"),
        pending.invocation,
        "failed",
      );
    }
  }

  private expire(key: string, dispatchId: string): void {
    const pending = this.parked.get(key);
    if (!pending) return;
    try {
      // The kernel's approval.resolved event settles the relay call.
      this.kernel.terminateDesktopToolApproval({ dispatchId, status: "expired", reason: "approval_wait_expired" });
    } catch (error) {
      this.log(`Failed to expire approval ${dispatchId}: ${error}`);
      if (!this.parked.has(key)) return;
      this.parked.delete(key);
      this.writeRelayToolResult(
        pending.client,
        pending.callId,
        relayToolError("approval_denied", "The approval request expired before the user answered.", { reason: "expired" }),
        pending.invocation,
        "failed",
      );
    }
  }
}

function parseObject(json: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(json) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}
