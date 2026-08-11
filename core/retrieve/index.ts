// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-007)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMCORE-012)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-006)
import { compareStrings } from "../order";
import type { ClaimPlacementStatus, GeneratedAdjacency, PlacementArtifact } from "../ledger";
import type { CanonicalClaim, ClaimArgument, Entity, Evidence, IdentityAuthorization, IdentityConstraint, IdentityEndpoint, L1Event, Mention, PersistedValidTime, Predicate, PredicateAssertion, ProvisionalClaim } from "../schema";
import type { ImmutableIdentitySupport } from "../resolve/identity-authority";
import { sha256CanonicalRedacted } from "../ledger";
import { grantAllows, type RequestContext } from "./grant";
import { restrictivePolicyJoin } from "./policy";
import { sha256CanonicalContent } from "./content-digest";

export * from "./temporal";
export * from "./grant";
export * from "./adjacency";
export * from "./walk";
export * from "./trajectory";
export * from "./projection-boundary";
export * from "./authorization-boundary";

export interface CommittedClaim {
  revision_id: string;
  claim: CanonicalClaim | ProvisionalClaim;
  placement_status: ClaimPlacementStatus;
  /** Durable commit order supplied by persistence; never infer recency from an ID. */
  commit_sequence?: number;
}
export interface CommittedEntity { revision_id: string; entity: Entity; }
export interface CommittedPredicate { revision_id: string; predicate: Predicate; }
export interface CommittedPredicateAssertion { revision_id: string; assertion: PredicateAssertion; }
export interface CommittedIdentity { revision_id: string; constraint: IdentityConstraint; }
export interface CommittedMention { revision_id: string; mention: Mention; }
export interface CommittedIdentityAuthorization { revision_id: string; authorization: IdentityAuthorization; }
export interface CommittedEvent { revision_id: string; event: L1Event; }
export interface CommittedEvidence {
  revision_id: string;
  evidence: Evidence;
  /** Durable commit order supplied by persistence; never infer current evidence from an ID. */
  commit_sequence?: number;
}
export interface GraphSnapshot {
  owner_account_id: string;
  /** Commit-frontier sequence when supplied by persistence; fixtures may omit it. */
  graph_generation?: string | number;
  claims: readonly CommittedClaim[];
  entities: readonly CommittedEntity[];
  predicates?: readonly CommittedPredicate[];
  predicate_assertions?: readonly CommittedPredicateAssertion[];
  identity_constraints?: readonly CommittedIdentity[];
  mentions?: readonly CommittedMention[];
  identity_authorizations?: readonly CommittedIdentityAuthorization[];
  identity_support?: readonly ImmutableIdentitySupport[];
  events?: readonly CommittedEvent[];
  evidence?: readonly CommittedEvidence[];
  /** Immutable D35 fences. A revision named here can never become reader-visible. */
  liveness_causes?: Pick<D35LivenessCauses, "purged_claim_revision_ids" | "forgotten_claim_revision_ids">;
  adjacency: readonly GeneratedAdjacency[];
  /** Retrieval coordinates only; excluded from all durable entity graph walks. */
  source_local_roles?: readonly { claim_revision_id: string; source_local_ref: string; role_slot_id: string }[];
  /** Operational provenance; it deliberately does not alter claim semantics. */
  placement_artifacts?: readonly PlacementArtifact[];
}

