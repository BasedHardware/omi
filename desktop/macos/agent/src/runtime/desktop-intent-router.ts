import { createHash, randomUUID } from "node:crypto";

import type { AgentExecutionRole } from "./execution-policy.js";

export type DesktopIntentRouteKind =
  | "answer_inline"
  | "spawn_agent"
  | "continue_run"
  | "clarify"
  | "reject";

export type DesktopIntentEffectKind = Extract<DesktopIntentRouteKind, "spawn_agent" | "continue_run">;

export type DesktopIntentReasonCode =
  | "explicit_delegation_negation"
  | "inline_proposal"
  | "spawn_proposal"
  | "continue_proposal"
  | "proposal_required"
  | "continuation_handle_required"
  | "continuation_target_unavailable"
  | "parent_run_unavailable"
  | "caller_role_forbidden"
  | "provider_unavailable"
  | "agent_count_unsupported"
  | "surface_requested_clarification";

/**
 * These are syntax facts, not authorization or semantic-routing outcomes.
 * Surfaces may extract them mechanically from structured UI state or explicit
 * user syntax. The kernel re-resolves every referenced identity and provider.
 */
export interface DesktopIntentSyntaxFacts {
  delegationNegated?: boolean;
  explicitSessionId?: string | null;
  explicitRunId?: string | null;
  parentRunId?: string | null;
  explicitProvider?: string | null;
  requestedAgentCount?: number | null;
}

/** An untrusted semantic proposal. Kernel-owned policy validates the effect. */
export type DesktopIntentProposal =
  | { intent: "answer_inline" }
  | { intent: "spawn_agent" }
  | { intent: "continue_run" }
  | { intent: "clarify"; missing?: readonly string[] };

export interface DesktopIntentRouteRequest {
  /**
   * Retained while surfaces migrate to structured proposals. Routing never
   * inspects this text; only a bounded hash is exposed for safe correlation.
   */
  utterance: string;
  surfaceKind: string;
  taskId?: string | null;
  snapshotVersion?: string;
  syntaxFacts?: DesktopIntentSyntaxFacts;
  proposal?: DesktopIntentProposal;
}

export interface DesktopIntentSessionCandidate {
  sessionId: string;
  runId?: string | null;
  surfaceKind: string;
  taskId?: string | null;
  title?: string | null;
  status: "healthy" | "stale" | "failed" | "orphaned" | "closed";
  relevance: number;
  lastActivityAtMs: number;
}

/** Kernel-resolved continuation target. Surface-provided handles never set it. */
export interface DesktopIntentTarget {
  sessionId: string;
  runId?: string | null;
  status: "open" | "closed";
}

export interface DesktopIntentRouteAuthority {
  ownerId: string;
  callerExecutionRole: AgentExecutionRole;
  availableAdapterIds: readonly string[];
  continuationTarget?: DesktopIntentTarget | null;
  parentRunAvailable?: boolean;
  nowMs: number;
}

interface DesktopIntentRouteBase {
  decisionId: string;
  intent: DesktopIntentRouteKind;
  surfaceKind: string;
  snapshotVersion: string;
  createdAtMs: number;
  reasonCode: DesktopIntentReasonCode;
  explanation: string;
  inputHash: string;
}

export interface DesktopIntentAnswerInlineRoute extends DesktopIntentRouteBase {
  intent: "answer_inline";
}

export interface DesktopIntentSpawnAgentRoute extends DesktopIntentRouteBase {
  intent: "spawn_agent";
  requestedProvider: string | null;
  requestedAgentCount: number;
  parentRunId: string | null;
}

export interface DesktopIntentContinueRunRoute extends DesktopIntentRouteBase {
  intent: "continue_run";
  sessionId: string;
  runId: string | null;
}

export interface DesktopIntentClarifyRoute extends DesktopIntentRouteBase {
  intent: "clarify";
  missing: readonly string[];
}

