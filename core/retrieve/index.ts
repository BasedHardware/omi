import type { ClaimPlacementStatus, GeneratedAdjacency } from "../ledger";
import type { CanonicalClaim, Entity, ProvisionalClaim } from "../schema";

export interface CommittedClaim {
  revision_id: string;
  claim: CanonicalClaim | ProvisionalClaim;
  placement_status: ClaimPlacementStatus;
}
export interface CommittedEntity { revision_id: string; entity: Entity; }
export interface GraphSnapshot {
  owner_account_id: string;
  claims: readonly CommittedClaim[];
  entities: readonly CommittedEntity[];
  adjacency: readonly GeneratedAdjacency[];
}

export type RetrievalRequest =
  | { owner_account_id: string; kind: "entity"; entity_id: string }
  | { owner_account_id: string; kind: "as_of"; date: string };

type RetrievableStatus = Exclude<ClaimPlacementStatus, "consumed">;

export interface RetrievedClaim {
  revision_id: string;
  claim: CanonicalClaim | ProvisionalClaim;
  entities: readonly Entity[];
  scope: CanonicalClaim["scope"];
  evidence_citations: readonly string[];
  dates: CanonicalClaim["temporal_scope"];
  status: RetrievableStatus;
  /** A withheld claim has not been falsely filed under any durable entity. */
  match: "matched" | "withheld_unplaced";
}
export interface OmissionAccounting {
  total_committed_claims: number;
  returned_canonical: number;
  withheld_items: number;
  withheld_by_status: Readonly<Record<Exclude<RetrievableStatus, "canonical">, number>>;
  /** Kept explicit so callers can distinguish an intentional result omission from withholding. */
  omitted_items: number;
}
export interface RetrievalResult { claims: readonly RetrievedClaim[]; omission_accounting: OmissionAccounting; }

/** Pure B5 query over a committed snapshot; it never drops an unresolved/abstained claim. */
export const retrieveCommittedGraph = (snapshot: GraphSnapshot, request: RetrievalRequest): RetrievalResult => {
  if (request.owner_account_id !== snapshot.owner_account_id) throw new Error("retrieval owner does not match graph snapshot");
  const entitiesById = new Map(snapshot.entities.map(({ entity }) => [entity.entity_id, entity]));
  const adjacencyByClaim = new Map<string, GeneratedAdjacency[]>();
  for (const edge of snapshot.adjacency) adjacencyByClaim.set(edge.claim_revision_id, [...(adjacencyByClaim.get(edge.claim_revision_id) ?? []), edge]);
  const withheldByStatus: Record<Exclude<RetrievableStatus, "canonical">, number> = { withheld_unresolved_subject: 0, withheld_abstained: 0 };
  const visible = snapshot.claims.filter((item) => {
    if (item.placement_status === "consumed") return false;
    const observedAt = item.claim.temporal_scope.observed_at;
    const temporalMatch = request.kind === "as_of" ? observedAt <= request.date : true;
    if (!temporalMatch) return false;
    // Withheld claims remain in every eligible result set because they have no safe entity filing.
    if (item.placement_status !== "canonical") return true;
    return request.kind === "as_of" || (adjacencyByClaim.get(item.revision_id) ?? []).some((edge) => edge.entity_id === request.entity_id);
  }).map((item) => {
    const edges = adjacencyByClaim.get(item.revision_id) ?? [];
    const entities = edges.map((edge) => entitiesById.get(edge.entity_id)).filter((entity): entity is Entity => entity !== undefined);
    if (item.placement_status !== "canonical") withheldByStatus[item.placement_status] += 1;
    return {
      revision_id: item.revision_id, claim: item.claim, entities, scope: item.claim.scope,
      evidence_citations: item.claim.evidence_refs, dates: item.claim.temporal_scope,
      status: item.placement_status, match: item.placement_status === "canonical" ? "matched" : "withheld_unplaced",
    };
  });
  const withheld_items = withheldByStatus.withheld_unresolved_subject + withheldByStatus.withheld_abstained;
  return {
    claims: visible,
    omission_accounting: {
      total_committed_claims: snapshot.claims.filter((item) => item.placement_status !== "consumed").length,
      returned_canonical: visible.filter((item) => item.status === "canonical").length,
      withheld_items, withheld_by_status: withheldByStatus, omitted_items: 0,
    },
  };
};

export interface RetrievalPort { retrieve(request: RetrievalRequest): Promise<RetrievalResult>; }
export interface ProvisionalInclusionPolicy { include_provisional: true; }
