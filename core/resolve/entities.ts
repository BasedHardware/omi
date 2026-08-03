import type { CoreferenceSupport, Entity, IdentityAuthorization, IdentityConstraint, IdentityEndpoint, SourceIdentityRef } from "../schema";
import type { LocalHandle } from "./mentions";
import { authorizeIdentity, type IdentityAuthorityContext } from "./identity-authority";
import { candidateSnapshotContains, type CandidateSnapshot } from "./candidates";

export interface EntityTable { owner_account_id: string; entities: readonly Entity[]; constraints: readonly IdentityConstraint[]; }
export type EntityProposal = { decision: "same"; entity_id: string } | { decision: "distinct" } | { decision: "abstain" };
/** Model-facing context only; resolution still authorizes targets by ID from the table. */
export interface EntityResolutionCandidate { entity_id: string; handle: string; labels: readonly string[]; }
export interface EntityResolutionRequest {
  strategy: "local-handle-durable-entity";
  version: "v1";
  owner_account_id: string;
  local_handle: LocalHandle;
  evidence_refs: readonly string[];
  candidate_entity_ids: readonly string[];
  candidate_entities?: readonly EntityResolutionCandidate[];
  /** Capture coordinate, never a rendering or model mention id. */
  source_identity_ref?: SourceIdentityRef;
  candidate_snapshot: CandidateSnapshot;
  authorizations?: readonly IdentityAuthorization[];
  authority_context?: IdentityAuthorityContext;
  /** The D44 unit in which a coreference edge is admissible. */
  discourse_unit_ref?: string | null;
  coreference_supports?: readonly CoreferenceSupport[];
}
export type EntityResolution =
  | { outcome: "same"; entity_id: string; blockers: readonly string[] }
  | { outcome: "distinct"; blockers: readonly string[] }
  | { outcome: "abstain"; blockers: readonly string[] };

/** Pure request construction. Candidate selection and any model response remain data. */
export const buildEntityResolutionRequest = (owner_account_id: string, local_handle: LocalHandle, evidence_refs: readonly string[], candidate_entity_ids: readonly string[], candidate_entities?: readonly EntityResolutionCandidate[], source_identity_ref?: SourceIdentityRef, candidate_snapshot?: CandidateSnapshot, authorizations?: readonly IdentityAuthorization[], authority_context?: IdentityAuthorityContext, discourse_unit_ref?: string | null, coreference_supports?: readonly CoreferenceSupport[]): EntityResolutionRequest =>
  ({ strategy: "local-handle-durable-entity", version: "v1", owner_account_id, local_handle, evidence_refs, candidate_entity_ids, ...(candidate_entities ? { candidate_entities } : {}), ...(source_identity_ref ? { source_identity_ref } : {}), candidate_snapshot: candidate_snapshot ?? { snapshot_id: `implicit:${owner_account_id}:${local_handle.handle}`, owner_account_id, frontier: 0, candidates: candidate_entity_ids.map((entity_id) => ({ entity_id, owner_account_id })), derivations: [] }, authorizations: authorizations ?? [], authority_context, discourse_unit_ref, coreference_supports: coreference_supports ?? [] });

const endpointKey = (endpoint: IdentityEndpoint): string => endpoint.kind === "entity"
  ? `entity:${endpoint.entity_id}`
  : `source:${JSON.stringify([
    endpoint.source_identity_ref.namespace_instance_ref,
    endpoint.source_identity_ref.local_key,
    endpoint.source_identity_ref.producer.producer_ref,
    endpoint.source_identity_ref.producer.contract_ref,
    endpoint.source_identity_ref.asserted_identity.domain,
    endpoint.source_identity_ref.asserted_identity.scope_ref,
  ])}`;

const activeAt = (constraint: IdentityConstraint, frontier: number) =>
  constraint.effective_at <= frontier && (constraint.reversed_at === null || constraint.reversed_at > frontier) && !!constraint.endpoints;