export interface DesktopIntentRejectRoute extends DesktopIntentRouteBase {
  intent: "reject";
  code:
    | "caller_role_forbidden"
    | "provider_unavailable"
    | "continuation_target_unavailable"
    | "parent_run_unavailable"
    | "agent_count_unsupported";
}

export type DesktopIntentRoute =
  | DesktopIntentAnswerInlineRoute
  | DesktopIntentSpawnAgentRoute
  | DesktopIntentContinueRunRoute
  | DesktopIntentClarifyRoute
  | DesktopIntentRejectRoute;

export interface DesktopIntentDecisionBinding {
  decisionId: string;
  ownerId: string;
  surfaceKind: string;
  snapshotVersion: string;
  expectedIntent: DesktopIntentEffectKind;
  nowMs: number;
}

export interface DesktopIntentRouterOptions {
  nextDecisionId?: () => string;
  decisionTtlMs?: number;
  maxTrackedDecisions?: number;
}

interface TrackedDecision {
  decision: DesktopIntentRoute;
  ownerId: string;
  consumedAtMs: number | null;
}

export class DesktopIntentRouteError extends Error {
  readonly reasonCode: DesktopIntentReasonCode | "decision_not_found" | "decision_expired" | "decision_replayed" | "decision_binding_mismatch";

  constructor(
    reasonCode: DesktopIntentRouteError["reasonCode"],
    message: string,
  ) {
    super(message);
    this.name = "DesktopIntentRouteError";
    this.reasonCode = reasonCode;
  }
}

/**
 * Single route-decision owner. It intentionally has no language heuristics:
 * semantic proposals remain untrusted until checked against kernel authority.
 */
export class DesktopIntentRouter {
  private readonly tracked = new Map<string, TrackedDecision>();
  private readonly nextDecisionId: () => string;
  private readonly decisionTtlMs: number;
  private readonly maxTrackedDecisions: number;

  constructor(options: DesktopIntentRouterOptions = {}) {
    this.nextDecisionId = options.nextDecisionId ?? randomUUID;
    this.decisionTtlMs = options.decisionTtlMs ?? 5 * 60 * 1_000;
    this.maxTrackedDecisions = options.maxTrackedDecisions ?? 512;
  }

  route(request: DesktopIntentRouteRequest, authority: DesktopIntentRouteAuthority): DesktopIntentRoute {
    this.prune(authority.nowMs);
    const decision = decideDesktopIntent(this.nextDecisionId(), request, authority);
    if (decision.intent === "spawn_agent" || decision.intent === "continue_run") {
      this.tracked.set(decision.decisionId, {
        decision,
        ownerId: authority.ownerId,
        consumedAtMs: null,
      });
      this.prune(authority.nowMs);
    }
    return decision;
  }

  consume(binding: DesktopIntentDecisionBinding): DesktopIntentSpawnAgentRoute | DesktopIntentContinueRunRoute {
    const tracked = this.tracked.get(binding.decisionId);
    if (!tracked) {
      throw new DesktopIntentRouteError("decision_not_found", "Desktop intent decision is unknown or no longer active.");
    }
    if (binding.nowMs - tracked.decision.createdAtMs > this.decisionTtlMs) {
      this.tracked.delete(binding.decisionId);
      throw new DesktopIntentRouteError("decision_expired", "Desktop intent decision has expired.");
    }
    if (tracked.consumedAtMs !== null) {
      throw new DesktopIntentRouteError("decision_replayed", "Desktop intent decision was already consumed.");
    }
    if (
      tracked.ownerId !== binding.ownerId ||
      tracked.decision.surfaceKind !== binding.surfaceKind ||
      tracked.decision.snapshotVersion !== binding.snapshotVersion ||
      tracked.decision.intent !== binding.expectedIntent
    ) {
      throw new DesktopIntentRouteError(
        "decision_binding_mismatch",
        "Desktop intent decision does not match the active owner, surface, snapshot, or effect.",
      );
    }
    // Consume before executing the effect. A callback failure must not make a
    // possibly-partial side effect replayable.
    tracked.consumedAtMs = binding.nowMs;
    return tracked.decision as DesktopIntentSpawnAgentRoute | DesktopIntentContinueRunRoute;
  }