/** Authoritative D35 inputs. `lineage_members` is the caller's already-eligible view. */
export interface D35LivenessCauses {
  evidence: readonly CommittedEvidence[];
  purged_claim_revision_ids: readonly string[];
  forgotten_claim_revision_ids: readonly string[];
  lineage_members: readonly CommittedClaim[];
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
    const values = (prefix: string): string[] => [...labels].filter((item) => item.startsWith(prefix)).map((item) => item.slice(prefix.length));
    // This is the same order-independent lattice used by rendering. Multiple
    // contributors can only retain or strengthen a policy dimension.
    return restrictivePolicyJoin(values("subject:").map((subject_class) => ({ subject_class, sensitivity: "generic", capture_class: "generic" })).concat(
      values("sensitivity:").map((sensitivity) => ({ subject_class: "generic", sensitivity, capture_class: "generic" })),
      values("capture:").map((capture_class) => ({ subject_class: "generic", sensitivity: "generic", capture_class })),
    ));
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
  predicate_id: string | null;
  predicate: string;
  proposition_key_raw: string | null;
  proposition_key_resolved: string | null;
  predicate_alias_frontier: string | null;
  arguments: readonly ClaimArgument[];
  observed_at: string;
  /** Persisted canonical temporal truth. It is never reconstructed from observation time. */
  valid_time: PersistedValidTime | null;
  temporal_precision: string;
  time_anchor: { kind: "valid_time"; value: string } | { kind: "imprecise_time"; observed_at: string; marker: "persisted_imprecise_or_missing_valid_time" };
  evidence_refs: readonly string[];
  evidence_spans: readonly EvidenceSpan[];
  scope: CanonicalClaim["scope"];
  source_language: string;
  polarity?: "positive" | "negative";
  policy_labels: readonly string[];
  policy_class: PolicyClass;
  placement_status: RetrievableStatus;
}
export interface TreeInputSnapshot {
  owner_account_id: string;
  graph_generation: string;
  /** Exact reader/grant projection provenance; null only for unprojected owner/internal views. */
  reader_projection_digest: string | null;
  /** Set only by the application authorization boundary after its grant gate succeeds. */
  projection_authorization_digest: string | null;
  /** Hash of the exact projected claim/evidence content consumed by structure/render. */
  projected_content_digest: string;
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
  classifier?: PolicyClassifier;
  /** Optional reader view; makes tree eligibility use the same D46 boundary as `project`. */
  request_context?: RequestContext;
  graph_generation?: string | number;
}

const endpointKey = (endpoint: IdentityEndpoint): string =>
  endpoint.kind === "entity" ? `entity:${endpoint.entity_id}` : `source:${endpoint.source_identity_ref.namespace_instance_ref}:${endpoint.source_identity_ref.local_key}`;

/** A persisted constraint is usable on a read path only if its embedded, previously
 * validated authorization still exactly describes this operation.  Renderings,
 * candidates, and legacy rows cannot enter this predicate. */
const authorizedActiveEntitySame = (constraint: IdentityConstraint, owner: string, asOf: number): boolean => {
  if (constraint.owner_account_id !== owner || constraint.relation !== "same" || !constraint.endpoints) return false;
  if (constraint.effective_at > asOf || (constraint.reversed_at !== null && constraint.reversed_at <= asOf)) return false;
  const authorization = constraint.identity_authorization;
  if (!authorization || authorization.lifecycle !== "active" || authorization.owner_account_id !== owner || authorization.relation !== "same") return false;
  const constraintEndpoints = new Set(constraint.endpoints.map(endpointKey));
  const sameEndpoints = authorization.endpoints.every((endpoint) => constraintEndpoints.has(endpointKey(endpoint)));
  return sameEndpoints && authorization.endpoints.every((endpoint) => endpoint.kind === "entity") && constraint.endpoints.every((endpoint) => endpoint.kind === "entity");
};

/**
 * D47 read-side entity canonicalization.  Entity ids move only across active,
 * authorized typed `same` constraints at the durable frontier.  Handles are
 * deliberately not a key or survivor rule: an unproven duplicate is malformed
 * input, not permission to merge it.
 */
