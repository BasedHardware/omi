import type { Entity, IdentityConstraint } from "../schema";
import type { LocalHandle } from "./mentions";

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
}
export type EntityResolution =
  | { outcome: "same"; entity_id: string; blockers: readonly string[] }
  | { outcome: "distinct"; blockers: readonly string[] }
  | { outcome: "abstain"; blockers: readonly string[] };

/** Pure request construction. Candidate selection and any model response remain data. */
export const buildEntityResolutionRequest = (owner_account_id: string, local_handle: LocalHandle, evidence_refs: readonly string[], candidate_entity_ids: readonly string[], candidate_entities?: readonly EntityResolutionCandidate[]): EntityResolutionRequest =>
  ({ strategy: "local-handle-durable-entity", version: "v1", owner_account_id, local_handle, evidence_refs, candidate_entity_ids, ...(candidate_entities ? { candidate_entities } : {}) });

const activeDistinct = (constraints: readonly IdentityConstraint[], left: string, right: string) => constraints.some((constraint) =>
  constraint.relation === "distinct" && constraint.reversed_at === null &&
  ((constraint.left_handle === left && constraint.right_handle === right) || (constraint.left_handle === right && constraint.right_handle === left)));

/** Pure deterministic blockers run before a proposal. They are never overridden by a model. */
export const planEntityResolution = (table: EntityTable, request: EntityResolutionRequest, proposal: EntityProposal, localBindings: ReadonlyMap<string, string> = new Map()): EntityResolution => {
  if (table.owner_account_id !== request.owner_account_id) return { outcome: "abstain", blockers: ["account_boundary"] };
  if (request.evidence_refs.length === 0) return { outcome: "abstain", blockers: ["missing_evidence"] };
  if (request.local_handle.antecedent_handle) {
    const antecedentEntity = localBindings.get(request.local_handle.antecedent_handle);
    if (antecedentEntity) return { outcome: "same", entity_id: antecedentEntity, blockers: [] };
  }
  if (proposal.decision === "abstain" || proposal.decision === "distinct") return { outcome: proposal.decision, blockers: [] };
  const target = table.entities.find((entity) => entity.entity_id === proposal.entity_id);
  if (!target || target.owner_account_id !== request.owner_account_id) return { outcome: "abstain", blockers: ["account_boundary"] };
  if (activeDistinct(table.constraints, request.local_handle.handle, target.handle)) return { outcome: "distinct", blockers: ["explicit_distinctness"] };
  return { outcome: "same", entity_id: target.entity_id, blockers: [] };
};

export type IdentityOperation =
  | { kind: "merge"; constraint: IdentityConstraint }
  | { kind: "split"; constraint_id: string; effective_at: number };

/** Immutable/reversible identity history: a split only closes the selected same constraint. */
export const applyIdentityOperation = (constraints: readonly IdentityConstraint[], operation: IdentityOperation): IdentityConstraint[] => {
  if (operation.kind === "merge") return [...constraints, operation.constraint];
  return constraints.map((constraint) => constraint.constraint_id === operation.constraint_id
    ? { ...constraint, reversed_at: operation.effective_at }
    : constraint);
};

/** Read-time canonicalization uses only active, owner-local constraints as of the requested frontier. */
export const canonicalHandleAt = (table: EntityTable, entity_id: string, as_of: number): string | null => {
  const entity = table.entities.find((item) => item.entity_id === entity_id && item.owner_account_id === table.owner_account_id);
  if (!entity) return null;
  const handles = new Map(table.entities.filter((item) => item.owner_account_id === table.owner_account_id).map((item) => [item.handle, item]));
  const parent = new Map([...handles.keys()].map((handle) => [handle, handle]));
  const find = (handle: string): string => { const root = parent.get(handle)!; return root === handle ? root : find(root); };
  const join = (left: string, right: string) => { if (parent.has(left) && parent.has(right)) parent.set(find(right), find(left)); };
  for (const constraint of table.constraints) {
    const activeAt = constraint.relation === "same" && constraint.effective_at <= as_of && (constraint.reversed_at === null || constraint.reversed_at > as_of);
    if (activeAt) join(constraint.left_handle, constraint.right_handle);
  }
  const root = find(entity.handle);
  return [...handles.keys()].filter((handle) => find(handle) === root).sort()[0] ?? null;
};
