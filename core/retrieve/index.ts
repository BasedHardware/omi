import type { ClaimPlacementStatus, GeneratedAdjacency } from "../ledger";
import { canonicalHandleAt, type EntityTable } from "../resolve/entities";
import type { CanonicalClaim, ClaimArgument, Entity, Evidence, IdentityConstraint, L1Event, ProvisionalClaim } from "../schema";
import { sha256CanonicalRedacted } from "../ledger";

export interface CommittedClaim {
  revision_id: string;
  claim: CanonicalClaim | ProvisionalClaim;
  placement_status: ClaimPlacementStatus;
  /** Durable commit order supplied by persistence; never infer recency from an ID. */
  commit_sequence?: number;
}
export interface CommittedEntity { revision_id: string; entity: Entity; }
export interface CommittedIdentity { revision_id: string; constraint: IdentityConstraint; }
export interface CommittedEvent { revision_id: string; event: L1Event; }
export interface CommittedEvidence { revision_id: string; evidence: Evidence; }
export interface GraphSnapshot {
  owner_account_id: string;
  /** Commit-frontier sequence when supplied by persistence; fixtures may omit it. */
  graph_generation?: string | number;
  claims: readonly CommittedClaim[];
  entities: readonly CommittedEntity[];
  identity_constraints?: readonly CommittedIdentity[];
  events?: readonly CommittedEvent[];
  evidence?: readonly CommittedEvidence[];
  adjacency: readonly GeneratedAdjacency[];
}

export interface PolicyClass { subject_class: string; sensitivity: string; capture_class: string; }
export interface PolicyClassifier {
  version: string;
  classify(claim: CanonicalClaim | ProvisionalClaim, evidence: readonly Evidence[]): PolicyClass;
}
/** Open-world classifier: no label is assumed sensitive or person-specific without a versioned rule. */
export const genericPolicyClassifier: PolicyClassifier = {
  version: "policy-classifier-generic-v1",
  classify: (claim, evidence) => {
    const labels = new Set([...claim.policy_labels, ...evidence.flatMap((item) => item.policy_labels)]);
    const take = (prefix: string, fallback: string) => [...labels].sort().find((item) => item.startsWith(prefix))?.slice(prefix.length) ?? fallback;
    return { subject_class: take("subject:", "generic"), sensitivity: take("sensitivity:", "generic"), capture_class: take("capture:", "generic") };
  },
};
export const policyPartitionLabel = (policy: PolicyClass): string => `subject_class=${policy.subject_class}|sensitivity=${policy.sensitivity}|capture_class=${policy.capture_class}`;

export interface EvidenceSpan {
  evidence_id: string;
  event_revision_id: string;
  capture_session_id: string;
  excerpt: string | null;
  range: { start: number; end: number };
  policy_labels: readonly string[];
}
export interface LiveClaimView {
  claim_revision_id: string;
  canonical_claim_id: string | null;
  claim_lineage_id: string;
  predicate: string;
  arguments: readonly ClaimArgument[];
  observed_at: string;
  /** Projection-only: core claims intentionally carry only observation time. */
  valid_time: string | null;
  temporal_precision: string;
  time_anchor: { kind: "valid_time"; value: string } | { kind: "imprecise_time"; observed_at: string; marker: "observed_at_fallback_imprecise" };
  evidence_refs: readonly string[];
  evidence_spans: readonly EvidenceSpan[];
  scope: CanonicalClaim["scope"];
  source_language: string;
  policy_labels: readonly string[];
  policy_class: PolicyClass;
  placement_status: RetrievableStatus;
}
export interface TreeInputSnapshot {
  owner_account_id: string;
  graph_generation: string;
  account_timezone: string;
  claims: readonly LiveClaimView[];
  identity_constraints: readonly IdentityConstraint[];
  evidence_index: readonly EvidenceSpan[];
  policy_classes: Readonly<Record<string, PolicyClass>>;
  liveness_hook_version: string;
  classifier_version: string;
  /** Evidence-chain faults are visible to callers instead of being silently projected away. */
  diagnostics: readonly ProjectionDiagnostic[];
}
export type ProjectionDiagnostic = {
  kind: "missing_evidence" | "missing_event";
  claim_revision_id: string;
  evidence_ref: string;
  message: string;
} | {
  /** A multi-revision lineage without edges cannot honestly infer recency. */
  kind: "missing_commit_sequence";
  claim_lineage_id: string;
  claim_revision_ids: readonly string[];
  message: string;
};
export interface TreeInputOptions {
  account_timezone: string;
  valid_time_by_claim_revision?: Readonly<Record<string, string | null>>;
  classifier?: PolicyClassifier;
  /** Versioned future hook for dispute/purge; false removes an otherwise live item. */
  liveness_hook?: { version: string; include(item: CommittedClaim): boolean };
  graph_generation?: string | number;
}