export const canonicalEntityIdsAt = (snapshot: GraphSnapshot, asOf: number | undefined = typeof snapshot.graph_generation === "number" ? snapshot.graph_generation : undefined): Map<string, string> => {
  const entities = snapshot.entities.map((item) => item.entity).filter((entity) => entity.owner_account_id === snapshot.owner_account_id);
  const parent = new Map(entities.map((entity) => [entity.entity_id, entity.entity_id]));
  const find = (id: string): string => {
    const root = parent.get(id);
    if (!root) return id;
    return root === id ? root : find(root);
  };
  const join = (left: string, right: string): void => {
    if (!parent.has(left) || !parent.has(right)) return;
    const leftRoot = find(left);
    const rightRoot = find(right);
    if (leftRoot !== rightRoot) parent.set(rightRoot, leftRoot);
  };
  // A fixture without a durable frontier has no honest "active" identity view.
  // Fail closed instead of smuggling in MAX_SAFE_INTEGER.
  if (asOf !== undefined) for (const { constraint } of snapshot.identity_constraints ?? []) {
    if (!authorizedActiveEntitySame(constraint, snapshot.owner_account_id, asOf)) continue;
    const [left, right] = constraint.endpoints!;
    join(left.entity_id, right.entity_id);
  }
  const members = new Map<string, string[]>();
  for (const entity of entities) members.set(find(entity.entity_id), [...(members.get(find(entity.entity_id)) ?? []), entity.entity_id]);
  const byHandle = new Map<string, string>();
  for (const entity of entities) {
    const root = find(entity.entity_id);
    const existing = byHandle.get(entity.handle);
    if (existing !== undefined && existing !== root) throw new Error(`duplicate entity handle without authorized identity merge: ${entity.handle}`);
    byHandle.set(entity.handle, root);
  }
  const result = new Map<string, string>();
  for (const ids of members.values()) {
    // Stable entity identity, never a display-string survivor, chooses the root.
    const canonical = [...ids].sort()[0]!;
    for (const id of ids) result.set(id, canonical);
  }
  return result;
};

const canonicalEntityIds = (snapshot: GraphSnapshot): Map<string, string> => canonicalEntityIdsAt(snapshot);

interface LiveClaimSelection { claims: readonly CommittedClaim[]; diagnostics: readonly ProjectionDiagnostic[]; }

const explicitlySupersedes = (newer: CommittedClaim, older: CommittedClaim): boolean => {
  const sourceIds = newer.claim.lifecycle === "canonical" ? newer.claim.source_provisional_revision_ids : [];
  const explicit = newer.claim.lifecycle === "canonical" ? newer.claim.supersedes_revision_ids ?? [] : [];
  return [...sourceIds, ...explicit].includes(older.revision_id);
};
const stableTieBreak = (item: CommittedClaim): string => sha256CanonicalRedacted({ revision_id: item.revision_id, claim: item.claim, placement_status: item.placement_status });
const selectLineageHead = (members: readonly CommittedClaim[]): CommittedClaim => {
  const rank = (item: CommittedClaim) => item.placement_status === "canonical" ? 2 : 1;
  if (members.length === 1) return members[0]!;
  const explicitHeads = members.filter((candidate) => !members.some((other) => other !== candidate && explicitlySupersedes(other, candidate)));
  if (explicitHeads.length === 1 && members.some((candidate) => explicitlySupersedes(explicitHeads[0]!, candidate))) return explicitHeads[0]!;
  if (members.some((member) => member.commit_sequence === undefined)) return [...members].sort((left, right) => compareStrings(stableTieBreak(left), stableTieBreak(right)))[0]!;
  return [...members].sort((left, right) => {
    const sequence = right.commit_sequence! - left.commit_sequence!;
    if (sequence) return sequence;
    const placement = rank(right) - rank(left);
    return placement || compareStrings(stableTieBreak(left), stableTieBreak(right));
  })[0]!;
};

/**
 * Select one evidence revision per evidence id exclusively from durable commit
 * order.  A malformed multi-revision fixture with no complete sequence has no
 * trustworthy head, so it is deliberately omitted (and its citations fail
 * closed) rather than depending on array or revision-id order.
 */
const currentEvidenceById = (revisions: readonly CommittedEvidence[]): Map<string, Evidence> => {
  const grouped = new Map<string, CommittedEvidence[]>();
  for (const revision of revisions) {
    const bucket = grouped.get(revision.evidence.evidence_id);
    if (bucket) bucket.push(revision);
    else grouped.set(revision.evidence.evidence_id, [revision]);
  }
  const current = new Map<string, Evidence>();
  for (const [evidenceId, members] of grouped) {
    if (members.length === 1) {
      current.set(evidenceId, members[0]!.evidence);
      continue;
    }
    if (members.some((member) => member.commit_sequence === undefined)) continue;
    const greatest = Math.max(...members.map((member) => member.commit_sequence!));
    const heads = members.filter((member) => member.commit_sequence === greatest);
    // Distinct revisions of one evidence id must not share a commit sequence.
    // Treat a corrupt tie as not-active instead of letting an arbitrary order
    // reanimate a retracted citation.
    if (heads.length === 1) current.set(evidenceId, heads[0]!.evidence);
  }
  return current;
};

