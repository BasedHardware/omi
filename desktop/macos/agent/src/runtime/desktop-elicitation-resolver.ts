/**
 * The kernel-backed side of elicitation: turn an adapter's blocked request into
 * a pending `desktop_dispatches` row, then wait for a person to resolve it.
 *
 * The dispatch primitive already models this — kind, decision prompt, pending
 * status, `resolvedBy: "user"`, and a grant minted on approval. What it has
 * never had is a producer that a human answers. This is that producer.
 */

import {
  failClosedOutcome,
  type ElicitationOutcome,
  type ElicitationRequest,
  type ElicitationResolver,
} from "./desktop-elicitation.js";
import { dispatchKindFor } from "./desktop-elicitation.js";
import type { AgentEvent, DesktopCoordinatorDispatch, NewDesktopCoordinatorDispatch } from "./types.js";

/**
 * The resolution an answering surface writes back through
 * `resolve_desktop_dispatch`. `optionId` names one of the offered options;
 * `text` carries a typed answer, which only a question may accept.
 */
export interface ElicitationResolutionPayload {
  optionId?: unknown;
  optionIds?: unknown;
  text?: unknown;
}

/** Notifies the desktop surface that a question is waiting, or no longer is. */
export interface ElicitationNotifier {
  pending(input: {
    dispatchId: string;
    ownerId: string;
    sessionId: string;
    runId: string | null;
    request: ElicitationRequest;
    createdAtMs: number;
  }): void;
  resolved(input: {
    dispatchId: string;
    ownerId: string;
    outcome: "answered" | "cancelled";
  }): void;
}

export interface KernelElicitationDeps {
  kernel: {
    createDesktopDispatch(input: NewDesktopCoordinatorDispatch): DesktopCoordinatorDispatch;
    sessionForAdapterNativeSession(
      adapterId: string,
      adapterNativeSessionId: string,
    ): { sessionId: string; ownerId: string; runId: string | null } | null;
    subscribe(subscriber: (event: AgentEvent) => void): () => void;
  };
  notifier?: ElicitationNotifier;
  log: (message: string) => void;
}

/**
 * Dispatch priority. Elicitations block a live run, so they outrank the
 * review-style dispatches that can wait for the user to come back.
 */
const BLOCKING_DISPATCH_PRIORITY = 100;

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/**
 * Build the stored resolution for an answer arriving from the desktop surface.
 *
 * The surface and this module have to agree on key names, and nothing used to
 * hold them together: the surface began sending `optionIds` while the runtime
 * still read `optionId`, so every answer was recorded empty and came back to
 * the model as "no valid answer was registered". Both sides go through here now.
 */
export function elicitationResolution(
  input: { optionIds?: readonly string[]; text?: string | null },
): ElicitationResolutionPayload {
  return {
    optionIds: [...(input.optionIds ?? [])],
    text: input.text ?? null,
  };
}

/**
 * Map a resolution payload onto an outcome.
 *
 * A permission request may only be answered with an option the agent offered,
 * so typed text is rejected here rather than at the wire, keeping the
 * protocol's constraint enforced on every path into it.
 */
export function outcomeFromResolution(
  request: ElicitationRequest,
  status: unknown,
  resolution: ElicitationResolutionPayload | null,
): ElicitationOutcome {
  if (status !== "resolved") {
    return { kind: "cancelled", reason: typeof status === "string" ? status : "cancelled" };
  }
  // Only ids the request actually offered are accepted, so a stale or malformed
  // resolution can never manufacture an answer the user was not shown.
  const offered = new Set(request.options.map((option) => option.optionId));
  const claimed = Array.isArray(resolution?.optionIds)
    ? resolution.optionIds
    : typeof resolution?.optionId === "string"
      ? [resolution.optionId]
      : [];
  const selected = claimed.filter(
    (id): id is string => typeof id === "string" && offered.has(id),
  );
  const typed = typeof resolution?.text === "string" ? resolution.text.trim() : "";
  if (selected.length > 0) {
    // A permission answers with exactly one option whatever the surface sent;
    // the protocol has no way to carry a second.
    const optionIds = request.allowsMultiple ? selected : [selected[0]!];
    // A pick-many question can be answered with options *and* the user's own
    // words -- "these three, plus this" -- so both are carried rather than one
    // silently discarding the other.
    return request.allowsFreeText && typed.length > 0
      ? { kind: "selected", optionIds, text: typed }
      : { kind: "selected", optionIds };
  }
  if (request.allowsFreeText && typed.length > 0) {
    return { kind: "answered", text: typed };
  }
  return { kind: "cancelled", reason: "resolution_carried_no_valid_answer" };
}

/**
 * Build the resolver an adapter calls when policy will not auto-resolve.
 *
 * Fails closed on every path that cannot reach a person: an adapter session
 * with no kernel binding, or a dispatch that cannot be recorded. Approving
 * because bookkeeping failed would be the exact behaviour this replaces.
 */
export function createKernelElicitationResolver(deps: KernelElicitationDeps): ElicitationResolver {
  return async (request: ElicitationRequest): Promise<ElicitationOutcome> => {
    if (!request.externalSessionId) {
      deps.log("Elicitation has no adapter session to bind to; failing closed");
      return failClosedOutcome(request, "no_adapter_session");
    }

    const binding = deps.kernel.sessionForAdapterNativeSession(
      request.adapterId,
      request.externalSessionId,
    );
    if (!binding) {
      deps.log(
        `Elicitation has no kernel binding for ${request.adapterId}/${request.externalSessionId}; failing closed`,
      );
      return failClosedOutcome(request, "no_kernel_binding");
    }

    return await askUser(deps, request, binding);
  };
}