const canonicalEntityIds = (snapshot: GraphSnapshot): Map<string, string> => {
  const constraints = snapshot.identity_constraints?.map((item) => item.constraint) ?? [];
  const table: EntityTable = { owner_account_id: snapshot.owner_account_id, entities: snapshot.entities.map((item) => item.entity), constraints };
  const asOf = Number.MAX_SAFE_INTEGER;
  const byHandle = new Map<string, string[]>();
  for (const entity of table.entities) {
    const canonical = canonicalHandleAt(table, entity.entity_id, asOf) ?? entity.handle;
    byHandle.set(canonical, [...(byHandle.get(canonical) ?? []), entity.entity_id]);
  }
  const result = new Map<string, string>();
  for (const [canonicalHandle, ids] of byHandle) {
    // Reversible survivor rule: the entity already carrying the canonical (lexical-minimum)
    // handle wins; only malformed duplicate handles fall back to entity-id ordering.
    const survivor = ids.find((id) => table.entities.find((entity) => entity.entity_id === id)?.handle === canonicalHandle) ?? [...ids].sort()[0]!;
    for (const id of ids) result.set(id, survivor);
  }
  return result;
};

interface LiveClaimSelection { claims: readonly CommittedClaim[]; diagnostics: readonly ProjectionDiagnostic[]; }

/** D35 i-lite: pick one current member per lineage, after consumed + versioned erasure. */
const selectLiveCommittedClaims = (snapshot: GraphSnapshot, hook: TreeInputOptions["liveness_hook"]): LiveClaimSelection => {
  const eligible = snapshot.claims.filter((item) => item.placement_status !== "consumed" && (hook?.include(item) ?? true));
  const rank = (item: CommittedClaim) => item.placement_status === "canonical" ? 2 : 1;
  const explicitlySupersedes = (newer: CommittedClaim, older: CommittedClaim): boolean => {
    const sourceIds = newer.claim.lifecycle === "canonical" ? newer.claim.source_provisional_revision_ids : [];
    const explicit = newer.claim.lifecycle === "canonical" ? newer.claim.supersedes_revision_ids ?? [] : [];
    return [...sourceIds, ...explicit].includes(older.revision_id);
  };
  // This content-derived key is deliberately independent of ingestion/array order.
  const stableTieBreak = (item: CommittedClaim): string => sha256CanonicalRedacted({ revision_id: item.revision_id, claim: item.claim, placement_status: item.placement_status });
  const byLineage = new Map<string, CommittedClaim[]>();
  for (const item of eligible) byLineage.set(item.claim.claim_lineage_id, [...(byLineage.get(item.claim.claim_lineage_id) ?? []), item]);
  const diagnostics: ProjectionDiagnostic[] = [];
  const winners = [...byLineage.entries()].map(([lineage, members]) => {
    if (members.length === 1) return members[0]!;
    // A unique explicit head is authoritative, even when its commit sequence is lower.
    const explicitHeads = members.filter((candidate) => !members.some((other) => other !== candidate && explicitlySupersedes(other, candidate)));
    if (explicitHeads.length === 1 && members.some((candidate) => explicitlySupersedes(explicitHeads[0]!, candidate))) return explicitHeads[0]!;
    if (members.some((member) => member.commit_sequence === undefined)) {
      diagnostics.push({ kind: "missing_commit_sequence", claim_lineage_id: lineage, claim_revision_ids: members.map((member) => member.revision_id).sort(), message: `lineage ${lineage} has multiple revisions without a complete commit sequence; selected by stable content hash` });
      return [...members].sort((left, right) => stableTieBreak(left).localeCompare(stableTieBreak(right)))[0]!;
    }
    return [...members].sort((left, right) => {
      const sequence = right.commit_sequence! - left.commit_sequence!;
      if (sequence) return sequence;
      const placement = rank(right) - rank(left);
      return placement || stableTieBreak(left).localeCompare(stableTieBreak(right));
    })[0]!;
  });
  return { claims: winners.sort((left, right) => left.revision_id.localeCompare(right.revision_id)), diagnostics };
};

