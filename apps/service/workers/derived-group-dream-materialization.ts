import { isProxy } from "node:util/types";

import {
  parseDerivedGroupDreamOutcome,
  type DerivedGroupDreamOutcome,
} from "../../../core/consolidate/derived-group-dream";
import {
  parseDurableMemoryWorkJob,
  type DurableMemoryWorkErrorCode,
  type DurableMemoryWorkJob,
} from "../../../core/consolidate/state-machine";
import {
  parseRegisteredMemoryStrategy,
  type RegisteredMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import {
  prepareDerivation,
  type AtomicGraphTransition,
  type CanonicalJson,
  type GraphRevision,
} from "../../../core/ledger";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  assertAuthoritativeLedgerAppend,
  authoritativeAppendRequestDigest,
  type AuthoritativeLedgerAppend,
} from "../stores/authoritative-ledger-repository";
import {
  parseStagedDurableMemoryWorkResult,
  type StagedDurableMemoryWorkResult,
} from "../stores/durable-memory-work-result-repository";
import { DERIVED_GROUP_DREAM_RESULT_CONTRACT_VERSION } from "./derived-group-dream-contract";
import type { DurableMemoryWorkMaterializeOutcome } from "./durable-memory-work-runner";

export const DERIVED_GROUP_DREAM_MATERIALIZATION_VERSION =
  "derived-group-dream-materialization-v1" as const;

export type DerivedGroupDreamWitnessLoadOutcome =
  | Readonly<{ kind: "found"; committed_revisions: readonly GraphRevision[] }>
  | Readonly<{ kind: "failed"; error_code: DurableMemoryWorkErrorCode }>;

const fail = (code: string): never => { throw new TypeError(`derived group dream materialization ${code}`); };

const claimRevisionContent = (revision: GraphRevision): CanonicalJson => {
  if (revision.kind !== "claim") fail("invalid_witness");
  return revision.claim as unknown as CanonicalJson;
};

const versionsFor = (strategy: Readonly<RegisteredMemoryStrategy>) => ({
  strategy_version: strategy.coordinates.strategy_version,
  model_version: strategy.coordinates.model_version,
  prompt_version: strategy.coordinates.prompt_version,
  policy_version: strategy.coordinates.policy_version,
  code_version: strategy.coordinates.code_version,
  schema_version: strategy.coordinates.schema_version,
  tokenizer_version: strategy.coordinates.tokenizer_version,
  tool_version: strategy.coordinates.tool_version,
});

const witnessClaims = (witnesses: readonly GraphRevision[]): readonly GraphRevision[] => {
  const claims = witnesses.map((witness) => {
    if (witness.kind !== "claim") fail("invalid_witness");
    return witness;
  });
  const revisionIds = claims.map((item) => item.revision_id).sort();
  if (revisionIds.length !== new Set(revisionIds).size) fail("duplicate_witness");
  return Object.freeze(claims);
};

export const derivedGroupDreamMaterializationDigest = (
  outcome: Readonly<DerivedGroupDreamOutcome>,
  parentCommit: string | null,
): string => sha256CanonicalContent({
  contract_version: DERIVED_GROUP_DREAM_MATERIALIZATION_VERSION,
  parent_commit: parentCommit,
  outcome_digest: outcome.result_digest,
  group_projection_ids: outcome.group_projections.map((item) => item.group_projection_id),
  people_belief_revision_ids: outcome.people_cluster_beliefs.map((item) => item.belief_revision_id),
  original_claim_revision_ids: outcome.original_claim_revision_ids,
});

