/** Operational derivation only. It is intentionally not assignable to identity support. */
export interface CandidateDerivation {
  artifact_kind: "candidate_derivation";
  derivation_id: string;
  owner_account_id: string;
  source_ref: string;
  candidate_entity_id: string;
  strategy_ref: string;
  input_refs: readonly string[];
}
export interface CandidateSnapshot {
  snapshot_id: string;
  owner_account_id: string;
  frontier: number;
  candidates: readonly { entity_id: string; owner_account_id: string }[];
  derivations: readonly CandidateDerivation[];
}

export const candidateSnapshotContains = (snapshot: CandidateSnapshot, owner: string, entityId: string): boolean =>
  snapshot.owner_account_id === owner && snapshot.candidates.some((candidate) => candidate.entity_id === entityId && candidate.owner_account_id === owner);