/** Private, snapshot-derived indexes shared only within one selection attempt. */
interface LivenessSelectionIndex {
  evidence_by_id: ReadonlyMap<string, Evidence>;
  purged_claim_revision_ids: ReadonlySet<string>;
  forgotten_claim_revision_ids: ReadonlySet<string>;
}

const buildLivenessSelectionIndex = (causes: Pick<D35LivenessCauses, "evidence" | "purged_claim_revision_ids" | "forgotten_claim_revision_ids">): LivenessSelectionIndex => ({
  evidence_by_id: currentEvidenceById(causes.evidence),
  purged_claim_revision_ids: new Set(causes.purged_claim_revision_ids),
  forgotten_claim_revision_ids: new Set(causes.forgotten_claim_revision_ids),
});

const isLiveWithIndex = (claim: CommittedClaim, lineageMembers: readonly CommittedClaim[], index: LivenessSelectionIndex): boolean => {
  if (index.purged_claim_revision_ids.has(claim.revision_id) || index.forgotten_claim_revision_ids.has(claim.revision_id)) return false;
  if (claim.claim.lifecycle === "canonical" && claim.claim.evidence_refs.length > 0) {
    const citedEvidence = claim.claim.evidence_refs.map((ref) => index.evidence_by_id.get(ref)).filter((evidence): evidence is Evidence => evidence !== undefined);
    // A canonical claim with citations needs at least one currently active one:
    // a lost reference and a tombstoned/security-hidden last citation are both D35.
    if (!citedEvidence.some((evidence) => evidence.state === "active")) return false;
  }
  const lineage = lineageMembers.filter((member) => member.claim.claim_lineage_id === claim.claim.claim_lineage_id);
  return !lineage.length || selectLineageHead(lineage).revision_id === claim.revision_id;
};

/**
 * D35's single, pure liveness authority. Evidence loss, an immutable purge/forget
 * fence, and a non-head lineage member are all non-live. Placement `consumed` is
 * deliberately absent: it is provisional audit bookkeeping, not retraction.
 */
export const isLive = (claim: CommittedClaim, causes: D35LivenessCauses): boolean =>
  isLiveWithIndex(claim, causes.lineage_members, buildLivenessSelectionIndex(causes));

/** D35 selection is intentionally evaluated after the reader grant projection. */
const selectLiveCommittedClaims = (snapshot: GraphSnapshot, ctx?: RequestContext): LiveClaimSelection => {
  const index = buildLivenessSelectionIndex({
    evidence: snapshot.evidence ?? [],
    purged_claim_revision_ids: snapshot.liveness_causes?.purged_claim_revision_ids ?? [],
    forgotten_claim_revision_ids: snapshot.liveness_causes?.forgotten_claim_revision_ids ?? [],
  });
  const eligible = snapshot.claims.filter((item) => item.placement_status !== "consumed").filter((item) => {
    if (!ctx) return true;
    const evidence = item.claim.evidence_refs.map((ref) => index.evidence_by_id.get(ref)).filter((entry): entry is Evidence => entry !== undefined);
    return grantAllows(ctx, item.claim, genericPolicyClassifier.classify(item.claim, evidence));
  });
  // First remove global D35 exclusions. Only then may the remaining members contend
  // for a lineage head; a tombstoned/purged revision cannot suppress an older one.
  const materiallyLive = eligible.filter((item) => isLiveWithIndex(item, [item], index));
  const byLineage = new Map<string, CommittedClaim[]>();
  for (const item of materiallyLive) byLineage.set(item.claim.claim_lineage_id, [...(byLineage.get(item.claim.claim_lineage_id) ?? []), item]);
  const diagnostics: ProjectionDiagnostic[] = [];
  const winners = [...byLineage.entries()].flatMap(([lineage, members]) => {
    if (members.some((member) => member.commit_sequence === undefined)) {
      diagnostics.push({ kind: "missing_commit_sequence", claim_lineage_id: lineage, claim_revision_ids: members.map((member) => member.revision_id).sort(), message: `lineage ${lineage} has multiple revisions without a complete commit sequence; selected by stable content hash` });
    }
    return members.filter((item) => isLiveWithIndex(item, members, index));
  });
  return { claims: winners.sort((left, right) => compareStrings(left.revision_id, right.revision_id)), diagnostics };
};