/** The kernel identity an elicitation is recorded against. */
export interface ElicitationOwnerBinding {
  sessionId: string;
  ownerId: string;
  runId: string | null;
}

/**
 * How many questions are on screen waiting for an answer, process-wide.
 *
 * Idle watchdogs elsewhere measure "has this turn produced progress lately" and
 * cannot otherwise tell a stalled agent from one correctly blocked on a person.
 * A user reading a question is progress; cancelling the turn under them throws
 * away the answer they are in the middle of giving.
 *
 * Deliberately a process-wide count rather than per-session: an elicitation is
 * bound to a kernel session, while the watchdogs that need this run against
 * adapter-native sessions, and the two do not share an id. The cost of the
 * coarser signal is that one session's open question briefly protects another
 * session's genuinely stalled turn; the next tick after the answer catches it.
 */
let inFlightElicitations = 0;

export function humanIsBeingAsked(): boolean {
  return inFlightElicitations > 0;
}

/**
 * Record the question, tell the surface, and wait for the user.
 *
 * Shared by the ACP path, which has to discover its binding from an
 * adapter-native session, and by `ask_user`, which already knows the session it
 * was called from.
 */
export async function askUser(
  deps: KernelElicitationDeps,
  request: ElicitationRequest,
  binding: ElicitationOwnerBinding,
): Promise<ElicitationOutcome> {
  let dispatch: DesktopCoordinatorDispatch;
  try {
    dispatch = deps.kernel.createDesktopDispatch({
      ownerId: binding.ownerId,
      kind: dispatchKindFor(request),
      priority: BLOCKING_DISPATCH_PRIORITY,
      title: request.title,
      decisionPrompt: request.prompt,
      recommendedDefault: request.recommendedDefault,
      sourceSessionId: binding.sessionId,
      sourceRunId: binding.runId,
      payloadJson: JSON.stringify({
        channel: request.channel,
        mode: request.mode,
        adapterId: request.adapterId,
        subject: request.subject,
        context: request.context,
        options: request.options,
        allowsFreeText: request.allowsFreeText,
      }),
      // No expiry: the run waits in `waiting_approval` until the user acts or
      // the turn is cancelled. Startup reconciliation, not a clock, is what
      // clears a dispatch whose blocked request died with its process.
      expiresAtMs: null,
    });
  } catch (error) {
    deps.log(`Elicitation dispatch could not be recorded: ${String(error)}; failing closed`);
    return failClosedOutcome(request, "dispatch_not_recorded");
  }

  deps.log(`Elicitation dispatch ${dispatch.dispatchId} pending for ${request.adapterId}`);
  deps.notifier?.pending({
    dispatchId: dispatch.dispatchId,
    ownerId: binding.ownerId,
    sessionId: binding.sessionId,
    runId: binding.runId,
    request,
    createdAtMs: dispatch.createdAtMs,
  });

  inFlightElicitations += 1;
  let outcome: ElicitationOutcome;
  try {
    outcome = await waitForDispatchResolution(deps, request, dispatch.dispatchId, binding.runId);
  } finally {
    // Decremented on every exit, so a throw cannot leave a watchdog permanently
    // believing someone is still being asked.
    inFlightElicitations -= 1;
  }
  // Announced for every terminal transition, not only a user answer, so a card
  // cannot outlive the question it belongs to.
  deps.notifier?.resolved({
    dispatchId: dispatch.dispatchId,
    ownerId: binding.ownerId,
    outcome: outcome.kind === "cancelled" ? "cancelled" : "answered",
  });
  return outcome;
}

/**
 * Resolve when the dispatch does. Subscribes before returning so a resolution
 * arriving immediately after creation is still observed.
 */
/**
 * Run states after which nothing can consume an answer.
 *
 * A question outlives its run when the turn is cancelled, fails, or is
 * superseded. The card used to stay on screen regardless, so the user could
 * answer a run whose authority was already revoked and watch nothing happen.
 */
const TERMINAL_RUN_EVENTS: ReadonlySet<string> = new Set([
  "run.succeeded",
  "run.failed",
  "run.cancelled",
  "run.timed_out",
  "run.orphaned",
]);

function waitForDispatchResolution(
  deps: KernelElicitationDeps,
  request: ElicitationRequest,
  dispatchId: string,
  runId: string | null,
): Promise<ElicitationOutcome> {
  return new Promise<ElicitationOutcome>((resolve) => {
    const unsubscribe = deps.kernel.subscribe((event) => {
      // The run this question belongs to has ended. Release the waiter so the
      // surface retires the card instead of collecting an answer for nobody.
      if (runId && event.runId === runId && TERMINAL_RUN_EVENTS.has(event.type)) {
        unsubscribe();
        resolve({ kind: "cancelled", reason: `run_${event.type.replace("run.", "")}` });
        return;
      }
      if (event.type !== "approval.resolved") return;
      let payload: Record<string, unknown> | null;
      try {
        payload = asRecord(JSON.parse(event.payloadJson));
      } catch {
        return;
      }
      if (payload?.dispatchId !== dispatchId) return;
      unsubscribe();
      resolve(outcomeFromResolution(request, payload.status, asRecord(payload.resolution)));
    });
  });
}
