import type { UnitBoundaryJudgment } from "../extract/provisional";
import type { PlacementArtifact } from "../ledger";
import type { ScopeRolePlan } from "./placement";
import type { Mention } from "../schema";

export interface FlywheelArtifactInput {
  provisional_revision_id: string;
  canonical_claim_revision_id: string | null;
  scope_plan: ScopeRolePlan;
  unit_boundary: UnitBoundaryJudgment;
  /** Session graph facts, never boundary-model self-report. */
  mentions?: readonly Mention[];
  newly_minted_entity_ids?: readonly string[];
}

const underspecifiedSurface = /^(?:i|me|my|mine|myself|we|us|our|ours|ourselves|you|your|yours|yourself|yourselves|he|him|his|himself|she|her|hers|herself|it|its|itself|they|them|their|theirs|themselves|this|that|these|those|someone|somebody|something|anyone|anybody|anything|person|people)$/iu;

/**
 * D41 artifact routing. A semantic boundary abstention or unresolved placement
 * is queued; only a model-accepted, fully placed unit enters auto-placement.
 * There is intentionally no score, context-window, or presence threshold here.
 */
export const buildFlywheelArtifacts = (input: FlywheelArtifactInput): readonly PlacementArtifact[] => {
  const base = input.provisional_revision_id;
  const auto = input.unit_boundary.decision === "accept_ltm" && input.scope_plan.confidently_placed && input.canonical_claim_revision_id !== null;
  const margin = input.unit_boundary.margin ?? null;
  const minted = new Set(input.newly_minted_entity_ids ?? []);
  const resolvedMentions = (input.mentions ?? []).filter((mention) => mention.resolution === "resolved" && mention.entity_id !== null);
  const risk_markers = [...new Set([
    ...(margin === "low" ? ["low_margin" as const] : []),
    ...(resolvedMentions.some((mention) => minted.has(mention.entity_id!)) ? ["new_entity" as const] : []),
    ...(resolvedMentions.some((mention) => underspecifiedSurface.test(mention.surface.trim())) ? ["resolved_pronoun" as const] : []),
  ])];
  const details = { margin, risk_markers, unit_boundary_decision: input.unit_boundary.decision, scope_locality: input.scope_plan.scope?.locality ?? null };
  if (auto) return [{ artifact_id: `auto-placement:${base}`, kind: "auto_placement_log", provisional_revision_id: base, canonical_claim_revision_id: input.canonical_claim_revision_id, ...details }];
  // These are mutually exclusive operational strata: an explicit model
  // abstention is not also a confirmation-queue item.
  return [input.unit_boundary.decision === "abstain"
    ? { artifact_id: `abstention-set:${base}`, kind: "abstention_set" as const, provisional_revision_id: base, canonical_claim_revision_id: null, ...details }
    : { artifact_id: `confirmation-queue:${base}`, kind: "confirmation_queue" as const, provisional_revision_id: base, canonical_claim_revision_id: null, ...details }];
};
