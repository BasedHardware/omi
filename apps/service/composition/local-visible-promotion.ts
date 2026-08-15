// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
import { prepareDerivation, type AtomicGraphTransition } from "../../../core/ledger";
import { persistValidTime } from "../../../core/retrieve/temporal";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import type { CanonicalClaim, ProvisionalClaim } from "../../../core/schema";
import type { SqliteLedger } from "../../../drivers/sqlite";

const VERSIONS = Object.freeze({
  strategy_version: "local-visible-promotion-v1",
  model_version: "scripted:v1",
  prompt_version: "none",
  policy_version: "policy:v1",
  code_version: "code:v1",
  schema_version: "schema:v1",
  tokenizer_version: "none",
  tool_version: "none",
});

export interface LocalVisiblePromotionReport {
  readonly promoted: number;
  readonly predicates: readonly string[];
}

/**
 * Formation's STM-to-LTM plan abstains without owner identity (integrator notes
 * carry `identity_authority_context: null` by contract). This local step keeps
 * the structured claim and writes a new canonical revision with literal
 * arguments so the existing QA synthesizer can render the fact. It does not
 * filter, quality-gate, or drop user content.
 */
export const promoteLocalVisibleClaims = (
  ledger: SqliteLedger,
  ownerAccountId: string,
  accountTimezone: string,
): LocalVisiblePromotionReport => {
  const snapshot = ledger.snapshot(ownerAccountId);
  const alreadyCanonical = new Set(
    snapshot.claims
      .filter((item) => item.claim.lifecycle === "canonical")
      .flatMap((item) => item.claim.lifecycle === "canonical"
        ? item.claim.source_provisional_revision_ids
        : []),
  );
  const provisionals = snapshot.claims.filter((item) =>
    item.placement_status === "provisional_abstained"
    && item.claim.lifecycle === "provisional"
    && !alreadyCanonical.has(item.revision_id));
  if (provisionals.length === 0) {
    return Object.freeze({ promoted: 0, predicates: Object.freeze([]) });
  }

  const revisions: AtomicGraphTransition["revisions"] = [];
  const predicates: string[] = [];
  for (const item of provisionals) {
    const provisional = item.claim as ProvisionalClaim;
    const observed = provisional.temporal_scope.observed_at;
    const canonicalId = `canonical:local-visible:${provisional.claim_revision_id}`;
    const validTime = provisional.temporal_scope.valid_time ?? persistValidTime(
      { kind: "imprecise", bucket: "unknown", precision: "coarse" },
      { query_at: observed, capture_at: observed },
      accountTimezone,
    );
    const claim: CanonicalClaim = {
      claim_lineage_id: provisional.claim_lineage_id,
      claim_revision_id: canonicalId,
      owner_account_id: provisional.owner_account_id,
      ...(provisional.predicate_id ? { predicate_id: provisional.predicate_id } : {}),
      predicate: provisional.predicate,
      arguments: provisional.arguments.map((argument) => ({
        slot_id: argument.slot_id,
        role: argument.role,
        value: {
          kind: "literal" as const,
          value: argument.surface ?? "noted",
        },
      })),
      ...(provisional.polarity ? { polarity: provisional.polarity } : {}),
      temporal_scope: {
        observed_at: observed,
        precision: provisional.temporal_scope.precision,
        valid_time: validTime,
      },
      evidence_refs: [...provisional.evidence_refs],
      policy_labels: [...provisional.policy_labels],
      source_language: provisional.source_language,
      scope: { locality: "durable", scope_ref: "global" },
      lifecycle: "canonical",
      canonical_claim_id: canonicalId,
      source_provisional_revision_ids: [provisional.claim_revision_id],
    };
    revisions.push({
      kind: "claim",
      revision_id: canonicalId,
      claim,
      placement_status: "canonical",
    });
    predicates.push(provisional.predicate);
  }

  const digest = sha256CanonicalContent({
    contract_version: "local-visible-promotion-v1",
    owner_account_id: ownerAccountId,
    provisional_revision_ids: provisionals.map((item) => item.revision_id).sort(),
  });
  const head = ledger.graphHead(ownerAccountId);
  const derivation = prepareDerivation({
    attempt_id: `attempt:local-visible:${digest}`,
    commit_id: `commit:local-visible:${digest}`,
    owner_account_id: ownerAccountId,
    parent_commit: head?.commit_id ?? null,
    idempotency_key: `append:local-visible:${digest}`,
    input_revisions: provisionals.map((item) => ({
      revision_id: item.revision_id,
      content: item.claim,
    })),
    output_revisions: revisions.map((revision) => ({
      revision_id: revision.revision_id,
      content: revision.kind === "claim" ? revision.claim : revision,
    })),
    versions: VERSIONS,
    success_kind: "success",
  });
  ledger.append({
    placement: { offline_experiment: true, allocations: {}, results: [] },
    derivation,
    revisions,
    adjacency: [],
    artifacts: [],
  });
  return Object.freeze({
    promoted: revisions.length,
    predicates: Object.freeze(predicates),
  });
};
