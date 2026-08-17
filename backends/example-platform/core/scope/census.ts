import type { GraphSnapshot } from "../retrieve";

export interface OperationalCensus {
  placement_counts: { auto: number; queued: number; abstained: number };
  predicted_temporal_kinds: Readonly<Record<string, number>>;
  scope_distribution: Readonly<Record<string, number>>;
  boundary_distribution: Readonly<Record<string, number>>;
  claims_per_session: Readonly<Record<string, number>>;
  /** Model-derived proxies only; these are explicitly not gold measurements. */
  proxy_risk_counts: Readonly<Record<string, number>>;
}

const increment = (record: Record<string, number>, key: string): void => { record[key] = (record[key] ?? 0) + 1; };

/** Pure operational census over a committed graph; no gold-dependent fields are inferred. */
export const aggregateOperationalCensus = (graph: GraphSnapshot): OperationalCensus => {
  const placement_counts = { auto: 0, queued: 0, abstained: 0 };
  const boundary_distribution: Record<string, number> = {};
  const proxy_risk_counts: Record<string, number> = {};
  for (const artifact of graph.placement_artifacts ?? []) {
    if (artifact.kind === "auto_placement_log") placement_counts.auto += 1;
    else if (artifact.kind === "confirmation_queue") placement_counts.queued += 1;
    else placement_counts.abstained += 1;
    increment(boundary_distribution, artifact.unit_boundary_decision);
    for (const marker of artifact.risk_markers) increment(proxy_risk_counts, marker);
  }
  const predicted_temporal_kinds: Record<string, number> = {};
  const scope_distribution: Record<string, number> = {};
  const claims_per_session: Record<string, number> = {};
  const evidence = new Map((graph.evidence ?? []).map((item) => [item.evidence.evidence_id, item.evidence]));
  const events = new Map((graph.events ?? []).map((item) => [item.event.event_revision_id, item.event]));
  for (const item of graph.claims) if (item.claim.lifecycle === "canonical") {
    increment(predicted_temporal_kinds, item.claim.temporal_scope.valid_time.typed_expression.kind);
    increment(scope_distribution, item.claim.scope.locality);
    const session = item.claim.evidence_refs.map((id) => evidence.get(id)).map((item) => item && events.get(item.event_revision_id)?.capture_session_id).find((item): item is string => Boolean(item)) ?? "unlinked_evidence";
    increment(claims_per_session, session);
  }
  return { placement_counts, predicted_temporal_kinds, scope_distribution, boundary_distribution, claims_per_session, proxy_risk_counts };
};
