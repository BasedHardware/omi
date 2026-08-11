import { buildFlywheelArtifacts } from "../../core/scope/flywheel";
import { prepareDerivation, sha256CanonicalRedacted, type AtomicGraphTransition, type DerivationVersions, type LedgerPort } from "../../core/ledger";
import { hasDistinctArgumentSlotIds, type CoreferenceSupport, type Entity, type Evidence, type IdentityAuthorization, type L1Event, type Mention, type PersistedValidTime, type Predicate, type ProvisionalClaim, type SourceIdentityRef } from "../../core/schema";
import { durableRoleSlotBindings, isForcedUnresolvedMention } from "../../core/resolve/mention-detection";
import { authorizeIdentity, type IdentityAuthorityContext } from "../../core/resolve/identity-authority";
import type { CandidateSnapshot } from "../../core/resolve/candidates";
import { invokeEntityStrategy } from "./entity-edge";
import { invokeClaimMentionStrategy } from "./mention-edge";
import type { ModelPort } from "./port";
import { invokeScopeStrategy } from "./scope-edge";
import { invokeUnitBoundaryStrategy } from "./unit-boundary-edge";

export interface SessionStmLtmRequest {
  ledger: LedgerPort;
  model: ModelPort;
  session_id: string;
  /** Exact formation work namespace, derived from complete strategy coordinates. */
  formation_work_id: string;
  owner_account_id: string;
  provisionals: readonly ProvisionalClaim[];
  entities: readonly Entity[];
  evidence: readonly Evidence[];
  /** L1 inputs are committed with their dependent evidence so later grounded
   * windows can retrieve a live provenance chain. */
  events?: readonly L1Event[];
  valid_times: Readonly<Record<string, PersistedValidTime>>;
  parent_commit: string | null;
  /** Graph head/frontier read by the caller before planning this transition. */
  graph_frontier: number;
  versions: DerivationVersions;
  /** I2 authority inputs are immutable records supplied by the caller/ledger, never model output. */
  identity_authorizations?: readonly IdentityAuthorization[];
  identity_authority_context?: IdentityAuthorityContext;
}

const sessionWorkCoordinate = (owner: string, session: string, work: string): string =>
  sha256CanonicalRedacted({ owner, session, work });
const sessionKey = (coordinate: string) => `cold-session:${coordinate}`;
const canonicalRevisionId = (coordinate: string, provisional: string) => `canonical:${coordinate}:${provisional}`;
const unscopedIdentity = (session: string, mention: Mention): SourceIdentityRef => ({
  namespace_instance_ref: `unscoped:${session}:${mention.evidence_id}:${mention.mention_id}`,
  local_key: mention.mention_id,
  producer: { producer_ref: null, contract_ref: null },
  asserted_identity: { domain: null, scope_ref: null },
});

const sourceIdentityForMention = (request: SessionStmLtmRequest, mention: Mention): SourceIdentityRef =>
  // Mention planning is the authority boundary: only the observed speaker slot
  // receives the evidence producer coordinate. Reloading the evidence-wide
  // identity here upgraded every named bystander or repaired speaker slot into
  // the diarized speaker and could make an unrelated owner authorization fit.
  mention.source_identity_ref ?? unscopedIdentity(request.session_id, mention);
const revisionContent = (revision: AtomicGraphTransition["revisions"][number]) => revision.kind === "claim" ? revision.claim : revision.kind === "event" ? revision.event : revision.kind === "evidence" ? revision.evidence : revision.kind === "mention" ? revision.mention : revision.kind === "identity_authorization" ? revision.authorization : revision.kind === "coreference_support" ? revision.support : revision.kind === "entity" ? revision.entity : revision.kind === "identity" ? revision.constraint : revision.kind === "predicate" ? revision.predicate : revision.assertion;

/**
 * The cold-run transition boundary: it makes all decisions first, constructs
 * canonical facts from those outputs, then writes the whole session once.
 */