/** Returns deterministic live members; projection callers also receive selection diagnostics. */
export const liveCommittedClaims = (snapshot: GraphSnapshot, ctx?: RequestContext): readonly CommittedClaim[] =>
  selectLiveCommittedClaims(snapshot, ctx).claims;

/** The only graph shape eligible for a reader path or a future walk. */
export interface SafeSubgraph {
  owner_account_id: string;
  reader_account_id: string;
  claims: readonly CommittedClaim[];
  /** Existing generated adjacency, restricted to visible live claim revisions. */
  adjacency: readonly GeneratedAdjacency[];
  /** Complete, visible-only provenance chains used by the G5 read projection. */
  evidence_lineage: readonly SafeEvidenceLineage[];
}
export interface SafeEvidenceLineage {
  claim_revision_id: string;
  evidence_id: string;
  event_revision_id: string;
  capture_session_id: string;
  /** Event time is a persisted input coordinate used for temporal-proximity watermarks. */
  event_time?: string;
  range?: { start: number; end: number };
  excerpt?: string | null;
}

/**
 * D46 deterministic authorization boundary. Grant eligibility comes first, so a
 * hidden newer revision cannot suppress a visible lineage member for that reader.
 */
export const project = (snapshot: GraphSnapshot, ctx: RequestContext): SafeSubgraph => {
  const claims = liveCommittedClaims(snapshot, ctx);
  const visible = new Set(claims.map((item) => item.revision_id));
  const canonicalIds = canonicalEntityIds(snapshot);
  const currentEvidence = currentEvidenceById(snapshot.evidence ?? []);
  const eventById = new Map<string, L1Event>();
  for (const item of snapshot.events ?? []) { eventById.set(item.revision_id, item.event); eventById.set(item.event.event_revision_id, item.event); }
  const evidence_lineage = claims.flatMap((claim) => claim.claim.evidence_refs.flatMap((evidence_id) => {
    const evidence = currentEvidence.get(evidence_id);
    const event = evidence ? eventById.get(evidence.event_revision_id) : undefined;
    return evidence && event ? [{ claim_revision_id: claim.revision_id, evidence_id, event_revision_id: evidence.event_revision_id, capture_session_id: event.capture_session_id, event_time: event.event_time, range: evidence.range, excerpt: evidence.excerpt }] : [];
  })).sort((left, right) => compareStrings(`${left.claim_revision_id}\u0000${left.evidence_id}\u0000${left.event_revision_id}`, `${right.claim_revision_id}\u0000${right.evidence_id}\u0000${right.event_revision_id}`));
  return {
    owner_account_id: snapshot.owner_account_id,
    reader_account_id: ctx.reader_account_id,
    claims,
    adjacency: snapshot.adjacency.filter((edge) => visible.has(edge.claim_revision_id)).map((edge) => ({ ...edge, entity_id: canonicalIds.get(edge.entity_id) ?? edge.entity_id })).sort((left, right) => compareStrings(`${left.claim_revision_id}\u0000${left.entity_id}\u0000${left.role_slot_id}`, `${right.claim_revision_id}\u0000${right.entity_id}\u0000${right.role_slot_id}`)),
    evidence_lineage,
  };
};

