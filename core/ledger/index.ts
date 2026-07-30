import { createHash } from "node:crypto";
import type { AllocatedPlacementPlan } from "../consolidate/plan";
import type { CanonicalClaim, Entity, IdentityConstraint, ProvisionalClaim } from "../schema";

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
export type ClaimPlacementStatus = "canonical" | "consumed" | "withheld_unresolved_subject" | "withheld_abstained";
export interface ClaimRevision {
  kind: "claim";
  revision_id: string;
  claim: CanonicalClaim | ProvisionalClaim;
  placement_status: ClaimPlacementStatus;
}
export interface EntityRevision { kind: "entity"; revision_id: string; entity: Entity; }
export interface IdentityRevision { kind: "identity"; revision_id: string; constraint: IdentityConstraint; }
export type GraphRevision = ClaimRevision | EntityRevision | IdentityRevision;
export interface GeneratedAdjacency { claim_revision_id: string; entity_id: string; role_slot_id: string; }

/** T9's typed persistence input: T7 allocation plus the already-validated immutable payloads. */
export interface AtomicGraphTransition {
  placement: AllocatedPlacementPlan;
  derivation: PreparedDerivation;
  revisions: readonly GraphRevision[];
  adjacency: readonly GeneratedAdjacency[];
}

export class GraphTransitionValidationError extends Error {}

/** Pure guard for the D13 claim-to-generated-adjacency invariant before any I/O begins. */
export const validateAtomicGraphTransition = (transition: AtomicGraphTransition): void => {
  const revisionIds = new Set<string>();
  for (const revision of transition.revisions) {
    if (revisionIds.has(revision.revision_id)) throw new GraphTransitionValidationError(`duplicate revision id: ${revision.revision_id}`);
    revisionIds.add(revision.revision_id);
  }
  const dispositionIds = new Set(transition.placement.results.map((result) => result.input_provisional_revision_id));
  for (const result of transition.placement.results) if (!revisionIds.has(result.input_provisional_revision_id)) throw new GraphTransitionValidationError(`missing provisional revision for disposition: ${result.input_provisional_revision_id}`);
  const adjacencyByClaim = new Map<string, GeneratedAdjacency[]>();
  for (const edge of transition.adjacency) {
    if (!revisionIds.has(edge.claim_revision_id)) throw new GraphTransitionValidationError(`adjacency references unknown claim: ${edge.claim_revision_id}`);
    adjacencyByClaim.set(edge.claim_revision_id, [...(adjacencyByClaim.get(edge.claim_revision_id) ?? []), edge]);
  }
  for (const revision of transition.revisions) {
    if (revision.kind !== "claim") continue;
    if (revision.claim.lifecycle === "provisional" && !dispositionIds.has(revision.revision_id)) throw new GraphTransitionValidationError(`unaccounted provisional claim: ${revision.revision_id}`);
    if (revision.placement_status === "canonical" && revision.claim.lifecycle !== "canonical") throw new GraphTransitionValidationError(`canonical status requires a canonical claim: ${revision.revision_id}`);
    if (revision.placement_status === "canonical" && !(adjacencyByClaim.get(revision.revision_id)?.length)) throw new GraphTransitionValidationError(`active claim lacks generated adjacency: ${revision.revision_id}`);
    if (revision.placement_status !== "canonical" && revision.claim.lifecycle !== "provisional") throw new GraphTransitionValidationError(`non-canonical claim must remain provisional: ${revision.revision_id}`);
  }
};

export interface LedgerPort { appendTransitionPlan(plan: AtomicGraphTransition): Promise<{ commit_id: string; sequence: number; idempotent: boolean }>; }
export interface LedgerSnapshot { owner_account_id: string; graph_generation: number; }
