import { createHash } from "node:crypto";

export type Disposition = "admit" | "reinforce" | "supersede" | "coexist" | "dispute" | "reject" | "defer_review";
export interface LeasedInput { provisional_revision_id: string; entity_id: string | null; /** legacy/raw historical key */ proposition_key: string; proposition_key_resolved?: string; alias_frontier_generation?: string; review_attempt: number; max_review_attempts: number; }
export interface CanonicalSnapshot { canonical_claim_id: string; proposition_key: string; proposition_key_resolved?: string; alias_frontier_generation?: string; }
/** Identity linkage: attach a claim to an entity; it is not proposition consolidation. */
export interface IdentityLinkage { kind: "identity_linkage"; entity_id: string; }
/** Consolidation: reinforce/supersede exactly one proposition across captures. */
export interface Consolidation { kind: "consolidation"; canonical_claim_id: string; proposition_key: string; }
/** Synthesis: a higher-level memory, only with a stated justification. */
export interface Synthesis { kind: "synthesis"; justification_evidence_refs: readonly string[]; }
export type PlacementOperation = IdentityLinkage | Consolidation | Synthesis | null;
export interface PlacementResultRow {
  input_provisional_revision_id: string;
  disposition: Disposition;
  operation: PlacementOperation;
  re_resolution_trigger?: string;
}
export interface PlacementBatch { batch_id: string; leased_inputs: readonly LeasedInput[]; snapshot: readonly CanonicalSnapshot[]; results: readonly PlacementResultRow[]; }
export interface AllocatedPlacementPlan { offline_experiment: true; allocations: Readonly<Record<string, string>>; results: readonly PlacementResultRow[]; }

export class BatchValidationError extends Error { constructor(readonly errors: readonly string[]) { super(errors.join("; ")); } }
const matchKey = (item: { proposition_key: string; proposition_key_resolved?: string }): string => item.proposition_key_resolved ?? item.proposition_key;
const deterministicId = (batch: string, input: string) => `canonical:${createHash("sha256").update(`${batch}:${input}`).digest("hex").slice(0, 16)}`;

/** Pure B3.2-shaped validation and deterministic allocation; deliberately no batch lease/outbox/concurrency behavior. */
export const validateAndAllocatePlacement = (batch: PlacementBatch): AllocatedPlacementPlan => {
  const errors: string[] = [];
  const inputs = new Map(batch.leased_inputs.map((input) => [input.provisional_revision_id, input]));
  const resultIds = batch.results.map((row) => row.input_provisional_revision_id);
  const unique = new Set(resultIds);
  if (resultIds.length !== batch.leased_inputs.length) errors.push("exact partition count mismatch");
  if (unique.size !== resultIds.length) errors.push("duplicate disposition row");
  for (const input of batch.leased_inputs) if (!unique.has(input.provisional_revision_id)) errors.push(`missing disposition: ${input.provisional_revision_id}`);
  for (const id of unique) if (!inputs.has(id)) errors.push(`unknown leased input: ${id}`);
  const canonical = new Map(batch.snapshot.map((claim) => [claim.canonical_claim_id, claim]));
  for (const row of batch.results) {
    const input = inputs.get(row.input_provisional_revision_id);
    if (!input) continue;
    if (row.operation?.kind === "identity_linkage" && input.entity_id !== null && row.operation.entity_id !== input.entity_id) errors.push(`identity linkage mismatches input entity: ${input.provisional_revision_id}`);
    if (row.operation?.kind === "consolidation") {
      const target = canonical.get(row.operation.canonical_claim_id);
      if (!target) errors.push(`unknown canonical reference: ${row.operation.canonical_claim_id}`);
      else if (matchKey(target) !== row.operation.proposition_key || matchKey(input) !== row.operation.proposition_key) errors.push(`unrelated proposition consolidation: ${input.provisional_revision_id}`);
      // Resolved keys are meaningful only at one declared frontier; otherwise a re-alias could
      // silently reinterpret history while a batch is being allocated.
      else if ((input.proposition_key_resolved || target.proposition_key_resolved) && (!input.alias_frontier_generation || !target.alias_frontier_generation || input.alias_frontier_generation !== target.alias_frontier_generation)) errors.push(`frontier mismatch consolidation: ${input.provisional_revision_id}`);
    }
    if (row.operation?.kind === "synthesis" && row.operation.justification_evidence_refs.length === 0) errors.push(`unjustified synthesis: ${input.provisional_revision_id}`);
    if (row.disposition === "defer_review" && (!row.re_resolution_trigger || input.review_attempt >= input.max_review_attempts)) errors.push(`unbounded or triggerless defer_review: ${input.provisional_revision_id}`);
  }
  if (errors.length) throw new BatchValidationError(errors);
  const allocations: Record<string, string> = {};
  for (const row of batch.results) if (row.disposition === "admit" || row.operation?.kind === "synthesis") allocations[row.input_provisional_revision_id] = deterministicId(batch.batch_id, row.input_provisional_revision_id);
  return { offline_experiment: true, allocations, results: batch.results };
};
