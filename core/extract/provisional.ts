import { hasDistinctArgumentSlotIds, type Evidence, type ProvisionalClaim } from "../schema";

/** B2 adapter input: extraction may populate this only from retained L1/evidence context. */
export type ProvisionalClaimAdapterInput = ProvisionalClaim;

export type StmSufficiencyResult =
  | { ok: true; claim: ProvisionalClaim }
  | { ok: false; errors: readonly string[] };

/** D44 semantic boundary output. Only a model strategy may make this decision. */
export type DecisionMargin = "low" | "medium" | "high";
/** `risk_markers` are the only diagnostic this edge produces; parsers used to
 * validate then discard them, so an abstention arrived with no stated cause. */
export type UnitBoundaryJudgment =
  | { decision: "accept_ltm"; margin?: DecisionMargin; risk_markers?: readonly string[] }
  | { decision: "abstain"; reason: string; margin?: DecisionMargin; risk_markers?: readonly string[] };

/**
 * Input-structure validation only. It deliberately does not infer lost role,
 * evidence, or context data and is not an STM→LTM unit-boundary decision.
 */
export const checkStmSufficiency = (
  claim: ProvisionalClaimAdapterInput,
  evidence: readonly Evidence[],
  requiredRoleSlots: readonly string[],
): StmSufficiencyResult => {
  const errors: string[] = [];
  if (!hasDistinctArgumentSlotIds(claim.arguments)) errors.push("duplicate argument slot_id");
  const actualSlots = new Set(claim.arguments.map((argument) => argument.slot_id));
  for (const slot of requiredRoleSlots) if (!actualSlots.has(slot)) errors.push(`missing required role slot: ${slot}`);
  if (!Array.isArray(claim.ambiguity_markers)) errors.push("missing ambiguity markers");
  if (!claim.context_packet?.version) errors.push("missing versioned referent/topic context packet");
  if (claim.evidence_refs.length === 0) errors.push("missing evidence references");
  const evidenceById = new Map(evidence.map((item) => [item.evidence_id, item]));
  for (const ref of claim.evidence_refs) {
    const item = evidenceById.get(ref);
    if (!item) errors.push(`unknown evidence: ${ref}`);
    else if (item.range.end <= item.range.start) errors.push(`invalid evidence range: ${ref}`);
  }
  return errors.length ? { ok: false, errors } : { ok: true, claim };
};
