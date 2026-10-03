// One entry point from "what the user said" to "which agent runs it".
//
// The pieces each answer one question — agent-mention.ts what was asked for,
// adapter-scoring.ts what fits, agent-install.ts what to say when the answer is
// "nothing" — and this composes them into the single decision a surface needs
// before it hands a proposal to `DesktopIntentRouter`.
//
// Nothing here executes an attempt or touches the kernel. It returns a decision
// the kernel is still free to reject; `explicitProvider` on the returned route
// is exactly what belongs in `DesktopIntentSyntaxFacts`.

import type { ProductionAdapterId } from "../adapters/interface.js";
import {
  agentUnavailableGuidance,
  type AgentUnavailableGuidance,
} from "./agent-install.js";
import {
  explicitProviderFrom,
  negatedAgentsFrom,
  type MentionableAgentId,
} from "./agent-mention.js";
import {
  scoreAdapters,
  selectAdapterChain,
  selectRequestedAdapterChain,
  type AdapterCandidate,
  type AgentTaskRequirements,
} from "./adapter-scoring.js";

export interface AgentRouteRequest {
  /** Raw utterance, e.g. the push-to-talk transcript. */
  readonly utterance: string;
  /** Adapters registered and activated in this runtime, with capabilities. */
  readonly connected: readonly AdapterCandidate[];
  readonly requirements?: AgentTaskRequirements;
}

export interface AgentRouteSelected {
  readonly kind: "route";
  /** Agent to run on. */
  readonly adapterId: ProductionAdapterId;
  /** Full attempt order: `adapterId` first, then fallbacks. */
  readonly chain: readonly ProductionAdapterId[];
  /** True when the user named this agent. */
  readonly explicit: boolean;
  /**
   * Value for `DesktopIntentSyntaxFacts.explicitProvider`. Null when the user
   * named nobody, which keeps the kernel's own provider checks unchanged.
   */
  readonly explicitProvider: string | null;
  /**
   * Set when the user named an agent that is connected but cannot do this task.
   * The surface should say so rather than silently substituting.
   */
  readonly requestedButIneligible?: {
    readonly adapterId: MentionableAgentId;
    readonly missing: readonly string[];
  };
  readonly reasons: readonly string[];
}

export interface AgentRouteInstallRequired {
  readonly kind: "install_required";
  /** The agent the user named. */
  readonly adapterId: MentionableAgentId;
  readonly guidance: AgentUnavailableGuidance;
}

export interface AgentRouteUnavailable {
  readonly kind: "no_agent_available";
  /** Why each connected agent was ruled out. */
  readonly reasons: readonly string[];
}

export type AgentRoute =
  | AgentRouteSelected
  | AgentRouteInstallRequired
  | AgentRouteUnavailable;

/**
 * Decide which agent should run an utterance.
 *
 * - Named an agent that isn't connected → `install_required`.
 * - Named a connected agent → it leads, the ranked remainder is its fallback.
 * - Named nobody → the best-scoring agent leads.
 * - Nothing can do the job → `no_agent_available`.
 */
export function routeAgentRequest(request: AgentRouteRequest): AgentRoute {
  const { utterance, connected: allConnected, requirements = {} } = request;
  const requested = explicitProviderFrom(utterance);

  // An agent the user ruled out is dropped before scoring, so it can be neither
  // selected nor fallen back to.
  const excluded = new Set<string>(negatedAgentsFrom(utterance));
  const connected = allConnected.filter(
    (candidate) => !excluded.has(candidate.adapterId),
  );
  if (connected.length === 0 && allConnected.length > 0) {
    return {
      kind: "no_agent_available",
      reasons: [`every connected agent was ruled out (${[...excluded].join(", ")})`],
    };
  }

  const scored = scoreAdapters(connected, requirements);
  const rankedChain = selectAdapterChain(connected, requirements);

  if (requested) {
    const isConnected = connected.some(
      (candidate) => candidate.adapterId === requested,
    );

    if (!isConnected) {
      return {
        kind: "install_required",
        adapterId: requested,
        guidance: agentUnavailableGuidance(requested),
      };
    }

    const chain = selectRequestedAdapterChain(connected, requested, requirements);
    const leads = chain[0] === requested;

    if (leads) {
      return {
        kind: "route",
        adapterId: requested as ProductionAdapterId,
        chain,
        explicit: true,
        explicitProvider: requested,
        reasons: [`${requested} was named in the request`],
      };
    }

    // Connected, but it fails a hard requirement, so it was dropped from the
    // chain. Route to what can actually do the job and report the substitution.
    const skipped = scored.find((entry) => entry.adapterId === requested);
    if (rankedChain.length === 0) {
      return { kind: "no_agent_available", reasons: reasonsFrom(scored) };
    }
    return {
      kind: "route",
      adapterId: rankedChain[0],
      chain: rankedChain,
      explicit: false,
      // The named agent cannot run this, so it must not be proposed to the
      // kernel as the requested provider.
      explicitProvider: null,
      requestedButIneligible: {
        adapterId: requested,
        missing: skipped?.missing ?? [],
      },
      reasons: [
        `${requested} cannot run this task (${(skipped?.missing ?? []).join(", ") || "unmet requirements"})`,
        `${rankedChain[0]} selected instead`,
      ],
    };
  }

  if (rankedChain.length === 0) {
    return { kind: "no_agent_available", reasons: reasonsFrom(scored) };
  }

  const winner = scored.find((entry) => entry.adapterId === rankedChain[0]);
  return {
    kind: "route",
    adapterId: rankedChain[0],
    chain: rankedChain,
    explicit: false,
    explicitProvider: null,
    reasons: winner?.reasons ?? [],
  };
}

function reasonsFrom(scored: readonly { adapterId: string; missing: readonly string[] }[]): readonly string[] {
  if (scored.length === 0) return ["no agents are connected"];
  return scored.map(
    (entry) => `${entry.adapterId}: missing ${entry.missing.join(", ") || "nothing"}`,
  );
}