/** Relation closure is over typed referent/entity ids, never model handles/renderings. */
const activeDistinct = (constraints: readonly IdentityConstraint[], left: IdentityEndpoint, right: IdentityEndpoint, frontier: number): boolean => {
  const parent = new Map<string, string>();
  const find = (key: string): string => { const root = parent.get(key) ?? key; if (!parent.has(key)) parent.set(key, key); return root === key ? root : find(root); };
  const join = (a: string, b: string) => parent.set(find(b), find(a));
  for (const constraint of constraints) if (constraint.relation === "same" && activeAt(constraint, frontier)) {
    const [a, b] = constraint.endpoints!;
    join(endpointKey(a), endpointKey(b));
  }
  const leftClass = find(endpointKey(left));
  const rightClass = find(endpointKey(right));
  return constraints.some((constraint) => {
    if (constraint.relation !== "distinct" || !activeAt(constraint, frontier)) return false;
    const [a, b] = constraint.endpoints!;
    return (find(endpointKey(a)) === leftClass && find(endpointKey(b)) === rightClass) || (find(endpointKey(a)) === rightClass && find(endpointKey(b)) === leftClass);
  });
};

/** Reject relation contradictions through equivalence classes, not just direct pairs. */
export const identityConstraintConflicts = (constraints: readonly IdentityConstraint[], incoming: IdentityConstraint): boolean => {
  if (!incoming.endpoints) return true;
  const frontier = incoming.effective_at;
  const [left, right] = incoming.endpoints;
  if (incoming.relation === "same") return activeDistinct(constraints, left, right, frontier);
  const parent = new Map<string, string>();
  const find = (key: string): string => { const root = parent.get(key) ?? key; if (!parent.has(key)) parent.set(key, key); return root === key ? root : find(root); };
  const join = (a: string, b: string) => parent.set(find(b), find(a));
  for (const constraint of constraints) if (constraint.relation === "same" && activeAt(constraint, frontier)) {
    const [a, b] = constraint.endpoints!;
    join(endpointKey(a), endpointKey(b));
  }
  return find(endpointKey(left)) === find(endpointKey(right));
};

export interface LocalDurableBinding { entity_id: string; mention_id: string; discourse_unit_ref: string; }

/** Pure deterministic blockers run before a proposal. They are never overridden by a model. */
export const planEntityResolution = (table: EntityTable, request: EntityResolutionRequest, proposal: EntityProposal, localBindings: ReadonlyMap<string, LocalDurableBinding> = new Map()): EntityResolution => {
  if (table.owner_account_id !== request.owner_account_id) return { outcome: "abstain", blockers: ["account_boundary"] };
  if (request.evidence_refs.length === 0) return { outcome: "abstain", blockers: ["missing_evidence"] };
  if (request.local_handle.antecedent_handle) {
    const antecedent = localBindings.get(request.local_handle.antecedent_handle);
    const support = antecedent && request.discourse_unit_ref ? request.coreference_supports?.find((item) =>
      item.lifecycle === "active" && item.owner_account_id === request.owner_account_id &&
      item.discourse_unit_ref === request.discourse_unit_ref && item.antecedent_mention_id === antecedent.mention_id &&
      item.anaphor_mention_id === request.local_handle.mention_ref && item.evidence_refs.some((ref) => request.evidence_refs.includes(ref)) &&
      item.lineage_refs.includes(`mention:${antecedent.mention_id}`) && item.lineage_refs.includes(`mention:${request.local_handle.mention_ref}`)) : undefined;
    if (antecedent && support) return { outcome: "same", entity_id: antecedent.entity_id, blockers: [] };
    if (antecedent) return { outcome: "abstain", blockers: ["missing_persisted_in_unit_coreference_support"] };
  }
  // I0-I3 deliberately keep unmatched/source-local separate from `distinct`.
  if (proposal.decision === "abstain" || proposal.decision === "distinct") return { outcome: "abstain", blockers: proposal.decision === "distinct" ? ["distinct_requires_pair_specific_authorization"] : [] };
  if (!request.source_identity_ref) return { outcome: "abstain", blockers: ["missing_typed_source_identity"] };
  if (!candidateSnapshotContains(request.candidate_snapshot, request.owner_account_id, proposal.entity_id)) return { outcome: "abstain", blockers: ["candidate_snapshot_boundary"] };
  const authorizedTargets = request.candidate_snapshot.candidates.flatMap((candidate) => {
    const target = table.entities.find((entity) => entity.entity_id === candidate.entity_id && entity.owner_account_id === request.owner_account_id);
    if (!target || !candidateSnapshotContains(request.candidate_snapshot, request.owner_account_id, target.entity_id)) return [];
    const endpoints = [{ kind: "source_identity" as const, source_identity_ref: request.source_identity_ref! }, { kind: "entity" as const, entity_id: target.entity_id }] as const;
    if (activeDistinct(table.constraints, endpoints[0], endpoints[1], request.candidate_snapshot.frontier)) return [];
    const expected = { owner_account_id: request.owner_account_id, endpoints, relation: "same" as const, evaluated_frontier: request.candidate_snapshot.frontier };
    return (request.authorizations ?? []).some((item) => authorizeIdentity(item, expected, request.authority_context ?? { owner_confirmations: [], producer_assertions: [], standing_policies: [] }).authorized) ? [target] : [];
  });
  // The model may rank coverage, but an exact authorization chooses the target.
  return authorizedTargets.length === 1 ? { outcome: "same", entity_id: authorizedTargets[0]!.entity_id, blockers: [] } : { outcome: "abstain", blockers: [authorizedTargets.length ? "ambiguous_authorizations" : "missing_authorization"] };
};

