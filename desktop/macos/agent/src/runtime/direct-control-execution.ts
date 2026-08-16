import {
  handleAgentControlToolCall,
  isAgentControlToolName,
  withMergedOwnerGuard,
  type AgentControlToolContext,
} from "./control-tools.js";

export type DirectControlAuthorityErrorCode =
  | "direct_control_owner_revoked"
  | "direct_control_request_replayed";

export class DirectControlAuthorityError extends Error {
  constructor(
    readonly code: DirectControlAuthorityErrorCode,
    message: string,
  ) {
    super(message);
    this.name = "DirectControlAuthorityError";
  }
}

export interface DirectControlExecutionRequest {
  ownerId: string;
  clientId: string;
  requestId: string;
  name: string;
  input: Record<string, unknown>;
}

export interface DirectControlExecutionResult {
  ownerId: string;
  name: string;
  result: string;
}

interface DirectControlLeaseState {
  key: string;
  ownerId: string;
  ownerEpoch: number;
  controller: AbortController;
}

interface DirectControlExecutionLease {
  readonly signal: AbortSignal;
  assertCurrentAuthority(): void;
  retainRun(runId: string): void;
  release(input: {
    retainedRunIds: readonly string[];
    kernel: AgentControlToolContext["kernel"];
  }): void;
}

const OWNER_RETAINED_SIGNAL_TOOLS = new Set(["spawn_agent", "spawn_background_agent"]);
const TRACE_PROPAGATED_TOOLS = new Set([
  "spawn_agent",
  "spawn_background_agent",
  "send_agent_message",
  "run_agent_and_wait",
]);
const DEFAULT_RECENT_REQUEST_LIMIT = 4_096;
const TERMINAL_RUN_EVENTS = new Set([
  "run.succeeded",
  "run.failed",
  "run.cancelled",
  "run.timed_out",
  "run.orphaned",
]);

interface RetainedOwnerSignal {
  controller: AbortController;
  pendingRunIds: Set<string>;
  unsubscribe: () => void;
}

/**
 * Owner-scoped authority for signed desktop control requests. Request identity
 * is single-use within a bounded replay window; durable kernel effect
 * idempotency still applies where supported. Owner epochs invalidate every
 * active request and every accepted background-spawn signal on account
 * transition.
 */
export class DirectControlExecutionBroker {
  private readonly activeOwnerId: () => string;
  private readonly recentRequestLimit: number;
  private readonly ownerEpochs = new Map<string, number>();
  private readonly activeLeases = new Map<string, DirectControlLeaseState>();
  /** Bounded FIFO replay window; active request identities live separately and are never evicted. */
  private readonly recentRequestKeys = new Set<string>();
  private readonly recentRequestOrder: string[] = [];
  /** One entry per nonterminal accepted direct spawn; kernel terminal events prune it. */
  private readonly retainedOwnerSignals = new Map<string, Set<RetainedOwnerSignal>>();

  constructor(input: { activeOwnerId: () => string; recentRequestLimit?: number }) {
    this.activeOwnerId = input.activeOwnerId;
    this.recentRequestLimit = input.recentRequestLimit ?? DEFAULT_RECENT_REQUEST_LIMIT;
    if (!Number.isSafeInteger(this.recentRequestLimit) || this.recentRequestLimit < 1) {
      throw new Error("Direct control recent request limit must be a positive integer");
    }
  }

  async execute(
    request: DirectControlExecutionRequest,
    context: AgentControlToolContext,
  ): Promise<DirectControlExecutionResult> {
    const ownerId = request.ownerId.trim();
    let lease: DirectControlExecutionLease | undefined;
    let retainedRunIds: string[] = [];
    try {
      if (!ownerId || ownerId !== this.activeOwnerId()) {
        throw ownerRevoked("Direct control owner does not match the active signed-in owner");
      }
      if (!isAgentControlToolName(request.name)) {
        return {
          ownerId,
          name: request.name,
          result: controlFailure(
            "unsupported_direct_control_tool",
            `Direct app control cannot execute ${request.name}`,
          ),
        };
      }
      lease = this.acquire({ ...request, ownerId });
      const controlInput = withMergedOwnerGuard(request.input, ownerId, ownerId);
      const tracedControlInput = TRACE_PROPAGATED_TOOLS.has(request.name)
        ? {
            ...controlInput,
            requestId:
              typeof controlInput.requestId === "string" && controlInput.requestId.trim()
                ? controlInput.requestId
                : request.requestId,
            clientId:
              typeof controlInput.clientId === "string" && controlInput.clientId.trim()
                ? controlInput.clientId
                : request.clientId,
          }
        : controlInput;
      const result = await handleAgentControlToolCall(
        {
          ...context,
          trustedUserControl: true,
          getOwnerId: this.activeOwnerId,
          executionLease: lease,
        },
        request.name,
        tracedControlInput,
      );
      lease.assertCurrentAuthority();
      retainedRunIds = OWNER_RETAINED_SIGNAL_TOOLS.has(request.name) && controlSucceeded(result)
        ? controlRunIds(result)
        : [];
      return { ownerId, name: request.name, result };
    } catch (error) {
      const authorityError = directControlAuthorityError(error);
      if (authorityError) {
        return {
          ownerId,
          name: request.name,
          result: controlFailure(authorityError.code, authorityError.message),
        };
      }
      return {
        ownerId,
        name: request.name,
        result: controlFailure(
          "direct_control_failed",
          error instanceof Error ? error.message : String(error),
        ),
      };
    } finally {
      lease?.release({ retainedRunIds, kernel: context.kernel });
    }
  }

