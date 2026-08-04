import type { Evidence, ProvisionalClaim } from "../../core/schema";
import type { UnitBoundaryJudgment } from "../../core/extract/provisional";
import type { ModelPort } from "./port";

/** Extract bookkeeping about offset collisions — not a durability signal. */
const isSurfaceAmbiguityMarker = (marker: string): boolean => marker.startsWith("ambiguous_surface:");

/** Imperative D44 edge. Presence validation never supplies this semantic judgment. */
export const buildUnitBoundaryRequest = (claim: ProvisionalClaim, evidence: readonly Evidence[]) => {
  const byId = new Map(evidence.map((item) => [item.evidence_id, item]));
  const source_excerpts = claim.evidence_refs.map((evidence_id) => {
    const item = byId.get(evidence_id);
    if (!item?.excerpt) throw new Error(`unit-boundary request lacks retained source excerpt: ${evidence_id}`);
    return { evidence_id, excerpt: item.excerpt, range: item.range };
  });
  if (!source_excerpts.length) throw new Error("unit-boundary request lacks retained source excerpt");
  // Strip ambiguous_surface:* before the model sees them: they mean "I/you
  // appeared twice in the excerpt", and live runs treated them as abstain
  // reasons, wiping durable owner self-facts. Durability markers (one_off,
  // hedged, …) stay.
  const ambiguity_markers = claim.ambiguity_markers.filter((marker) => !isSurfaceAmbiguityMarker(marker));
  return { claim_revision_id: claim.claim_revision_id, predicate: claim.predicate, arguments: claim.arguments, ambiguity_markers, context_packet: claim.context_packet, source_excerpts };
};

export const invokeUnitBoundaryStrategy = async (port: ModelPort, claim: ProvisionalClaim, evidence: readonly Evidence[]): Promise<UnitBoundaryJudgment> => {
  const input = buildUnitBoundaryRequest(claim, evidence);
  const judged = await port.invoke({ strategy: "stm-ltm-unit-boundary", version: "v3", input: {
    ...input,
  } });
  if (typeof judged !== "object" || judged === null || !["accept_ltm", "abstain"].includes((judged as { decision?: unknown }).decision as string)) throw new Error("invalid STM/LTM unit-boundary model judgment");
  const value = judged as { decision: "accept_ltm" | "abstain"; margin?: unknown; reason?: unknown; risk_markers?: unknown };
  const margin = ["low", "medium", "high"].includes(value.margin as string) ? value.margin as "low" | "medium" | "high" : undefined;
  // Carried through rather than dropped: an abstention with no recorded risk is
  // indistinguishable from one the edge never made.
  const risk_markers = Array.isArray(value.risk_markers) ? value.risk_markers.filter((marker): marker is string => typeof marker === "string" && !!marker.trim()) : undefined;
  if (value.decision === "accept_ltm") return { decision: "accept_ltm", ...(margin ? { margin } : {}), ...(risk_markers?.length ? { risk_markers } : {}) };
  if (typeof value.reason !== "string" || !value.reason) throw new Error("STM/LTM abstention requires a reason");
  return { decision: "abstain", reason: value.reason, ...(margin ? { margin } : {}), ...(risk_markers?.length ? { risk_markers } : {}) };
};