export type IdentityOperation =
  | { kind: "merge"; constraint: IdentityConstraint }
  | { kind: "split"; constraint_id: string; effective_at: number };

/** Immutable/reversible identity history: a split only closes the selected same constraint. */
export const applyIdentityOperation = (constraints: readonly IdentityConstraint[], operation: IdentityOperation): IdentityConstraint[] => {
  if (operation.kind === "merge") {
    if (identityConstraintConflicts(constraints, operation.constraint)) throw new Error("identity relation conflicts with active equivalence class");
    return [...constraints, operation.constraint];
  }
  // A split closes a `same` constraint and nothing else. Matching on the id
  // alone let a split reverse a `distinct` constraint, which re-opens the merge
  // that constraint was recorded to forbid -- a false-merge path inside the
  // layer whose entire purpose is preventing false merges.
  return constraints.map((constraint) => constraint.constraint_id === operation.constraint_id && constraint.relation === "same"
    ? { ...constraint, reversed_at: operation.effective_at }
    : constraint);
};

/** Read-time canonicalization uses only active, owner-local constraints as of the requested frontier. */
export const canonicalHandleAt = (table: EntityTable, entity_id: string, as_of: number): string | null => {
  const entity = table.entities.find((item) => item.entity_id === entity_id && item.owner_account_id === table.owner_account_id);
  if (!entity) return null;
  const entities = new Map(table.entities.filter((item) => item.owner_account_id === table.owner_account_id).map((item) => [item.entity_id, item]));
  const parent = new Map([...entities.keys()].map((id) => [id, id]));
  const find = (id: string): string => { const root = parent.get(id)!; return root === id ? root : find(root); };
  const join = (left: string, right: string) => { if (parent.has(left) && parent.has(right)) parent.set(find(right), find(left)); };
  for (const constraint of table.constraints) {
    const activeAt = constraint.relation === "same" && constraint.effective_at <= as_of && (constraint.reversed_at === null || constraint.reversed_at > as_of);
    if (activeAt && constraint.endpoints?.[0].kind === "entity" && constraint.endpoints?.[1].kind === "entity") join(constraint.endpoints[0].entity_id, constraint.endpoints[1].entity_id);
  }
  const root = find(entity.entity_id);
  return [...entities.values()].filter((item) => find(item.entity_id) === root).map((item) => item.handle).sort()[0] ?? null;
};
