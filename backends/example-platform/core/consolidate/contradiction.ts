import { compareStrings } from "../order";
/** Pure false-merge detector. Inputs are already committed claim facts; no model dependency. */
export interface ContradictionFact {
  claim_revision_id: string;
  entity_id: string;
  proposition_key_resolved: string;
  polarity?: "positive" | "negative";
  /** A predicate/slot marked single-valued may not hold two values over an overlap. */
  single_valued_key?: string;
  value_key?: string;
  valid_time?: { start: string; end: string } | null;
}
export interface SplitCandidate { entity_id: string; kind: "polarity" | "single_valued"; claim_revision_ids: readonly string[]; reason: string; }

const overlaps = (left: ContradictionFact, right: ContradictionFact): boolean => {
  if (!left.valid_time || !right.valid_time) return true; // unknown time cannot exonerate a contradictory permanent attribute
  return left.valid_time.start <= right.valid_time.end && right.valid_time.start <= left.valid_time.end;
};

export const scanContradictions = (facts: readonly ContradictionFact[]): readonly SplitCandidate[] => {
  const result: SplitCandidate[] = [];
  const ordered = [...facts].sort((a, b) => compareStrings(a.claim_revision_id, b.claim_revision_id));
  for (let index = 0; index < ordered.length; index++) for (let peer = index + 1; peer < ordered.length; peer++) {
    const left = ordered[index]!, right = ordered[peer]!;
    if (left.entity_id !== right.entity_id || !overlaps(left, right)) continue;
    if (left.proposition_key_resolved === right.proposition_key_resolved && left.polarity && right.polarity && left.polarity !== right.polarity) {
      result.push({ entity_id: left.entity_id, kind: "polarity", claim_revision_ids: [left.claim_revision_id, right.claim_revision_id], reason: "opposite polarity for one proposition over overlapping valid time" });
    }
    if (left.single_valued_key && left.single_valued_key === right.single_valued_key && left.value_key !== right.value_key) {
      result.push({ entity_id: left.entity_id, kind: "single_valued", claim_revision_ids: [left.claim_revision_id, right.claim_revision_id], reason: "two values for a single-valued attribute over overlapping valid time" });
    }
  }
  return result.sort((a, b) => compareStrings(`${a.entity_id}:${a.kind}:${a.claim_revision_ids.join(":")}`, `${b.entity_id}:${b.kind}:${b.claim_revision_ids.join(":")}`));
};