export const commitSessionStmToLtmTransition = async (request: SessionStmLtmRequest): Promise<{ commit_id: string; sequence: number; idempotent: boolean }> => {
  if (!request.session_id || !request.formation_work_id || !request.owner_account_id) throw new Error("session transition requires stable session, formation work, and owner ids");
  const coordinate = sessionWorkCoordinate(request.owner_account_id, request.session_id, request.formation_work_id);
  const key = sessionKey(coordinate);
  const ids = new Set<string>();
  for (const claim of request.provisionals) {
    if (claim.owner_account_id !== request.owner_account_id || ids.has(claim.claim_revision_id)) throw new Error("session claims must be unique and owner-local");
    if (!hasDistinctArgumentSlotIds(claim.arguments)) throw new Error(`claim arguments must have distinct slot_ids: ${claim.claim_revision_id}`);
    ids.add(claim.claim_revision_id);
    if (!request.valid_times[claim.claim_revision_id]) throw new Error(`session canonical construction lacks valid_time: ${claim.claim_revision_id}`);
  }
  const decisionInputDigest = sha256CanonicalRedacted({
    parent_commit: request.parent_commit,
    graph_frontier: request.graph_frontier ?? 0,
    entities: request.entities,
    valid_times: request.valid_times,
    identity_authorizations: request.identity_authorizations ?? [],
    identity_authority_context: request.identity_authority_context ?? null,
  });
  const inputRevisions = [
    ...request.provisionals.map((claim) => ({ revision_id: claim.claim_revision_id, content: claim })),
    ...(request.events ?? []).map((event) => ({ revision_id: event.event_revision_id, content: event })),
    ...request.evidence.map((evidence) => ({ revision_id: `evidence-revision:${evidence.evidence_id}`, content: evidence })),
    { revision_id: `formation-decision-input:${coordinate}`, content: { decision_input_digest: decisionInputDigest } },
  ];
  const preflight = prepareDerivation({
    attempt_id: `attempt:session:${coordinate}`,
    commit_id: `commit:session:${coordinate}`,
    owner_account_id: request.owner_account_id,
    parent_commit: request.parent_commit,
    idempotency_key: key,
    input_revisions: inputRevisions,
    output_revisions: [],
    versions: request.versions,
    success_kind: "successful_empty",
  });
  const prior = request.ledger.findCommitByIdempotencyKey(key);
  // Resume before any model edge only when both inputs and every strategy
  // coordinate are identical. Reusing a work id with changed content is loud.
  if (prior) {
    if (prior.input_version_digest !== preflight.commit.input_version_digest) throw new Error(`formation work id reused with changed input or versions: ${request.formation_work_id}`);
    return { commit_id: prior.commit_id, sequence: prior.sequence, idempotent: true };
  }

  const mentioned = await invokeClaimMentionStrategy(request.model, request.owner_account_id, request.provisionals, request.evidence);
  const mentions: Mention[] = [];
  const sessionEntities: Entity[] = [...request.entities];
  const localBindings = new Map<string, { entity_id: string; mention_id: string; discourse_unit_ref: string }>();
  const coreferenceSupports: CoreferenceSupport[] = [];
  const usedAuthorizations = new Map<string, IdentityAuthorization>();
  const candidateArtifacts: Extract<AtomicGraphTransition["artifacts"][number], { kind: "candidate_derivation" }>[] = [];
  // Resolve antecedents before their dependents even if a model response is not
  // ordered that way; cycles remain source-local and may abstain.
  const pending = [...mentioned];
  while (pending.length) {
    const index = pending.findIndex((item) => item.antecedent_handle === null || localBindings.has(item.antecedent_handle));
    const source = pending.splice(index < 0 ? 0 : index, 1)[0]!;
    if (isForcedUnresolvedMention(source)) {
      mentions.push(source);
      continue;
    }
    const excerpt = request.evidence.find((item) => item.evidence_id === source.evidence_id)?.excerpt;
    const sourceIdentity = sourceIdentityForMention(request, source);
    const discourseUnit = request.evidence.find((item) => item.evidence_id === source.evidence_id)?.source_unit_ref;
    // A local handle names ONE mention, per `planLocalHandles`. This used to key
    // on the source identity, which is per-EVIDENCE: every slot in a segment
    // collapsed onto one handle (last writer winning) and no antecedent handle
    // emitted by extraction -- `local:<mention_id>` -- could ever match a key in
    // this map, so the coreference branch below was unreachable by construction.
    const handle = { handle: `local:${source.mention_id}`, mention_ref: source.mention_id, antecedent_handle: source.antecedent_handle, uncertainty: source.antecedent_handle ? [] : ["unresolved_local_mention"] };
    const candidates = sessionEntities.filter((entity) => entity.owner_account_id === request.owner_account_id);
    const candidateSnapshot: CandidateSnapshot = {
      snapshot_id: `candidate-snapshot:${request.owner_account_id}:${request.session_id}:${source.mention_id}`,
      owner_account_id: request.owner_account_id,
      frontier: request.graph_frontier,
      candidates: candidates.map((entity) => ({ entity_id: entity.entity_id, owner_account_id: entity.owner_account_id })),
      derivations: candidates.map((entity) => ({ artifact_kind: "candidate_derivation" as const, derivation_id: `candidate:${source.mention_id}:${entity.entity_id}`, owner_account_id: request.owner_account_id, source_ref: `${sourceIdentity.namespace_instance_ref}:${sourceIdentity.local_key}`, candidate_entity_id: entity.entity_id, strategy_ref: "all-owner-local-v1", input_refs: [source.evidence_id] })),
    };
    candidateArtifacts.push(...candidateSnapshot.derivations.map((derivation) => ({
      artifact_id: `candidate-artifact:${derivation.derivation_id}`, kind: "candidate_derivation" as const,
      owner_account_id: derivation.owner_account_id, source_ref: derivation.source_ref,
      candidate_entity_id: derivation.candidate_entity_id, strategy_ref: derivation.strategy_ref, input_refs: derivation.input_refs,
    })));
    const antecedent = handle.antecedent_handle ? localBindings.get(handle.antecedent_handle) : undefined;
    const support = antecedent && discourseUnit && antecedent.discourse_unit_ref === discourseUnit ? {
      coreference_support_id: `coreference:${request.session_id}:${antecedent.mention_id}:${source.mention_id}`,
      owner_account_id: request.owner_account_id, discourse_unit_ref: discourseUnit,
      antecedent_mention_id: antecedent.mention_id, anaphor_mention_id: source.mention_id,
      evidence_refs: [source.evidence_id], lineage_refs: [`mention:${antecedent.mention_id}`, `mention:${source.mention_id}`], lifecycle: "active" as const,
    } : undefined;
    if (support) coreferenceSupports.push(support);
    const resolution = await invokeEntityStrategy(request.model, { owner_account_id: request.owner_account_id, entities: sessionEntities, constraints: [] }, request.owner_account_id, handle, excerpt ? [source.evidence_id] : [], candidates.map((entity) => entity.entity_id), localBindings, sourceIdentity, candidateSnapshot, request.identity_authorizations, request.identity_authority_context, discourseUnit, support ? [support] : []);
    if (resolution.outcome === "same") {
      if (!antecedent) {
        const endpoints = [{ kind: "source_identity" as const, source_identity_ref: sourceIdentity }, { kind: "entity" as const, entity_id: resolution.entity_id }] as const;
        const authorization = request.identity_authorizations?.find((item) => authorizeIdentity(item, { owner_account_id: request.owner_account_id, endpoints, relation: "same", evaluated_frontier: request.graph_frontier }, request.identity_authority_context ?? { owner_confirmations: [], producer_assertions: [], standing_policies: [] }).authorized);
        if (authorization) usedAuthorizations.set(authorization.authorization_id, authorization);
      }
      if (discourseUnit) localBindings.set(handle.handle, { entity_id: resolution.entity_id, mention_id: source.mention_id, discourse_unit_ref: discourseUnit });
      mentions.push({ ...source, resolution: "resolved", entity_id: resolution.entity_id });
    } else mentions.push(source);
  }

  const revisions: AtomicGraphTransition["revisions"] = [];
  // Predicate identity is the extracted name plus slot set; rendering can change without moving a claim.
  const predicates = new Map<string, Predicate>();
  for (const provisional of request.provisionals) if (provisional.predicate_id && !predicates.has(provisional.predicate_id)) predicates.set(provisional.predicate_id, {
    predicate_id: provisional.predicate_id, owner_account_id: request.owner_account_id, predicate_revision_id: `${provisional.predicate_id}:initial`, identity_name: provisional.predicate, display_name: provisional.predicate, lifecycle: "provisional", slot_ids: provisional.arguments.map((argument) => argument.slot_id).sort(),
  });
  for (const predicate of predicates.values()) revisions.push({ kind: "predicate", revision_id: predicate.predicate_revision_id, predicate });
  const eventsByRevision = new Map((request.events ?? []).map((event) => [event.event_revision_id, event]));
  for (const event of request.events ?? []) revisions.push({ kind: "event", revision_id: event.event_revision_id, event });
  for (const evidence of request.evidence) {
    if (request.events && !eventsByRevision.has(evidence.event_revision_id)) throw new Error(`evidence lacks committed event revision: ${evidence.evidence_id}`);
    revisions.push({ kind: "evidence", revision_id: `evidence-revision:${evidence.evidence_id}`, evidence });
  }
  const adjacency: AtomicGraphTransition["adjacency"] = [];
  const results: AtomicGraphTransition["placement"]["results"] = [];
  const allocations: Record<string, string> = {};
  const artifacts: AtomicGraphTransition["artifacts"] = [...candidateArtifacts];
  const admittedProvisionals = new Set<string>();
  const ownerEntityIds = new Set(sessionEntities.filter((entity) => entity.owner_account_id === request.owner_account_id).map((entity) => entity.entity_id));
  for (const provisional of request.provisionals) {
    const claimMentions = mentions.filter((mention) => mention.claim_revision_id === provisional.claim_revision_id);
    const bound = durableRoleSlotBindings(claimMentions);
    const claimForScope: ProvisionalClaim = { ...provisional, arguments: provisional.arguments.map((argument) => bound.has(argument.slot_id) ? { ...argument, value: { kind: "entity_ref" as const, ref: bound.get(argument.slot_id)! } } : argument) };
    const scope_plan = await invokeScopeStrategy(request.model, claimForScope, sessionEntities, request.evidence);
    const unit_boundary = await invokeUnitBoundaryStrategy(request.model, claimForScope, request.evidence);
    const allRoleSlotsResolved = provisional.arguments.every((argument) => {
      const entityId = bound.get(argument.slot_id);
      return entityId !== undefined && ownerEntityIds.has(entityId) && scope_plan.bindings[argument.slot_id] === entityId;
    });
    // D40/D41: scope may never promote a partial or guessed role binding.
    // Canonical placement is allowed only after every original role mention
    // resolved to a durable entity and the scope plan agrees with it.
    const admitted = unit_boundary.decision === "accept_ltm" && scope_plan.confidently_placed && allRoleSlotsResolved;
    const canonicalId = canonicalRevisionId(coordinate, provisional.claim_revision_id);
    revisions.push({ kind: "claim", revision_id: provisional.claim_revision_id, claim: provisional, placement_status: admitted ? "consumed" : "provisional_abstained" });
    if (admitted) {
      admittedProvisionals.add(provisional.claim_revision_id);
      allocations[provisional.claim_revision_id] = canonicalId;
      const { ambiguity_markers: _ambiguityMarkers, context_packet: _contextPacket, ...canonicalBase } = claimForScope;
      const canonical = {
        ...canonicalBase,
        claim_revision_id: canonicalId,
        arguments: claimForScope.arguments.map((argument) => bound.has(argument.slot_id)
          ? { ...argument, value: { kind: "entity_ref" as const, ref: bound.get(argument.slot_id)! } }
          : argument),
        temporal_scope: { ...claimForScope.temporal_scope, valid_time: request.valid_times[provisional.claim_revision_id]! },
        scope: scope_plan.scope!, lifecycle: "canonical" as const, canonical_claim_id: canonicalId,
        source_provisional_revision_ids: [provisional.claim_revision_id],
      };
      revisions.push({ kind: "claim", revision_id: canonicalId, claim: canonical, placement_status: "canonical" });
      for (const [slot_id, entity_id] of bound) adjacency.push({ claim_revision_id: canonicalId, entity_id, role_slot_id: slot_id });
      results.push({ input_provisional_revision_id: provisional.claim_revision_id, disposition: "admit", operation: null });
    } else results.push({ input_provisional_revision_id: provisional.claim_revision_id, disposition: "defer_review", operation: null, re_resolution_trigger: unit_boundary.decision === "abstain" ? "boundary_reconsideration" : "new_identity_evidence" });
    artifacts.push(...buildFlywheelArtifacts({ provisional_revision_id: provisional.claim_revision_id, canonical_claim_revision_id: admitted ? canonicalId : null, scope_plan, unit_boundary, mentions: claimMentions, newly_minted_entity_ids: [] }));
  }
  for (const mention of mentions) revisions.push({ kind: "mention", revision_id: `mention:${mention.mention_id}`, mention });
  for (const authorization of usedAuthorizations.values()) {
    const source = authorization.endpoints.find((endpoint) => endpoint.kind === "source_identity");
    const target = authorization.endpoints.find((endpoint) => endpoint.kind === "entity");
    if (source?.kind === "source_identity" && target?.kind === "entity" && mentions.some((mention) => admittedProvisionals.has(mention.claim_revision_id) && mention.entity_id === target.entity_id && mention.source_identity_ref?.namespace_instance_ref === source.source_identity_ref.namespace_instance_ref && mention.source_identity_ref.local_key === source.source_identity_ref.local_key)) {
      revisions.push({ kind: "identity_authorization", revision_id: `identity-authorization:${authorization.authorization_id}`, authorization });
    }
  }
  for (const support of coreferenceSupports) revisions.push({ kind: "coreference_support", revision_id: `coreference-support:${support.coreference_support_id}`, support });
  const derivation = prepareDerivation({
    attempt_id: `attempt:session:${coordinate}`,
    commit_id: `commit:session:${coordinate}`,
    owner_account_id: request.owner_account_id, parent_commit: request.parent_commit, idempotency_key: key,
    input_revisions: inputRevisions,
    output_revisions: revisions.map((revision) => ({ revision_id: revision.revision_id, content: revisionContent(revision) })),
    versions: request.versions, success_kind: allocations && Object.keys(allocations).length ? "success" : "successful_empty",
  });
  return request.ledger.appendTransitionPlan({ placement: { offline_experiment: true, allocations, results }, derivation, revisions, adjacency, artifacts, identity_authority_context: request.identity_authority_context });
};