  abortOwner(ownerId: string, reason: "owner_changed" | "owner_state_cleared"): number {
    const normalizedOwnerId = ownerId.trim();
    if (!normalizedOwnerId) return 0;
    this.ownerEpochs.set(normalizedOwnerId, this.ownerEpoch(normalizedOwnerId) + 1);
    const error = ownerRevoked(`Direct control authority was revoked: ${reason}`);
    let aborted = 0;
    for (const state of this.activeLeases.values()) {
      if (state.ownerId !== normalizedOwnerId || state.controller.signal.aborted) continue;
      state.controller.abort(error);
      aborted += 1;
    }
    const retained = this.retainedOwnerSignals.get(normalizedOwnerId);
    if (retained) {
      for (const retainedSignal of [...retained]) {
        if (!retainedSignal.controller.signal.aborted) {
          retainedSignal.controller.abort(error);
          aborted += 1;
        }
        retainedSignal.unsubscribe();
        retained.delete(retainedSignal);
      }
      this.retainedOwnerSignals.delete(normalizedOwnerId);
    }
    return aborted;
  }

  transitionOwner(previousOwnerId: string, nextOwnerId: string): number {
    return previousOwnerId === nextOwnerId
      ? 0
      : this.abortOwner(previousOwnerId, "owner_changed");
  }

  abortAll(): number {
    const owners = new Set<string>();
    for (const state of this.activeLeases.values()) owners.add(state.ownerId);
    for (const ownerId of this.retainedOwnerSignals.keys()) owners.add(ownerId);
    let aborted = 0;
    for (const ownerId of owners) aborted += this.abortOwner(ownerId, "owner_state_cleared");
    return aborted;
  }

  retainedSignalCount(ownerId?: string): number {
    if (ownerId !== undefined) return this.retainedOwnerSignals.get(ownerId)?.size ?? 0;
    let count = 0;
    for (const signals of this.retainedOwnerSignals.values()) count += signals.size;
    return count;
  }

  private acquire(request: DirectControlExecutionRequest): DirectControlExecutionLease {
    const key = requestKey(request.clientId, request.requestId);
    if (this.activeLeases.has(key) || this.recentRequestKeys.has(key)) {
      throw new DirectControlAuthorityError(
        "direct_control_request_replayed",
        "Direct control request identity has already been used",
      );
    }
    const state: DirectControlLeaseState = {
      key,
      ownerId: request.ownerId,
      ownerEpoch: this.ownerEpoch(request.ownerId),
      controller: new AbortController(),
    };
    this.activeLeases.set(key, state);
    const admittedRunIds = new Set<string>();
    let released = false;
    const assertCurrentAuthority = (): void => {
      if (
        released
        || this.activeLeases.get(key) !== state
        || state.controller.signal.aborted
        || this.ownerEpoch(state.ownerId) !== state.ownerEpoch
        || this.activeOwnerId() !== state.ownerId
      ) {
        throw signalAuthorityError(state.controller.signal)
          ?? ownerRevoked("Direct control owner changed during execution");
      }
    };
    return {
      signal: state.controller.signal,
      assertCurrentAuthority,
      retainRun: (runId) => {
        assertCurrentAuthority();
        const normalizedRunId = runId.trim();
        if (!normalizedRunId) throw new Error("Direct control cannot retain an empty run id");
        admittedRunIds.add(normalizedRunId);
      },
      release: ({ retainedRunIds, kernel }) => {
        if (released) return;
        released = true;
        if (this.activeLeases.get(key) === state) this.activeLeases.delete(key);
        this.rememberRequestKey(key);
        const allRetainedRunIds = new Set([...admittedRunIds, ...retainedRunIds]);
        if (allRetainedRunIds.size > 0 && !state.controller.signal.aborted) {
          this.retainOwnerSignal(state, kernel, [...allRetainedRunIds]);
        }
      },
    };
  }