/** Pure committed-graph projection. It intentionally has no tree or model dependency. */
export const projectTreeInputSnapshot = (snapshot: GraphSnapshot, options: TreeInputOptions): TreeInputSnapshot => {
  const classifier = options.classifier ?? genericPolicyClassifier;
  const eventById = new Map<string, L1Event>();
  for (const item of snapshot.events ?? []) { eventById.set(item.revision_id, item.event); eventById.set(item.event.event_revision_id, item.event); }
  const currentEvidence = currentEvidenceById(snapshot.evidence ?? []);
  // Do not fabricate an "unknown" source: only a complete Evidence -> Event -> Capture
  // lineage earns a span in the retrieval projection.
  const spans = [...currentEvidence.values()].flatMap((evidence) => {
    const event = eventById.get(evidence.event_revision_id);
    return event ? [{ evidence_id: evidence.evidence_id, event_revision_id: evidence.event_revision_id,
      capture_session_id: event.capture_session_id, excerpt: evidence.excerpt, range: evidence.range, policy_labels: evidence.policy_labels }] : [];
  }).sort((left, right) => compareStrings(left.evidence_id, right.evidence_id));
  const spanById = new Map(spans.map((span) => [span.evidence_id, span]));
  const canonicalIds = canonicalEntityIds(snapshot);
  const selection = selectLiveCommittedClaims(snapshot, options.request_context);
  const diagnostics: ProjectionDiagnostic[] = [...selection.diagnostics];
  const claims = selection.claims.map((item) => {
    for (const ref of item.claim.evidence_refs) {
      const evidence = currentEvidence.get(ref);
      if (!evidence) diagnostics.push({ kind: "missing_evidence", claim_revision_id: item.revision_id, evidence_ref: ref, message: `claim ${item.revision_id} references missing evidence ${ref}` });
      else if (!eventById.has(evidence.event_revision_id)) diagnostics.push({ kind: "missing_event", claim_revision_id: item.revision_id, evidence_ref: ref, message: `evidence ${ref} references missing event ${evidence.event_revision_id}` });
    }
    const evidence_spans = item.claim.evidence_refs.map((ref) => spanById.get(ref)).filter((span): span is EvidenceSpan => span !== undefined);
    const policy_class = classifier.classify(item.claim, item.claim.evidence_refs.map((ref) => currentEvidence.get(ref)).filter((evidence): evidence is Evidence => evidence !== undefined));
    // Only canonical claims are required to carry persisted temporal truth. A
    // malformed/legacy or provisional item is honestly imprecise, never filed
    // under its capture/observation date.
    const valid_time = item.claim.lifecycle === "canonical" ? item.claim.temporal_scope.valid_time ?? null : null;
    const resolved = valid_time?.resolved_interval;
    return {
      claim_revision_id: item.revision_id, canonical_claim_id: item.claim.lifecycle === "canonical" ? item.claim.canonical_claim_id : null,
      claim_lineage_id: item.claim.claim_lineage_id, predicate_id: item.claim.predicate_id ?? null, predicate: item.claim.predicate,
      proposition_key_raw: item.claim.proposition_key_raw ?? null, proposition_key_resolved: item.claim.proposition_key_resolved ?? null, predicate_alias_frontier: item.claim.predicate_alias_frontier ?? null,
      arguments: item.claim.arguments.map((argument) => argument.value.kind === "entity_ref" ? { ...argument, value: { ...argument.value, ref: canonicalIds.get(argument.value.ref) ?? argument.value.ref } } : argument),
      observed_at: item.claim.temporal_scope.observed_at, valid_time, temporal_precision: item.claim.temporal_scope.precision,
      time_anchor: resolved && resolved.kind !== "imprecise" ? { kind: "valid_time" as const, value: resolved.start } : { kind: "imprecise_time" as const, observed_at: item.claim.temporal_scope.observed_at, marker: "persisted_imprecise_or_missing_valid_time" as const },
      evidence_refs: item.claim.evidence_refs, evidence_spans, scope: item.claim.scope, source_language: item.claim.source_language,
      ...(item.claim.polarity === undefined ? {} : { polarity: item.claim.polarity }),
      policy_labels: item.claim.policy_labels, policy_class, placement_status: item.placement_status,
    } satisfies LiveClaimView;
  });
  const readerProjectionSeed = options.request_context ? {
    owner_account_id: snapshot.owner_account_id,
    reader_account_id: options.request_context.reader_account_id,
    grant_id: options.request_context.grant.grant_id,
    policy_classes: options.request_context.grant.policy_classes.map((policy) => ({ ...policy }))
      .sort((left, right) => compareStrings(`${left.subject_class}\u0000${left.sensitivity}\u0000${left.capture_class}`, `${right.subject_class}\u0000${right.sensitivity}\u0000${right.capture_class}`)),
  } : null;
  const reader_projection_digest = readerProjectionSeed === null ? null : sha256CanonicalRedacted(readerProjectionSeed);
  const identity_constraints = snapshot.identity_constraints?.map((item) => {
    const { endpoints, evidence_refs, identity_authorization, ...required } = item.constraint;
    return {
      ...required,
      ...(endpoints === undefined ? {} : { endpoints }),
      ...(evidence_refs === undefined ? {} : { evidence_refs }),
      ...(identity_authorization === undefined ? {} : { identity_authorization }),
    } satisfies IdentityConstraint;
  }) ?? [];
  const policy_classes = Object.fromEntries(claims.map((claim) => [claim.claim_revision_id, claim.policy_class]));
  const projected_content_digest = sha256CanonicalContent({ owner_account_id: snapshot.owner_account_id, claims, identity_constraints, evidence_index: spans, policy_classes, diagnostics });
  const generationSeed = { graph: options.graph_generation ?? snapshot.graph_generation ?? "snapshot", projected_content_digest, classifier: classifier.version, liveness_hook: "d35-liveness-v1", timezone: options.account_timezone, reader_projection_digest };
  return { owner_account_id: snapshot.owner_account_id, graph_generation: sha256CanonicalRedacted(generationSeed), reader_projection_digest, projection_authorization_digest: null, projected_content_digest, account_timezone: options.account_timezone,
    claims, identity_constraints, evidence_index: spans, policy_classes,
    liveness_hook_version: generationSeed.liveness_hook, classifier_version: classifier.version, diagnostics };
};

