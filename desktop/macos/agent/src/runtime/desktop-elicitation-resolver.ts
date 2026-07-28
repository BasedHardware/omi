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
  const optionId = resolution?.optionId;
  if (typeof optionId === "string" && request.options.some((option) => option.optionId === optionId)) {
    return { kind: "selected", optionId };
  }
  const text = resolution?.text;
  if (request.allowsFreeText && typeof text === "string" && text.trim().length > 0) {
    return { kind: "answered", text };
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

    const outcome = await waitForDispatchResolution(deps, request, dispatch.dispatchId);
    // Announced for every terminal transition, not only a user answer, so a
    // card cannot outlive the question it belongs to.
    deps.notifier?.resolved({
      dispatchId: dispatch.dispatchId,
      ownerId: binding.ownerId,
      outcome: outcome.kind === "cancelled" ? "cancelled" : "answered",
    });
    return outcome;
  };
}

/**
 * Resolve when the dispatch does. Subscribes before returning so a resolution
 * arriving immediately after creation is still observed.
 */
function waitForDispatchResolution(
  deps: KernelElicitationDeps,
  request: ElicitationRequest,
  dispatchId: string,
): Promise<ElicitationOutcome> {
  return new Promise<ElicitationOutcome>((resolve) => {
    const unsubscribe = deps.kernel.subscribe((event) => {
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
