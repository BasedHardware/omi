import { createHash } from "node:crypto";
import type { AllocatedPlacementPlan } from "../consolidate/plan";
import type { CanonicalClaim, CoreferenceSupport, Entity, Evidence, IdentityAuthorization, IdentityConstraint, L1Event, Mention, Predicate, PredicateAssertion, ProvisionalClaim, Scope } from "../schema";
import { IdentityAuthorizationSchema, MentionSchema, PredicateAssertionSchema, PredicateSchema } from "../schema";
import { validateCanonicalClaim, validateProvisionalClaim } from "../schema/claim-validation";
import { validateStrict } from "../schema/json";
import { authorizeIdentity, type IdentityAuthorityContext } from "../resolve/identity-authority";
import { identityConstraintConflicts } from "../resolve/entities";

/** Fields whose contents are intentionally excluded from sha256-canonical-redacted-v1. */
const redactedKeys = new Set(["api_key", "authorization", "raw", "raw_text", "secret", "token"]);

export type CanonicalJson = null | boolean | number | string | readonly CanonicalJson[] | { readonly [key: string]: CanonicalJson | undefined };

/**
 * sha256-canonical-redacted-v1 serializer: recursively sort object keys by JavaScript UTF-16
 * point, preserve array order, JSON-encode strings/numbers/booleans/null, reject
 * undefined/non-finite numbers, and replace values at the fixed redactedKeys with the
 * JSON string "[REDACTED]". Callers must supply already-redacted graph payloads; this
 * rule merely prevents a known raw credential/source field from entering the digest.
 */