/** Returns deterministic live members; projection callers also receive selection diagnostics. */
export const liveCommittedClaims = (snapshot: GraphSnapshot, hook: TreeInputOptions["liveness_hook"]): readonly CommittedClaim[] =>
  selectLiveCommittedClaims(snapshot, hook).claims;

/** Pure committed-graph projection. It intentionally has no tree or model dependency. */
export const projectTreeInputSnapshot = (snapshot: GraphSnapshot, options: TreeInputOptions): TreeInputSnapshot => {
  const classifier = options.classifier ?? genericPolicyClassifier;
  const eventById = new Map<string, L1Event>();
  for (const item of snapshot.events ?? []) { eventById.set(item.revision_id, item.event); eventById.set(item.event.event_revision_id, item.event); }
  const evidenceById = new Map((snapshot.evidence ?? []).map(({ evidence }) => [evidence.evidence_id, evidence]));
  // Do not fabricate an "unknown" source: only a complete Evidence -> Event -> Capture
  // lineage earns a span in the retrieval projection.
  const spans = (snapshot.evidence ?? []).flatMap(({ evidence }) => {
    const event = eventById.get(evidence.event_revision_id);
    return event ? [{ evidence_id: evidence.evidence_id, event_revision_id: evidence.event_revision_id,
      capture_session_id: event.capture_session_id, excerpt: evidence.excerpt, range: evidence.range, policy_labels: evidence.policy_labels }] : [];
  }).sort((left, right) => left.evidence_id.localeCompare(right.evidence_id));
  const spanById = new Map(spans.map((span) => [span.evidence_id, span]));
  const canonicalIds = canonicalEntityIds(snapshot);
  const selection = selectLiveCommittedClaims(snapshot, options.liveness_hook);
  const diagnostics: ProjectionDiagnostic[] = [...selection.diagnostics];
  const claims = selection.claims.map((item) => {
    for (const ref of item.claim.evidence_refs) {
      const evidence = evidenceById.get(ref);
      if (!evidence) diagnostics.push({ kind: "missing_evidence", claim_revision_id: item.revision_id, evidence_ref: ref, message: `claim ${item.revision_id} references missing evidence ${ref}` });
      else if (!eventById.has(evidence.event_revision_id)) diagnostics.push({ kind: "missing_event", claim_revision_id: item.revision_id, evidence_ref: ref, message: `evidence ${ref} references missing event ${evidence.event_revision_id}` });
    }
    const evidence_spans = item.claim.evidence_refs.map((ref) => spanById.get(ref)).filter((span): span is EvidenceSpan => span !== undefined);
    const policy_class = classifier.classify(item.claim, item.claim.evidence_refs.map((ref) => evidenceById.get(ref)).filter((evidence): evidence is Evidence => evidence !== undefined));
    // valid_time remains a caller-supplied projection side-map; it is not claim content.
    const valid_time = options.valid_time_by_claim_revision?.[item.revision_id] ?? null;
    return {
      claim_revision_id: item.revision_id, canonical_claim_id: item.claim.lifecycle === "canonical" ? item.claim.canonical_claim_id : null,
      claim_lineage_id: item.claim.claim_lineage_id, predicate: item.claim.predicate,
      arguments: item.claim.arguments.map((argument) => argument.value.kind === "entity_ref" ? { ...argument, value: { ...argument.value, ref: canonicalIds.get(argument.value.ref) ?? argument.value.ref } } : argument),
      observed_at: item.claim.temporal_scope.observed_at, valid_time, temporal_precision: item.claim.temporal_scope.precision,
      time_anchor: valid_time ? { kind: "valid_time" as const, value: valid_time } : { kind: "imprecise_time" as const, observed_at: item.claim.temporal_scope.observed_at, marker: "observed_at_fallback_imprecise" as const },
      evidence_refs: item.claim.evidence_refs, evidence_spans, scope: item.claim.scope, source_language: item.claim.source_language,
      policy_labels: item.claim.policy_labels, policy_class, placement_status: item.placement_status,
    } satisfies LiveClaimView;
  });
  const generationSeed = { graph: options.graph_generation ?? snapshot.graph_generation ?? "snapshot", classifier: classifier.version, liveness_hook: options.liveness_hook?.version ?? "dispute-purge-stub-v1", timezone: options.account_timezone };
  return { owner_account_id: snapshot.owner_account_id, graph_generation: sha256CanonicalRedacted(generationSeed), account_timezone: options.account_timezone,
    claims, identity_constraints: snapshot.identity_constraints?.map((item) => item.constraint) ?? [], evidence_index: spans,
    policy_classes: Object.fromEntries(claims.map((claim) => [claim.claim_revision_id, claim.policy_class])),
    liveness_hook_version: generationSeed.liveness_hook, classifier_version: classifier.version, diagnostics };
};