  private ownerEpoch(ownerId: string): number {
    return this.ownerEpochs.get(ownerId) ?? 0;
  }

  private rememberRequestKey(key: string): void {
    if (this.recentRequestKeys.has(key)) return;
    this.recentRequestKeys.add(key);
    this.recentRequestOrder.push(key);
    while (this.recentRequestOrder.length > this.recentRequestLimit) {
      const expired = this.recentRequestOrder.shift();
      if (expired) this.recentRequestKeys.delete(expired);
    }
  }

  private retainOwnerSignal(
    state: DirectControlLeaseState,
    kernel: AgentControlToolContext["kernel"],
    runIds: readonly string[],
  ): void {
    const pendingRunIds = new Set(runIds);
    if (pendingRunIds.size === 0) return;
    const retainedSet = this.retainedOwnerSignals.get(state.ownerId) ?? new Set<RetainedOwnerSignal>();
    let retained!: RetainedOwnerSignal;
    const releaseRun = (runId: string): void => {
      retained.pendingRunIds.delete(runId);
      if (retained.pendingRunIds.size > 0) return;
      retained.unsubscribe();
      retainedSet.delete(retained);
      if (retainedSet.size === 0) this.retainedOwnerSignals.delete(state.ownerId);
    };
    const unsubscribe = kernel.subscribe((event) => {
      if (event.runId && TERMINAL_RUN_EVENTS.has(event.type)) releaseRun(event.runId);
    });
    retained = { controller: state.controller, pendingRunIds, unsubscribe };
    retainedSet.add(retained);
    this.retainedOwnerSignals.set(state.ownerId, retainedSet);
    for (const runId of [...pendingRunIds]) {
      try {
        const status = kernel.getRun({ runId, ownerId: state.ownerId, includeEvents: false }).run.status;
        if (["succeeded", "failed", "cancelled", "timed_out", "orphaned"].includes(status)) releaseRun(runId);
      } catch {
        // An absent run cannot retain executable owner authority.
        releaseRun(runId);
      }
    }
  }
}

function requestKey(clientId: string, requestId: string): string {
  const normalizedClientId = clientId.trim();
  const normalizedRequestId = requestId.trim();
  if (!normalizedClientId || !normalizedRequestId) {
    throw new Error("Direct control requires tracing requestId and clientId");
  }
  return `${normalizedClientId}\u0000${normalizedRequestId}`;
}

function ownerRevoked(message: string): DirectControlAuthorityError {
  return new DirectControlAuthorityError("direct_control_owner_revoked", message);
}

function signalAuthorityError(signal: AbortSignal): DirectControlAuthorityError | undefined {
  return signal.reason instanceof DirectControlAuthorityError ? signal.reason : undefined;
}

function directControlAuthorityError(error: unknown): DirectControlAuthorityError | undefined {
  if (error instanceof DirectControlAuthorityError) return error;
  if (
    error
    && typeof error === "object"
    && "code" in error
    && (error as { code?: unknown }).code === "direct_control_owner_revoked"
  ) {
    return ownerRevoked(error instanceof Error ? error.message : "Direct control owner changed during execution");
  }
  return undefined;
}

function controlSucceeded(result: string): boolean {
  try {
    const parsed = JSON.parse(result) as unknown;
    return !!parsed && typeof parsed === "object" && !Array.isArray(parsed)
      && (parsed as { ok?: unknown }).ok !== false;
  } catch {
    return false;
  }
}

function controlRunIds(result: string): string[] {
  try {
    const parsed = JSON.parse(result) as Record<string, unknown>;
    const ids = new Set<string>();
    const addRun = (value: unknown): void => {
      if (!value || typeof value !== "object" || Array.isArray(value)) return;
      const runId = (value as { runId?: unknown }).runId;
      if (typeof runId === "string" && runId.trim()) ids.add(runId);
    };
    addRun(parsed.run);
    if (Array.isArray(parsed.agents)) {
      for (const agent of parsed.agents) {
        if (!agent || typeof agent !== "object" || Array.isArray(agent)) continue;
        addRun((agent as { run?: unknown }).run);
      }
    }
    return [...ids];
  } catch {
    return [];
  }
}

function controlFailure(code: string, message: string): string {
  return JSON.stringify({ ok: false, error: { code, message } });
}