  async apply<T>(
    binding: DesktopIntentDecisionBinding,
    effect: (decision: DesktopIntentSpawnAgentRoute | DesktopIntentContinueRunRoute) => T | Promise<T>,
  ): Promise<{ decision: DesktopIntentSpawnAgentRoute | DesktopIntentContinueRunRoute; result: T }> {
    const decision = this.consume(binding);
    const result = await effect(decision);
    return { decision, result };
  }

  async routeAndApply<T>(
    request: DesktopIntentRouteRequest,
    authority: DesktopIntentRouteAuthority,
    expectedIntent: DesktopIntentEffectKind,
    effect: (decision: DesktopIntentSpawnAgentRoute | DesktopIntentContinueRunRoute) => T | Promise<T>,
  ): Promise<{ decision: DesktopIntentSpawnAgentRoute | DesktopIntentContinueRunRoute; result: T }> {
    const decision = this.route(request, authority);
    if (decision.intent !== expectedIntent) {
      throw new DesktopIntentRouteError(
        decision.reasonCode,
        `Desktop intent effect rejected by canonical route policy (${decision.reasonCode}).`,
      );
    }
    return this.apply(
      {
        decisionId: decision.decisionId,
        ownerId: authority.ownerId,
        surfaceKind: decision.surfaceKind,
        snapshotVersion: decision.snapshotVersion,
        expectedIntent,
        nowMs: authority.nowMs,
      },
      effect,
    );
  }

  private prune(nowMs: number): void {
    for (const [decisionId, tracked] of this.tracked) {
      if (nowMs - tracked.decision.createdAtMs > this.decisionTtlMs) {
        this.tracked.delete(decisionId);
      }
    }
    while (this.tracked.size > this.maxTrackedDecisions) {
      const oldestDecisionId = this.tracked.keys().next().value as string | undefined;
      if (!oldestDecisionId) break;
      this.tracked.delete(oldestDecisionId);
    }
  }
}

