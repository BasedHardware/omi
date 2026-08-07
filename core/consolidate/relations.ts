import { compareStrings } from "../order";
import type { Predicate, PredicateAssertion } from "../schema";

export interface PredicateAlignmentPort { invoke(request: { strategy: string; version: string; input: unknown }): Promise<unknown>; }
export interface PredicateAlignmentProposal { assertions: readonly { predicate_id: string; target_predicate_id: string; slot_aliases?: readonly { from_slot_id: string; to_slot_id: string }[] }[]; }
/** `name` is the whole question this edge asks. The request used to carry the
 * sha256 predicate_id and the slot ids alone, so every adapter was asking which
 * of a list of digests meant the same thing -- unanswerable by construction. */
export interface PredicateAlignmentRequest { predicate_frontier: string; predicates: readonly { predicate_id: string; name: string; slot_ids: readonly string[] }[]; }

/** Model proposals are constrained to the committed frontier; no spelling is an authority by itself. */
export const invokePredicateAlignment = async (model: PredicateAlignmentPort, predicates: readonly Predicate[], frontier: string): Promise<readonly PredicateAssertion[]> => {
  const input: PredicateAlignmentRequest = { predicate_frontier: frontier, predicates: predicates.map((predicate) => ({ predicate_id: predicate.predicate_id, name: predicate.display_name || predicate.identity_name, slot_ids: predicate.slot_ids })).sort((left, right) => compareStrings(left.predicate_id, right.predicate_id)) };
  const response = await model.invoke({ strategy: "predicate-alignment", version: "dream-predicate-v1", input });
  const proposals = response && typeof response === "object" && Array.isArray((response as { assertions?: unknown }).assertions) ? (response as { assertions: unknown[] }).assertions : [];
  const known = new Map(predicates.map((predicate) => [predicate.predicate_id, predicate]));
  return proposals.flatMap((proposal, index) => {
    const item = proposal && typeof proposal === "object" ? proposal as { predicate_id?: unknown; target_predicate_id?: unknown; slot_aliases?: unknown } : {};
    if (typeof item.predicate_id !== "string" || typeof item.target_predicate_id !== "string" || item.predicate_id === item.target_predicate_id || !known.has(item.predicate_id) || !known.has(item.target_predicate_id)) return [];
    const slots = Array.isArray(item.slot_aliases) ? item.slot_aliases.flatMap((slot) => slot && typeof slot === "object" && typeof (slot as { from_slot_id?: unknown }).from_slot_id === "string" && typeof (slot as { to_slot_id?: unknown }).to_slot_id === "string" ? [{ from_slot_id: (slot as { from_slot_id: string }).from_slot_id, to_slot_id: (slot as { to_slot_id: string }).to_slot_id }] : []) : [];
    return [{ assertion_id: `predicate-alias:${frontier}:${index}:${item.predicate_id}:${item.target_predicate_id}`, owner_account_id: known.get(item.predicate_id)!.owner_account_id, predicate_id: item.predicate_id, relation: "alias_of" as const, target_predicate_id: item.target_predicate_id, slot_aliases: slots, alias_frontier: frontier, admission: "accepted" as const, lifecycle: "active" as const, supersedes_assertion_id: null }];
  }).sort((left, right) => compareStrings(left.assertion_id, right.assertion_id));
};