export type RetrievalRequest =
  | { owner_account_id: string; kind: "entity"; entity_id: string }
  | { owner_account_id: string; kind: "as_of"; date: string; include_provisional?: true }
  | { owner_account_id: string; kind: "source"; capture_session_id: string; include_provisional: true };

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
  const accountedWithheld = snapshot.claims.filter((item) => item.placement_status !== "consumed" && item.placement_status !== "canonical" && (request.kind !== "as_of" || item.claim.temporal_scope.observed_at <= request.date));
  const withheldByStatus: Record<Exclude<RetrievableStatus, "canonical">, number> = {
    withheld_unresolved_subject: accountedWithheld.filter((item) => item.placement_status === "withheld_unresolved_subject").length,
    withheld_abstained: accountedWithheld.filter((item) => item.placement_status === "withheld_abstained").length,
  };
  const visible = snapshot.claims.filter((item) => {
    if (item.placement_status === "consumed") return false;
    const observedAt = item.claim.temporal_scope.observed_at;
    const temporalMatch = request.kind === "as_of" ? observedAt <= request.date : true;
    if (!temporalMatch) return false;
    const sourceMatch = request.kind !== "source" || (snapshot.evidence ?? []).some(({ evidence }) => item.claim.evidence_refs.includes(evidence.evidence_id) && (snapshot.events ?? []).some(({ event }) => event.event_revision_id === evidence.event_revision_id && event.capture_session_id === request.capture_session_id));
    if (item.placement_status !== "canonical") {
      // Traversal/ops may account for withholding, but an entity query must never reader-surface it.
      if (request.kind === "entity") return false;
      if (request.kind === "source") return sourceMatch;
      return request.include_provisional === true;
    }
    return request.kind === "as_of" || (request.kind === "source" ? sourceMatch : (adjacencyByClaim.get(item.revision_id) ?? []).some((edge) => edge.entity_id === request.entity_id));
  }).map((item) => {
    const edges = adjacencyByClaim.get(item.revision_id) ?? [];
    const entities = edges.map((edge) => entitiesById.get(edge.entity_id)).filter((entity): entity is Entity => entity !== undefined);
    return {
      revision_id: item.revision_id, claim: item.claim, entities, scope: item.claim.scope,
      evidence_citations: item.claim.evidence_refs, dates: item.claim.temporal_scope,
      status: item.placement_status, match: item.placement_status === "canonical" ? "matched" : "withheld_unplaced",
    };
  });
  const allLive = snapshot.claims.filter((item) => item.placement_status !== "consumed");
  const withheld_items = withheldByStatus.withheld_unresolved_subject + withheldByStatus.withheld_abstained;
  return {
    claims: visible,
    omission_accounting: {
      total_committed_claims: allLive.length,
      returned_canonical: visible.filter((item) => item.status === "canonical").length,
      withheld_items, withheld_by_status: withheldByStatus, omitted_items: allLive.length - visible.length,
    },
  };
};

export interface RetrievalPort { retrieve(request: RetrievalRequest): Promise<RetrievalResult>; }
export interface ProvisionalInclusionPolicy { include_provisional: true; }
