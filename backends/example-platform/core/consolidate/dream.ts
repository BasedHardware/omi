import { sha256CanonicalRedacted } from "../ledger";
import { scanContradictions, type ContradictionFact, type SplitCandidate } from "./contradiction";

export type ConfirmationState = "pending" | "answered" | "dismissed" | "expired" | "invalidated";
export interface ConfirmationPair { pair_id: string; owner_account_id: string; left_ref: string; right_ref: string; frontier: string; state: ConfirmationState; evidence_generation: string; }
export const confirmationPairId = (owner: string, left: string, right: string, frontier: string): string => `confirmation:${sha256CanonicalRedacted({ owner, refs: [left, right].sort(), frontier })}`;
export const makeConfirmationPair = (owner: string, left: string, right: string, frontier: string, evidenceGeneration: string): ConfirmationPair => ({ pair_id: confirmationPairId(owner, left, right, frontier), owner_account_id: owner, left_ref: [left, right].sort()[0]!, right_ref: [left, right].sort()[1]!, frontier, state: "pending", evidence_generation: evidenceGeneration });
export const conservativeExpiry = (pair: ConfirmationPair): ConfirmationPair => ({ ...pair, state: "expired" });

export interface DreamCycleInput { cycle_id: string; facts: readonly ContradictionFact[]; previous_split_keys: readonly string[]; proposals: readonly { proposal_id: string; partition_hash: string; prior_partition_hash?: string; new_evidence: boolean }[]; }
export interface DreamCycleResult { split_candidates: readonly SplitCandidate[]; admitted_proposals: readonly string[]; repeated_partition_proposals: readonly string[]; }
/** One deterministic pass only. A proposal cannot reverse on variance alone. */
export const runDreamCycle = (input: DreamCycleInput): DreamCycleResult => {
  const split_candidates = scanContradictions(input.facts);
  const contradictionKeys = new Set(split_candidates.map((item) => `${item.entity_id}:${item.claim_revision_ids.join(":")}`));
  const admitted_proposals: string[] = [], repeated_partition_proposals: string[] = [];
  for (const proposal of input.proposals) {
    if (proposal.prior_partition_hash === proposal.partition_hash) { repeated_partition_proposals.push(proposal.proposal_id); continue; }
    // Reversal has an explicit evidence bit supplied by a pure prior-cycle comparison/authorization/owner event.
    if (proposal.prior_partition_hash && !proposal.new_evidence && ![...contradictionKeys].some((key) => !input.previous_split_keys.includes(key))) continue;
    admitted_proposals.push(proposal.proposal_id);
  }
  return { split_candidates, admitted_proposals, repeated_partition_proposals };
};
