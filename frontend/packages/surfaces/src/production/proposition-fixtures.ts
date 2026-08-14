import type { RefreshPhase, StoreStatus } from "@omi-core/domain";
import type { ProductionSynthesizedMemoryStore } from "./ProductionStores.js";
import type { SynthesizedMemoryItem, SynthesizedRecallReason, SynthesizedRecallState } from "@omi-core/contracts";

/**
 * Deterministic fixtures for the platform-generation Memories read model.
 *
 * They implement the same port FE-CORE's platform adapter implements, so this surface is
 * buildable and reviewable with no backend running — the discipline every existing
 * production surface was built with. No clock, no randomness: every value here is a
 * literal, so review renders are byte-stable across runs.
 */

/** Exported so a host can pass a fixed time into anything that needs one. */
export const PROPOSITION_FIXED_NOW = Date.UTC(2026, 7, 8, 12, 0, 0);

const DIGEST_A = "3f1c8a2b7d4e6019bb52c7a8f0d31e94c6b7a2058e1f4d3c9a06b25e7f81c4d2";
const DIGEST_B = "a71e05c9d3b48f26107ec5a9b2d84f31068ca7e5b93d21f4780ac6e5d1b39274";
const DIGEST_C = "5c2d90fe14ab7368d05e2c19f7b4a83612de07c5a94b1f28306ed7b5c294a1f0";
const DIGEST_D = "e04b7a1c8d29f536027bc4e1a95d803f16ca7d2e4b805f19c37ea6d2b418093c";

/**
 * A mixed corpus on purpose: some propositions carry citations and lineage, some only
 * one, one neither. Absent optional metadata is the normal case on this wire, so the
 * review corpus has to contain it or the absent-safe path is never actually looked at.
 */
function baseItems(): readonly SynthesizedMemoryItem[] {
  return [
    {
      id: "prop:0001",
      text: "You prefer concise updates when the next action is already clear.",
      citations: ["cite:conv:0912", "cite:conv:1044", "cite:conv:1180"],
      provenance: { synthesisVersion: "synth-2026.08.1", inputDigest: DIGEST_A, outputDigest: DIGEST_B },
    },
    {
      id: "prop:0002",
      text: "Your current project is a desktop-first redesign with shared product logic and thin native shells.",
      citations: ["cite:conv:0771"],
      provenance: { synthesisVersion: "synth-2026.08.1", inputDigest: DIGEST_B, outputDigest: DIGEST_C },
    },
    {
      id: "prop:0003",
      text: "You run the morning review around the single decision that matters most, rather than a list.",
      citations: ["cite:conv:0455", "cite:conv:0461"],
    },
    {
      id: "prop:0004",
      text: "You treat fast iteration and native feel as both being release criteria, not a trade between them.",
      provenance: { synthesisVersion: "synth-2026.07.9", inputDigest: DIGEST_C, outputDigest: DIGEST_D },
    },
    {
      id: "prop:0005",
      text: "entity:qa:000005 qa_memory (observed 2026-08-02T12:00:00.000Z).",
    },
  ];
}

function continuationItems(): readonly SynthesizedMemoryItem[] {
  return [
    {
      id: "prop:0006",
      text: "You keep review geometry fixed so an old window size cannot invalidate a comparison.",
      citations: ["cite:conv:1301"],
    },
    {
      id: "prop:0007",
      text: "You would rather see an honest degraded state than a confident wrong one.",
      provenance: { synthesisVersion: "synth-2026.08.1", inputDigest: DIGEST_D, outputDigest: DIGEST_A },
    },
  ];
}

function known(
  status: "complete" | "incomplete" | "degraded" | "partial",
  reasons: readonly SynthesizedRecallReason[],
  extras: { queryGap?: boolean; hasMore?: boolean } = {},
): SynthesizedRecallState {
  return {
    kind: "known",
    status,
    reasons,
    complete: status === "complete",
    queryGap: extras.queryGap ?? false,
    hasMore: extras.hasMore ?? false,
  };
}

export const PROPOSITION_FIXTURE_STATES = [
  "loading",
  "normal",
  "recall-unknown",
  "paged",
  "incomplete",
  "degraded",
  "partial",
  "query-gap",
  "empty",
  "unavailable",
] as const;

export type PropositionFixtureState = (typeof PROPOSITION_FIXTURE_STATES)[number];

type FixtureShape = {
  readonly first: readonly SynthesizedMemoryItem[];
  readonly recall: SynthesizedRecallState;
  readonly phase: RefreshPhase;
};

function shapeFor(state: PropositionFixtureState): FixtureShape {
  switch (state) {
    case "loading":
      return { first: [], recall: { kind: "unknown" }, phase: "initial-loading" };
    case "unavailable":
      return { first: [], recall: { kind: "unknown" }, phase: "unavailable" };
    case "recall-unknown":
      // Items with no envelope: the origin served rows but no completeness metadata. The
      // surface must render the rows and make no completeness or end-of-list claim.
      return { first: baseItems(), recall: { kind: "unknown" }, phase: "ready" };
    case "paged":
      return { first: baseItems(), recall: known("complete", [], { hasMore: true }), phase: "ready" };
    case "incomplete":
      return { first: baseItems(), recall: known("incomplete", ["accepted_work_pending"]), phase: "ready" };
    case "degraded":
      return { first: baseItems(), recall: known("degraded", ["projection_stale"]), phase: "ready" };
    case "partial":
      return { first: baseItems(), recall: known("partial", ["time_bound"]), phase: "ready" };
    case "query-gap":
      // Served successfully, matched nothing. Not the same story as an empty projection.
      return { first: [], recall: known("complete", [], { queryGap: true }), phase: "ready" };
    case "empty":
      return { first: [], recall: known("complete", []), phase: "ready" };
    default:
      return { first: baseItems(), recall: known("complete", []), phase: "ready" };
  }
}

export function fixturePropositionStore(
  state: PropositionFixtureState,
): ProductionSynthesizedMemoryStore {
  const shape = shapeFor(state);
  let items = shape.first;
  let recall = shape.recall;
  const listeners = new Set<() => void>();
  const notify = (): void => { for (const listener of listeners) listener(); };
  const status = (): StoreStatus => ({
    refresh: { phase: shape.phase, hasSavedData: items.length > 0 },
    // A read model has no outbox; the queue is structurally idle rather than simulated.
    queue: { phase: "idle", pendingCount: 0 },
  });
  return {
    status,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    async refresh() {
      notify();
    },
    async list() {
      return items;
    },
    recall() {
      return recall;
    },
    hasMore() {
      return recall.kind === "known" && recall.hasMore;
    },
    async loadMore() {
      if (recall.kind !== "known" || !recall.hasMore) return;
      items = [...items, ...continuationItems()];
      recall = known("complete", []);
      notify();
    },
  };
}