export const canonicalizeRedacted = (value: CanonicalJson): string => {
  if (value === null || typeof value === "boolean" || typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new TypeError("canonical JSON rejects non-finite numbers");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalizeRedacted).join(",")}]`;
  const entries = Object.entries(value).sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0);
  return `{${entries.map(([key, item]) => {
    if (item === undefined) throw new TypeError("canonical JSON rejects undefined values");
    return `${JSON.stringify(key)}:${redactedKeys.has(key) ? JSON.stringify("[REDACTED]") : canonicalizeRedacted(item)}`;
  }).join(",")}}`;
};

export const sha256CanonicalRedacted = (value: CanonicalJson): string =>
  createHash("sha256").update(canonicalizeRedacted(value)).digest("hex");

export interface DerivationVersions {
  strategy_version: string;
  model_version: string;
  prompt_version: string;
  policy_version: string;
  code_version: string;
  schema_version: string;
  tokenizer_version: string;
  tool_version: string;
}

export type SuccessKind = "success" | "successful_empty";
export interface RevisionContent { revision_id: string; content: CanonicalJson; }
export interface HashedRevision extends RevisionContent { content_hash: string; }

export interface DerivationAttempt {
  attempt_id: string;
  owner_account_id: string;
  input_revision_ids: readonly string[];
  input_digest: string;
  input_version_digest: string;
  output_revision_ids: readonly string[];
  output_revisions: readonly HashedRevision[];
  output_digest: string;
  success_kind: SuccessKind;
  versions: DerivationVersions;
}

export interface DerivationCommit extends DerivationAttempt {
  commit_id: string;
  parent_commit: string | null;
  /** Assigned by the storage transaction from its current graph head. */
  sequence: number | null;
  idempotency_key: string;
}

export interface PreparedDerivation { attempt: DerivationAttempt; commit: DerivationCommit; }

/** Pure D8 record construction; it deliberately performs no storage, clock, or model effect. */
export const prepareDerivation = (request: {
  attempt_id: string;
  commit_id: string;
  owner_account_id: string;
  parent_commit: string | null;
  idempotency_key: string;
  input_revisions: readonly RevisionContent[];
  output_revisions: readonly RevisionContent[];
  versions: DerivationVersions;
  success_kind: SuccessKind;
}): PreparedDerivation => {
  const input_revisions = request.input_revisions.map((revision) => ({ ...revision, content_hash: sha256CanonicalRedacted(revision.content) }));
  const output_revisions = request.output_revisions.map((revision) => ({ ...revision, content_hash: sha256CanonicalRedacted(revision.content) }));
  const input_revision_ids = input_revisions.map((revision) => revision.revision_id);
  const input_digest = sha256CanonicalRedacted({ input_revision_ids, input_content_hashes: input_revisions.map((revision) => revision.content_hash) });
  const input_version_digest = sha256CanonicalRedacted({ input_revision_ids, input_content_hashes: input_revisions.map((revision) => revision.content_hash), versions: request.versions as unknown as CanonicalJson });
  const output_revision_ids = output_revisions.map((revision) => revision.revision_id);
  const output_digest = sha256CanonicalRedacted({ output_revision_ids, output_content_hashes: output_revisions.map((revision) => revision.content_hash) });
  const attempt: DerivationAttempt = { attempt_id: request.attempt_id, owner_account_id: request.owner_account_id, input_revision_ids, input_digest, input_version_digest, output_revision_ids, output_revisions, output_digest, success_kind: request.success_kind, versions: request.versions };
  return {
    attempt,
    commit: {
      ...attempt, commit_id: request.commit_id, parent_commit: request.parent_commit, sequence: null,
      idempotency_key: request.idempotency_key,
    },
  };
};

/** `consumed` preserves a provisional revision for audit without making it an active retrieval item. */
export type ClaimPlacementStatus = "canonical" | "consumed" | "provisional_unresolved_subject" | "provisional_abstained";
export interface ClaimRevision {
  kind: "claim";
  revision_id: string;
  claim: CanonicalClaim | ProvisionalClaim;
  placement_status: ClaimPlacementStatus;
}
export interface EntityRevision { kind: "entity"; revision_id: string; entity: Entity; }
export interface PredicateRevision { kind: "predicate"; revision_id: string; predicate: Predicate; }
export interface PredicateAssertionRevision { kind: "predicate_assertion"; revision_id: string; assertion: PredicateAssertion; }
export interface IdentityRevision { kind: "identity"; revision_id: string; constraint: IdentityConstraint; }
/** L1 and evidence are immutable graph inputs too; retrieval needs their provenance, not just IDs. */
export interface EventRevision { kind: "event"; revision_id: string; event: L1Event; }
export interface EvidenceRevision { kind: "evidence"; revision_id: string; evidence: Evidence; }
export interface MentionRevision { kind: "mention"; revision_id: string; mention: Mention; }
export interface IdentityAuthorizationRevision { kind: "identity_authorization"; revision_id: string; authorization: IdentityAuthorization; }
export interface CoreferenceSupportRevision { kind: "coreference_support"; revision_id: string; support: CoreferenceSupport; }
export type GraphRevision = ClaimRevision | EntityRevision | PredicateRevision | PredicateAssertionRevision | IdentityRevision | EventRevision | EvidenceRevision | MentionRevision | IdentityAuthorizationRevision | CoreferenceSupportRevision;
export interface GeneratedAdjacency { claim_revision_id: string; entity_id: string; role_slot_id: string; }
/** Retrieval-only role coordinate. It can never participate in entity adjacency. */
export interface SourceLocalClaimRole { claim_revision_id: string; source_local_ref: string; role_slot_id: string; }
/** Persisted D41 sampling strata. These are operational artifacts, not claim semantics. */
export type PlacementArtifactKind = "confirmation_queue" | "abstention_set" | "auto_placement_log";
export interface PlacementArtifact {
  artifact_id: string;
  kind: PlacementArtifactKind;
  provisional_revision_id: string;
  canonical_claim_revision_id: string | null;
  /** Model decision margin is operational provenance, never core claim semantics. */
  margin: "low" | "medium" | "high" | null;
  risk_markers: readonly ("new_entity" | "resolved_pronoun" | "low_margin")[];
  unit_boundary_decision: "accept_ltm" | "abstain";
  scope_locality: Scope["locality"] | null;
}
/** Candidate ranking is auditable operational provenance, never identity support. */
export interface CandidateDerivationArtifact {
  artifact_id: string;
  kind: "candidate_derivation";
  owner_account_id: string;
  source_ref: string;
  candidate_entity_id: string;
  strategy_ref: string;
  input_refs: readonly string[];
}
export type TransitionArtifact = PlacementArtifact | CandidateDerivationArtifact;

/** T9's typed persistence input: T7 allocation plus the already-validated immutable payloads. */
export interface AtomicGraphTransition {
  placement: AllocatedPlacementPlan;
  derivation: PreparedDerivation;
  revisions: readonly GraphRevision[];
  adjacency: readonly GeneratedAdjacency[];
  /**
   * Durable placement accounting belongs to the same atomic write as its
   * disposition.  A transition may have no placement artifacts, but it must
   * say so explicitly; STM→LTM transitions populate this from their boundary
   * decision before this contract reaches persistence.
   */
  artifacts: readonly TransitionArtifact[];
  /** Immutable records used to check authorization refs; the validator has no I/O. */
  identity_authority_context?: IdentityAuthorityContext;
  /** The extraction adapter supplies this derived value after diffing the
   * writing context. It is deliberately not part of caller authority input. */
  derived_identity_support?: readonly import("../resolve/identity-authority").ImmutableIdentitySupport[];
  /**
   * Immutable committed inputs read at the leased graph frontier.  They are
   * validation witnesses only: the SQLite writer never writes them again.
   * This lets a later consolidation authorization cite its already-committed
   * claim/evidence/event lineage without pretending those rows were created
   * by the new transition.
   */
  committed_revisions?: readonly GraphRevision[];
}

export class GraphTransitionValidationError extends Error {}

/** Pure guard for the D13 claim-to-generated-adjacency invariant before any I/O begins. */
export const validateAtomicGraphTransition = (transition: AtomicGraphTransition): void => {
  if (!Array.isArray(transition.artifacts)) throw new GraphTransitionValidationError("transition must provide placement artifacts");
  const revisionIds = new Set<string>();
  for (const revision of transition.revisions) {
    if (revisionIds.has(revision.revision_id)) throw new GraphTransitionValidationError(`duplicate revision id: ${revision.revision_id}`);
    revisionIds.add(revision.revision_id);
    if (revision.kind === "claim" && revision.claim.lifecycle === "canonical" && !validateCanonicalClaim(revision.claim)) throw new GraphTransitionValidationError(`invalid canonical claim: ${revision.revision_id}`);
    if (revision.kind === "claim" && revision.claim.lifecycle === "provisional" && !validateProvisionalClaim(revision.claim)) throw new GraphTransitionValidationError(`invalid provisional claim: ${revision.revision_id}`);
    if (revision.kind === "predicate" && !validateStrict(PredicateSchema, revision.predicate)) throw new GraphTransitionValidationError(`invalid predicate: ${revision.revision_id}`);
    if (revision.kind === "predicate_assertion" && !validateStrict(PredicateAssertionSchema, revision.assertion)) throw new GraphTransitionValidationError(`invalid predicate assertion: ${revision.revision_id}`);
    if (revision.kind === "mention" && !validateStrict(MentionSchema, revision.mention)) throw new GraphTransitionValidationError(`invalid persisted mention: ${revision.revision_id}`);
    if (revision.kind === "identity_authorization" && !validateStrict(IdentityAuthorizationSchema, revision.authorization)) throw new GraphTransitionValidationError(`invalid identity authorization: ${revision.revision_id}`);
  }
  const dispositionIds = new Set(transition.placement.results.map((result) => result.input_provisional_revision_id));
  for (const result of transition.placement.results) if (!revisionIds.has(result.input_provisional_revision_id)) throw new GraphTransitionValidationError(`missing provisional revision for disposition: ${result.input_provisional_revision_id}`);
  const adjacencyByClaim = new Map<string, GeneratedAdjacency[]>();
  for (const edge of transition.adjacency) {
    if (!revisionIds.has(edge.claim_revision_id)) throw new GraphTransitionValidationError(`adjacency references unknown claim: ${edge.claim_revision_id}`);
    const claim = transition.revisions.find((revision): revision is ClaimRevision => revision.kind === "claim" && revision.revision_id === edge.claim_revision_id);
    if (!claim || claim.placement_status !== "canonical" || claim.claim.lifecycle !== "canonical") throw new GraphTransitionValidationError(`adjacency requires a canonical claim: ${edge.claim_revision_id}`);
    adjacencyByClaim.set(edge.claim_revision_id, [...(adjacencyByClaim.get(edge.claim_revision_id) ?? []), edge]);
  }
  for (const revision of transition.revisions) {
    if (revision.kind !== "claim") continue;
    if (revision.claim.lifecycle === "provisional" && !dispositionIds.has(revision.revision_id)) throw new GraphTransitionValidationError(`unaccounted provisional claim: ${revision.revision_id}`);
    if (revision.placement_status === "canonical" && revision.claim.lifecycle !== "canonical") throw new GraphTransitionValidationError(`canonical status requires a canonical claim: ${revision.revision_id}`);
    if (revision.placement_status === "canonical" && revision.claim.arguments.some((argument) => argument.value.kind === "entity_ref") && !(adjacencyByClaim.get(revision.revision_id)?.length)) throw new GraphTransitionValidationError(`active claim lacks generated adjacency: ${revision.revision_id}`);
    if (revision.placement_status !== "canonical" && revision.claim.lifecycle !== "provisional") throw new GraphTransitionValidationError(`non-canonical claim must remain provisional: ${revision.revision_id}`);
  }
  const context = transition.identity_authority_context ?? { owner_confirmations: [], producer_assertions: [], standing_policies: [] };
  if (context.identity_support?.some((support) => support.support_origin !== undefined || "entity_link_support" in support || "provenance_bearing" in support)) throw new GraphTransitionValidationError("untrusted caller identity support origin");
  const derivedSupport = transition.derived_identity_support ?? [];
  if (derivedSupport.some((support) => support.support_origin !== "independent" && support.support_origin !== "suggested")) throw new GraphTransitionValidationError("invalid derived identity support origin");
  const authorityContext: IdentityAuthorityContext = { ...context, identity_support: [...(context.identity_support ?? []), ...derivedSupport] };
  const committed = transition.committed_revisions ?? [];
  const transitionAuthorizations = transition.revisions.filter((revision): revision is IdentityAuthorizationRevision => revision.kind === "identity_authorization");
  // A witnessed authorization is prior committed authority carried into this
  // transition's immutable input set. It is REVALIDATED here exactly like a
  // new one -- endpoints, lifecycle, and support lineage -- so accepting it is
  // replay, not trust. Without this, a claim whose slot was bound in an
  // earlier cycle could never be reprojected again: append-only reprojection
  // of multiply-bound claims requires the old binding's authority to travel.
  const witnessedAuthorizations = committed.filter((revision): revision is IdentityAuthorizationRevision => revision.kind === "identity_authorization");
  const authorizations = [...transitionAuthorizations, ...witnessedAuthorizations];
  const mentions = [...transition.revisions, ...committed].filter((revision): revision is MentionRevision => revision.kind === "mention");
  const coreferences = transition.revisions.filter((revision): revision is CoreferenceSupportRevision => revision.kind === "coreference_support").map((revision) => revision.support);
  // Consolidation authority is admissible only when every support reference
  // resolves through this immutable transition's claim → evidence → event
  // lineage.  A caller-provided context record is not evidence by itself.
  for (const authorization of authorizations) if (authorization.authorization.support.kind === "consolidation_adjudication") {
    for (const supportRef of authorization.authorization.support.support_refs) {
      const support = authorityContext.identity_support?.find((item) => item.support_ref === supportRef);
      const available = [...transition.revisions, ...committed];
      const claim = support && available.find((item): item is ClaimRevision => item.kind === "claim" && item.revision_id === support.claim_revision_id);
      const evidence = support && available.find((item): item is EvidenceRevision => item.kind === "evidence" && (item.revision_id === support.evidence_ref || item.evidence.evidence_id === support.evidence_ref));
      const event = evidence && available.find((item): item is EventRevision => item.kind === "event" && item.revision_id === evidence.evidence.event_revision_id);
      if (!support || !claim || !evidence || !event || evidence.evidence.source_independence_key !== support.source_independence_key) throw new GraphTransitionValidationError(`unresolvable identity support lineage: ${supportRef}`);
    }
  }
  const usedAuthorizations = new Set<string>();
  const markAuthorized = (owner: string, endpoints: readonly [IdentityAuthorization["endpoints"][0], IdentityAuthorization["endpoints"][1]], relation: "same" | "distinct", frontier: number): boolean => {
    const match = authorizations.find((revision) => authorizeIdentity(revision.authorization, { owner_account_id: owner, endpoints, relation, evaluated_frontier: frontier }, authorityContext).authorized);
    if (match) usedAuthorizations.add(match.revision_id);
    return !!match;
  };
  const plannedConstraints: IdentityConstraint[] = [];
  for (const revision of transition.revisions) {
    if (revision.kind !== "identity") continue;
    const constraint = revision.constraint;
    if (!constraint.endpoints || !constraint.identity_authorization) throw new GraphTransitionValidationError(`identity constraint lacks typed authorized endpoints: ${revision.revision_id}`);
    const inline = authorizeIdentity(constraint.identity_authorization, { owner_account_id: constraint.owner_account_id, endpoints: constraint.endpoints, relation: constraint.relation, evaluated_frontier: constraint.effective_at }, authorityContext);
    if (!inline.authorized) throw new GraphTransitionValidationError(`invalid identity constraint authorization: ${revision.revision_id}`);
    if (!markAuthorized(constraint.owner_account_id, constraint.endpoints, constraint.relation, constraint.effective_at)) throw new GraphTransitionValidationError(`identity constraint lacks persisted authorization: ${revision.revision_id}`);
    if (identityConstraintConflicts(plannedConstraints, constraint)) throw new GraphTransitionValidationError(`identity relation conflicts with active equivalence class: ${revision.revision_id}`);
    plannedConstraints.push(constraint);
  }
  for (const revision of transition.revisions) {
    if (revision.kind !== "claim" || revision.placement_status !== "canonical" || revision.claim.lifecycle !== "canonical") continue;
    for (const edge of adjacencyByClaim.get(revision.revision_id) ?? []) {
      if (!revision.claim.arguments.some((argument) => argument.slot_id === edge.role_slot_id && argument.value.kind === "entity_ref" && argument.value.ref === edge.entity_id)) {
        throw new GraphTransitionValidationError(`generated adjacency lacks durable role binding: ${revision.revision_id}:${edge.role_slot_id}`);
      }
    }
    for (const argument of revision.claim.arguments) {
      if (argument.value.kind !== "entity_ref") continue;
      const edge = adjacencyByClaim.get(revision.revision_id)?.find((item) => item.role_slot_id === argument.slot_id && item.entity_id === argument.value.ref);
      if (!edge) throw new GraphTransitionValidationError(`durable role binding lacks matching adjacency: ${revision.revision_id}:${argument.slot_id}`);
      const mention = mentions.find((item) => revision.claim.source_provisional_revision_ids.includes(item.mention.claim_revision_id) && item.mention.slot_id === argument.slot_id && item.mention.entity_id === argument.value.ref && item.mention.source_identity_ref !== null);
      if (!mention?.mention.source_identity_ref) throw new GraphTransitionValidationError(`durable role binding lacks typed mention lineage: ${revision.revision_id}:${argument.slot_id}`);
      const coreference = coreferences.find((item) => item.lifecycle === "active" && item.owner_account_id === revision.claim.owner_account_id && item.anaphor_mention_id === mention.mention.mention_id && item.lineage_refs.includes(`mention:${mention.mention.mention_id}`));
      const authorityMention = coreference ? mentions.find((item) => item.mention.mention_id === coreference.antecedent_mention_id && item.mention.entity_id === argument.value.ref && item.mention.source_identity_ref !== null) : mention;
      if (!authorityMention?.mention.source_identity_ref) throw new GraphTransitionValidationError(`coreference binding lacks antecedent identity lineage: ${revision.revision_id}:${argument.slot_id}`);
      const endpoints = [{ kind: "source_identity" as const, source_identity_ref: authorityMention.mention.source_identity_ref }, { kind: "entity" as const, entity_id: argument.value.ref }] as const;
      // Several authorizations may target one entity (a carried binding plus a
      // new member joining it); each is valid only at its own evaluated
      // frontier, so try each candidate's frontier rather than the first one.
      const frontiers = [...new Set(authorizations.filter((item) => item.authorization.owner_account_id === revision.claim.owner_account_id && item.authorization.relation === "same" && item.authorization.endpoints[1].kind === "entity" && item.authorization.endpoints[1].entity_id === argument.value.ref).map((item) => item.authorization.evaluated_frontier))];
      if (!frontiers.some((frontier) => markAuthorized(revision.claim.owner_account_id, endpoints, "same", frontier))) throw new GraphTransitionValidationError(`durable role binding lacks identity authorization: ${revision.revision_id}:${argument.slot_id}`);
    }
  }
  for (const authorization of transitionAuthorizations) if (!usedAuthorizations.has(authorization.revision_id)) throw new GraphTransitionValidationError(`identity authorization has no dependent binding: ${authorization.revision_id}`);
  const artifacts = transition.artifacts.filter((artifact): artifact is PlacementArtifact => artifact.kind !== "candidate_derivation");
  const artifactIds = new Set<string>();
  const artifactsByProvisional = new Map<string, PlacementArtifact[]>();
  const claimsById = new Map(transition.revisions.filter((revision): revision is ClaimRevision => revision.kind === "claim").map((revision) => [revision.revision_id, revision]));
  for (const artifact of artifacts) {
    if (artifactIds.has(artifact.artifact_id)) throw new GraphTransitionValidationError(`duplicate artifact id: ${artifact.artifact_id}`);
    artifactIds.add(artifact.artifact_id);
    artifactsByProvisional.set(artifact.provisional_revision_id, [...(artifactsByProvisional.get(artifact.provisional_revision_id) ?? []), artifact]);
    const provisional = claimsById.get(artifact.provisional_revision_id);
    if (!provisional || provisional.claim.lifecycle !== "provisional") throw new GraphTransitionValidationError(`artifact references unknown provisional claim: ${artifact.provisional_revision_id}`);
    if (artifact.margin !== null && !["low", "medium", "high"].includes(artifact.margin)) throw new GraphTransitionValidationError(`invalid placement margin: ${artifact.artifact_id}`);
    if (!Array.isArray(artifact.risk_markers) || artifact.risk_markers.some((marker) => !["new_entity", "resolved_pronoun", "low_margin"].includes(marker))) throw new GraphTransitionValidationError(`invalid placement risk marker: ${artifact.artifact_id}`);
    if (!["accept_ltm", "abstain"].includes(artifact.unit_boundary_decision)) throw new GraphTransitionValidationError(`invalid placement boundary decision: ${artifact.artifact_id}`);
    if (artifact.scope_locality !== null && artifact.scope_locality !== "durable" && artifact.scope_locality !== "source_local") throw new GraphTransitionValidationError(`invalid placement scope locality: ${artifact.artifact_id}`);
    if (artifact.kind === "auto_placement_log") {
      const canonical = artifact.canonical_claim_revision_id ? claimsById.get(artifact.canonical_claim_revision_id) : undefined;
      if (!canonical || canonical.claim.lifecycle !== "canonical" || canonical.placement_status !== "canonical") throw new GraphTransitionValidationError(`auto-placement artifact requires committed canonical claim: ${artifact.artifact_id}`);
    } else if (artifact.canonical_claim_revision_id !== null) throw new GraphTransitionValidationError(`non-auto artifact cannot name a canonical claim: ${artifact.artifact_id}`);
  }
  for (const [provisionalRevisionId, provisionalArtifacts] of artifactsByProvisional) {
    if (provisionalArtifacts.length !== 1) throw new GraphTransitionValidationError(`provisional must have exactly one placement artifact: ${provisionalRevisionId}`);
  }
  for (const provisionalRevisionId of dispositionIds) {
    if (artifactsByProvisional.get(provisionalRevisionId)?.length !== 1) {
      throw new GraphTransitionValidationError(`provisional-consuming transition requires placement artifacts covering provisional: ${provisionalRevisionId}`);
    }
  }
};

export interface LedgerPort {
  appendTransitionPlan(plan: AtomicGraphTransition): Promise<{ commit_id: string; sequence: number; idempotent: boolean }>;
  /** Historical commits have no weaker persistence route than live append. */
  replayTransitionPlan(plan: AtomicGraphTransition): Promise<{ commit_id: string; sequence: number; idempotent: boolean }>;
  /** Repair is an append/replay of an immutable transition, never raw-table mutation. */
  repairTransitionPlan(plan: AtomicGraphTransition): Promise<{ commit_id: string; sequence: number; idempotent: boolean }>;
  /** A stable idempotency-key lookup is required before a session calls models. */
  findCommitByIdempotencyKey(idempotencyKey: string): { commit_id: string; sequence: number } | null;
}
export interface LedgerSnapshot { owner_account_id: string; graph_generation: number; }