export type RetrievalRequest =
  | { owner_account_id: string; kind: "entity"; entity_id: string; reader_context?: RequestContext }
  | { owner_account_id: string; kind: "source_local"; source_local_ref: string; reader_context?: RequestContext }
  | { owner_account_id: string; kind: "as_of"; date: string; include_provisional?: true; reader_context?: RequestContext }
  | { owner_account_id: string; kind: "source"; capture_session_id: string; include_provisional: true; reader_context?: RequestContext };

type RetrievableStatus = Exclude<ClaimPlacementStatus, "consumed">;

export interface RetrievedClaim {
  revision_id: string;
  claim: CanonicalClaim | ProvisionalClaim;
  entities: readonly Entity[];
  scope: CanonicalClaim["scope"];
  evidence_citations: readonly string[];
  dates: CanonicalClaim["temporal_scope"];
  status: RetrievableStatus;
  /** A provisional claim has not been falsely filed under any durable entity. */
  match: "matched" | "provisional_unplaced";
}
export type ReaderVisibleAbsence =
  | { kind: "query_gap"; message: "no cited memory matched" }
  | { kind: "policy_omission"; grant_class: string; message: "some matching memory is omitted by your grant class" };
/** Wire-safe: no counts or categories can expose a retracted or policy-hidden node. */
export interface RetrievalResult { claims: readonly RetrievedClaim[]; absence: ReaderVisibleAbsence | null; }
/** Ops/eval-only bookkeeping. Do not return this from a reader-facing port. */
export interface InternalOmissionAccounting {
  total_committed_claims: number;
  returned_canonical: number;
  provisional_items: number;
  provisional_by_status: Readonly<Record<Exclude<RetrievableStatus, "canonical">, number>>;
  /** Internal-only; it may change when a non-reader-visible item is inserted or removed. */
  omitted_items: number;
}
export interface InternalRetrievalResult { reader_visible: RetrievalResult; omission_accounting: InternalOmissionAccounting; }
/** Reader-safe rendering of an already-authorized subgraph; no internal snapshot metadata leaks. */
export interface ReaderVisibleSubgraph {
  claims: readonly CommittedClaim[];
  adjacency: readonly GeneratedAdjacency[];
  absence: ReaderVisibleAbsence | null;
}
export const readerVisibleSubgraph = (subgraph: SafeSubgraph, absence: ReaderVisibleAbsence | null = null): ReaderVisibleSubgraph => ({
  claims: subgraph.claims,
  adjacency: subgraph.adjacency,
  absence: subgraph.claims.length ? null : absence ?? { kind: "query_gap", message: "no cited memory matched" },
});

