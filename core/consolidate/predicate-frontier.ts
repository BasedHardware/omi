import { sha256CanonicalRedacted } from "../ledger";
import type { CanonicalClaim, PredicateAssertion, ProvisionalClaim } from "../schema";

export interface AliasEdge { from_predicate_id: string; to_predicate_id: string; from_slot_id?: string; to_slot_id?: string; }
export interface PredicateAliasFrontier { generation: string; edges: readonly AliasEdge[]; }
export interface PropositionIdentity { predicate_id: string; slots: readonly { slot_id: string; value_key: string }[]; }

/** Hash every semantic input: aliases are never an ambient mutable lookup. */
export const aliasFrontierGeneration = (edges: readonly AliasEdge[]): string => sha256CanonicalRedacted({
  kind: "predicate-alias-frontier-v1", edges: [...edges].sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b))),
});

const resolve = (value: string, edges: readonly AliasEdge[], field: "from_predicate_id" | "from_slot_id", target: "to_predicate_id" | "to_slot_id"): string => {
  const seen = new Set<string>(); let current = value;
  while (!seen.has(current)) {
    seen.add(current);
    const edge = edges.find((candidate) => candidate[field] === current && candidate[target]);
    if (!edge) break;
    current = edge[target]!;
  }
  return current;
};

export const rawPropositionKey = (identity: PropositionIdentity): string => sha256CanonicalRedacted({ predicate_id: identity.predicate_id, slots: [...identity.slots].sort((a, b) => a.slot_id.localeCompare(b.slot_id)) });
export const resolvedPropositionKey = (identity: PropositionIdentity, frontier: PredicateAliasFrontier): string => sha256CanonicalRedacted({
  frontier: frontier.generation,
  predicate_id: resolve(identity.predicate_id, frontier.edges, "from_predicate_id", "to_predicate_id"),
  slots: identity.slots.map((slot) => ({ ...slot, slot_id: resolve(slot.slot_id, frontier.edges, "from_slot_id", "to_slot_id") })).sort((a, b) => a.slot_id.localeCompare(b.slot_id)),
});

/** Only accepted append-only assertions participate in the persisted alias frontier. */
export const predicateAliasFrontier = (assertions: readonly PredicateAssertion[]): PredicateAliasFrontier => {
  const edges = assertions.filter((assertion) => assertion.relation === "alias_of" && assertion.lifecycle === "active" && assertion.admission === "accepted")
    .flatMap((assertion) => [{ from_predicate_id: assertion.predicate_id, to_predicate_id: assertion.target_predicate_id }, ...assertion.slot_aliases.map((slot) => ({ from_predicate_id: assertion.predicate_id, to_predicate_id: assertion.target_predicate_id, from_slot_id: slot.from_slot_id, to_slot_id: slot.to_slot_id }))]);
  return { generation: aliasFrontierGeneration(edges), edges };
};

const valueKey = (value: CanonicalClaim["arguments"][number]["value"]): string => value.kind === "literal" ? sha256CanonicalRedacted({ kind: value.kind, value: value.value }) : `${value.kind}:${value.ref}`;
export const propositionIdentityForClaim = (claim: CanonicalClaim | ProvisionalClaim): PropositionIdentity => ({
  // Historical rows without a vocabulary object stay auditable and resolvable as their raw spelling.
  predicate_id: claim.predicate_id ?? `raw:${claim.predicate}`,
  slots: claim.arguments.map((argument) => ({ slot_id: argument.slot_id, value_key: valueKey(argument.value) })),
});

export type ResolvedPropositionClaim<T extends CanonicalClaim | ProvisionalClaim> = T & {
  proposition_key_raw: string;
  proposition_key_resolved: string;
  predicate_alias_frontier: string;
};
/** A frontier change creates a new revision payload; it never mutates historical raw keys. */
export const resolveClaimProposition = <T extends CanonicalClaim | ProvisionalClaim>(claim: T, frontier: PredicateAliasFrontier): ResolvedPropositionClaim<T> => {
  const identity = propositionIdentityForClaim(claim);
  return { ...claim, proposition_key_raw: claim.proposition_key_raw ?? rawPropositionKey(identity), proposition_key_resolved: resolvedPropositionKey(identity, frontier), predicate_alias_frontier: frontier.generation };
};

export interface AliasCollision { raw_keys: readonly string[]; resolved_key: string; }
/** A collision is surfaced as a proposal. The caller must persist a derivation, never rewrite rows. */
export const detectAliasCollisions = (items: readonly { raw_key: string; resolved_key: string }[]): readonly AliasCollision[] => {
  const groups = new Map<string, Set<string>>();
  for (const item of items) groups.set(item.resolved_key, new Set([...(groups.get(item.resolved_key) ?? []), item.raw_key]));
  return [...groups].flatMap(([resolved_key, raw]) => raw.size > 1 ? [{ resolved_key, raw_keys: [...raw].sort() }] : []);
};

/** Explicit D35/consolidation derivation input; re-aliasing obtains a new digest. */
export const derivationFrontierDigest = (frontier: PredicateAliasFrontier, policy_version: string): string => sha256CanonicalRedacted({ predicate_alias_generation: frontier.generation, policy_version });