function decideDesktopIntent(
  decisionId: string,
  request: DesktopIntentRouteRequest,
  authority: DesktopIntentRouteAuthority,
): DesktopIntentRoute {
  const snapshotVersion = normalizedSnapshotVersion(request.snapshotVersion);
  const syntax = request.syntaxFacts ?? {};
  const base = {
    decisionId,
    surfaceKind: normalizedSurfaceKind(request.surfaceKind),
    snapshotVersion,
    createdAtMs: authority.nowMs,
    inputHash: safeInputHash(request.utterance),
  };

  if (syntax.delegationNegated === true) {
    return {
      ...base,
      intent: "answer_inline",
      reasonCode: "explicit_delegation_negation",
      explanation: "Explicit delegation negation requires an inline response.",
    };
  }

  const proposal = request.proposal ?? proposalFromExplicitHandle(syntax);
  if (!proposal) {
    return {
      ...base,
      intent: "clarify",
      reasonCode: "proposal_required",
      explanation: "A structured route proposal is required.",
      missing: ["proposal"],
    };
  }

  if (proposal.intent === "clarify") {
    return {
      ...base,
      intent: "clarify",
      reasonCode: "surface_requested_clarification",
      explanation: "The structured proposal requires clarification before an effect.",
      missing: normalizedMissing(proposal.missing),
    };
  }

  if (proposal.intent === "answer_inline") {
    return {
      ...base,
      intent: "answer_inline",
      reasonCode: "inline_proposal",
      explanation: "The validated proposal requires an inline response.",
    };
  }

  if (authority.callerExecutionRole === "leaf") {
    return {
      ...base,
      intent: "reject",
      reasonCode: "caller_role_forbidden",
      code: "caller_role_forbidden",
      explanation: "Leaf workers cannot spawn or continue agents.",
    };
  }

  const requestedProvider = normalizedOptionalId(syntax.explicitProvider);
  if (requestedProvider && !authority.availableAdapterIds.includes(requestedProvider)) {
    return {
      ...base,
      intent: "reject",
      reasonCode: "provider_unavailable",
      code: "provider_unavailable",
      explanation: "The explicitly requested provider is not registered in this runtime.",
    };
  }

  if (proposal.intent === "continue_run") {
    const requestedSessionId = normalizedOptionalId(syntax.explicitSessionId);
    const requestedRunId = normalizedOptionalId(syntax.explicitRunId);
    if (!requestedSessionId && !requestedRunId) {
      return {
        ...base,
        intent: "clarify",
        reasonCode: "continuation_handle_required",
        explanation: "Continuation requires an explicit canonical session or run handle.",
        missing: ["syntaxFacts.explicitSessionId"],
      };
    }
    const target = authority.continuationTarget;
    if (
      !target ||
      target.status !== "open" ||
      (requestedSessionId && target.sessionId !== requestedSessionId) ||
      (requestedRunId && target.runId !== requestedRunId)
    ) {
      return {
        ...base,
        intent: "reject",
        reasonCode: "continuation_target_unavailable",
        code: "continuation_target_unavailable",
        explanation: "The requested continuation target is unavailable to the active owner.",
      };
    }
    return {
      ...base,
      intent: "continue_run",
      reasonCode: "continue_proposal",
      explanation: "The explicit continuation target passed kernel ownership and lifecycle checks.",
      sessionId: target.sessionId,
      runId: target.runId ?? null,
    };
  }

  const parentRunId = normalizedOptionalId(syntax.parentRunId);
  if (parentRunId && authority.parentRunAvailable !== true) {
    return {
      ...base,
      intent: "reject",
      reasonCode: "parent_run_unavailable",
      code: "parent_run_unavailable",
      explanation: "The requested parent run is unavailable to the active owner.",
    };
  }
  const requestedAgentCount = syntax.requestedAgentCount ?? 1;
  if (!Number.isSafeInteger(requestedAgentCount) || requestedAgentCount < 1 || requestedAgentCount > 8) {
    return {
      ...base,
      intent: "reject",
      reasonCode: "agent_count_unsupported",
      code: "agent_count_unsupported",
      explanation: "A route decision authorizes from one through eight sibling agents.",
    };
  }
  return {
    ...base,
    intent: "spawn_agent",
    reasonCode: "spawn_proposal",
    explanation: "The spawn proposal passed kernel role, provider, and parent-run checks.",
    requestedProvider,
    requestedAgentCount,
    parentRunId,
  };
}

function proposalFromExplicitHandle(syntax: DesktopIntentSyntaxFacts): DesktopIntentProposal | undefined {
  return normalizedOptionalId(syntax.explicitSessionId) || normalizedOptionalId(syntax.explicitRunId)
    ? { intent: "continue_run" }
    : undefined;
}

function normalizedSurfaceKind(value: string): string {
  return value.trim() || "unknown_surface";
}

function normalizedSnapshotVersion(value: string | undefined): string {
  return value?.trim() || "snapshot:unversioned";
}

function normalizedOptionalId(value: string | null | undefined): string | null {
  const normalized = value?.trim();
  return normalized ? normalized : null;
}

function normalizedMissing(value: readonly string[] | undefined): readonly string[] {
  const normalized = (value ?? []).map((field) => field.trim()).filter(Boolean);
  return normalized.length ? [...new Set(normalized)].slice(0, 10) : ["route_details"];
}

function safeInputHash(value: string): string {
  return createHash("sha256").update(value).digest("hex").slice(0, 16);
}