/** Pure B5 query plus internal-only accounting for ops/eval. */
export const retrieveCommittedGraphInternal = (snapshot: GraphSnapshot, request: RetrievalRequest): InternalRetrievalResult => {
  if (request.owner_account_id !== snapshot.owner_account_id) throw new Error("retrieval owner does not match graph snapshot");
  const canonicalIds = canonicalEntityIds(snapshot);
  const requestedEntityId = request.kind === "entity" ? canonicalIds.get(request.entity_id) ?? request.entity_id : null;
  const entitiesById = new Map(snapshot.entities.map(({ entity }) => [entity.entity_id, entity]));
  const adjacencyByClaim = new Map<string, GeneratedAdjacency[]>();
  for (const edge of snapshot.adjacency) adjacencyByClaim.set(edge.claim_revision_id, [...(adjacencyByClaim.get(edge.claim_revision_id) ?? []), edge]);
  const live = liveCommittedClaims(snapshot, request.reader_context);
  const accountedProvisional = live.filter((item) => item.placement_status !== "canonical" && (request.kind !== "as_of" || item.claim.temporal_scope.observed_at <= request.date));
  const provisionalByStatus: Record<Exclude<RetrievableStatus, "canonical">, number> = {
    provisional_unresolved_subject: accountedProvisional.filter((item) => item.placement_status === "provisional_unresolved_subject").length,
    provisional_abstained: accountedProvisional.filter((item) => item.placement_status === "provisional_abstained").length,
  };
  const visible = live.filter((item) => {
    const observedAt = item.claim.temporal_scope.observed_at;
    const temporalMatch = request.kind === "as_of" ? observedAt <= request.date : true;
    if (!temporalMatch) return false;
    const sourceMatch = request.kind !== "source" || (snapshot.evidence ?? []).some(({ evidence }) => item.claim.evidence_refs.includes(evidence.evidence_id) && (snapshot.events ?? []).some(({ event }) => event.event_revision_id === evidence.event_revision_id && event.capture_session_id === request.capture_session_id));
    if (request.kind === "source_local") return (snapshot.source_local_roles ?? []).some((role) => role.claim_revision_id === item.revision_id && role.source_local_ref === request.source_local_ref);
    if (item.placement_status !== "canonical") {
      // An entity query cannot fabricate a durable entity placement for a provisional claim.
      if (request.kind === "entity") return false;
      if (request.kind === "source") return sourceMatch;
      return request.include_provisional === true;
    }
    return request.kind === "as_of" || (request.kind === "source" ? sourceMatch : (adjacencyByClaim.get(item.revision_id) ?? []).some((edge) => (canonicalIds.get(edge.entity_id) ?? edge.entity_id) === requestedEntityId));
  }).map((item) => {
    const edges = adjacencyByClaim.get(item.revision_id) ?? [];
    const entities = edges.map((edge) => entitiesById.get(canonicalIds.get(edge.entity_id) ?? edge.entity_id) ?? entitiesById.get(edge.entity_id)).filter((entity): entity is Entity => entity !== undefined);
    return {
      revision_id: item.revision_id, claim: item.claim, entities, scope: item.claim.scope,
      evidence_citations: item.claim.evidence_refs, dates: item.claim.temporal_scope,
      status: item.placement_status, match: item.placement_status === "canonical" ? "matched" : "provisional_unplaced",
    };
  });
  const provisional_items = provisionalByStatus.provisional_unresolved_subject + provisionalByStatus.provisional_abstained;
  return {
    reader_visible: { claims: visible, absence: visible.length ? null : { kind: "query_gap", message: "no cited memory matched" } },
    omission_accounting: {
      total_committed_claims: live.length,
      returned_canonical: visible.filter((item) => item.status === "canonical").length,
      provisional_items, provisional_by_status: provisionalByStatus, omitted_items: live.length - visible.length,
    },
  };
};
/** Reader-facing B5 result. Retraction/purge is indistinguishable from no matching claim. */
export const retrieveCommittedGraph = (snapshot: GraphSnapshot, request: RetrievalRequest): RetrievalResult =>
  retrieveCommittedGraphInternal(snapshot, request).reader_visible;

export interface RetrievalPort { retrieve(request: RetrievalRequest): Promise<RetrievalResult>; }
export interface ProvisionalInclusionPolicy { include_provisional: true; }