export const createDerivedGroupDreamAuthoritativeAppend = (
  contextValue: AuthorizedLedgerWriteContext,
  jobValue: DurableMemoryWorkJob,
  strategyValue: RegisteredMemoryStrategy,
  outcomeValue: Readonly<DerivedGroupDreamOutcome>,
  witnessValue: readonly GraphRevision[],
  parentCommit: string | null,
): AuthoritativeLedgerAppend => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  if (context.capability !== "memories.work.execute") fail("capability_denied");
  const job = parseDurableMemoryWorkJob(jobValue);
  const strategy = parseRegisteredMemoryStrategy(strategyValue);
  const outcome = parseDerivedGroupDreamOutcome(outcomeValue);
  if (outcome.owner_account_id !== job.owner_account_id
    || outcome.input_frontier !== job.input_frontier
    || strategy.work_kind !== "derived_group_dream"
    || strategy.coordinates.result_contract_version !== DERIVED_GROUP_DREAM_RESULT_CONTRACT_VERSION) {
    fail("coordinate_mismatch");
  }
  const witnesses = witnessClaims(witnessValue);
  const witnessIds = witnesses.map((item) => item.revision_id).sort();
  if (!witnessIds.every((id, index) => id === outcome.original_claim_revision_ids[index])
    || witnessIds.length !== outcome.original_claim_revision_ids.length) {
    fail("witness_mismatch");
  }
  const materializationDigest = derivedGroupDreamMaterializationDigest(outcome, parentCommit);
  const inputRevisions = witnesses.map((witness) => ({
    revision_id: witness.revision_id,
    content: claimRevisionContent(witness),
  }));
  const derivation = prepareDerivation({
    attempt_id: `attempt:derived-group-dream:${materializationDigest}`,
    commit_id: `commit:derived-group-dream:${materializationDigest}`,
    owner_account_id: job.owner_account_id,
    parent_commit: parentCommit,
    idempotency_key: `append:derived-group-dream:${materializationDigest}`,
    input_revisions: inputRevisions,
    output_revisions: [],
    versions: versionsFor(strategy),
    success_kind: "success",
  });
  const transition: AtomicGraphTransition = {
    placement: { offline_experiment: true, allocations: {}, results: [] },
    derivation,
    revisions: [],
    adjacency: [],
    artifacts: [],
    committed_revisions: witnesses,
  };
  const origin = Object.freeze({
    kind: "non_formation" as const,
    reason: "derived_group_dream" as const,
  });
  const append: AuthoritativeLedgerAppend = {
    append_attempt: {
      idempotency_key: derivation.commit.idempotency_key,
      expected_parent_commit: parentCommit,
      request_digest: authoritativeAppendRequestDigest(transition, origin),
    },
    origin,
    transition,
  };
  return assertAuthoritativeLedgerAppend(context, append);
};

export const derivedGroupDreamMaterializationIsEmpty = (
  stagedValue: StagedDurableMemoryWorkResult,
): boolean => {
  const staged = parseStagedDurableMemoryWorkResult(stagedValue);
  const outcome = parseDerivedGroupDreamOutcome(staged.normalized_result);
  return outcome.group_projections.length === 0 && outcome.people_cluster_beliefs.length === 0;
};

export const materializeDerivedGroupDream = (
  contextValue: AuthorizedLedgerWriteContext,
  jobValue: DurableMemoryWorkJob,
  stagedValue: StagedDurableMemoryWorkResult,
  strategyValue: RegisteredMemoryStrategy,
  parentCommit: string | null,
  witnessValue: readonly GraphRevision[],
): Readonly<{ kind: "ready"; result_kind: "successful"; authoritative_append: AuthoritativeLedgerAppend }> => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  const job = parseDurableMemoryWorkJob(jobValue);
  const staged = parseStagedDurableMemoryWorkResult(stagedValue, job);
  const strategy = parseRegisteredMemoryStrategy(strategyValue);
  if (staged.result_contract_version !== strategy.coordinates.result_contract_version) {
    fail("staged_result_contract_mismatch");
  }
  const outcome = parseDerivedGroupDreamOutcome(staged.normalized_result);
  if (outcome.result_digest !== staged.response_digest) fail("response_digest_mismatch");
  return Object.freeze({
    kind: "ready" as const,
    result_kind: "successful" as const,
    authoritative_append: createDerivedGroupDreamAuthoritativeAppend(
      context, job, strategy, outcome, witnessValue, parentCommit,
    ),
  });
};

const exactWitnessArray = (value: unknown): readonly GraphRevision[] => {
  if (!Array.isArray(value) || isProxy(value)) fail("invalid_witnesses");
  return Object.freeze(value as readonly GraphRevision[]);
};

export const materializeDerivedGroupDreamFromLoadedWitnesses = (
  contextValue: AuthorizedLedgerWriteContext,
  jobValue: DurableMemoryWorkJob,
  stagedValue: StagedDurableMemoryWorkResult,
  strategyValue: RegisteredMemoryStrategy,
  parentCommit: string | null,
  witnessLoad: DerivedGroupDreamWitnessLoadOutcome,
): DurableMemoryWorkMaterializeOutcome => {
  if (witnessLoad.kind === "failed") {
    return Object.freeze({ kind: "failed" as const, error_code: witnessLoad.error_code });
  }
  try {
    if (derivedGroupDreamMaterializationIsEmpty(stagedValue)) {
      return Object.freeze({
        kind: "ready" as const,
        result_kind: "successful_empty" as const,
        authoritative_append: null,
      });
    }
    return materializeDerivedGroupDream(
      contextValue, jobValue, stagedValue, strategyValue, parentCommit,
      exactWitnessArray(witnessLoad.committed_revisions),
    );
  } catch {
    return Object.freeze({ kind: "failed" as const, error_code: "model_response_invalid" });
  }
};
