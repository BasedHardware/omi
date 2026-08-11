import { isProxy } from "node:util/types";

import {
  parseFormationOutcomeEnvelope,
  type FormationOutcomeEnvelope,
} from "../../../core/consolidate/formation-outcome";
import {
  parseDurableMemoryWorkJob,
  type DurableMemoryWorkJob,
  type DurableMemoryWorkKind,
} from "../../../core/consolidate/state-machine";
import {
  parseRegisteredMemoryStrategy,
  type RegisteredMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import {
  prepareDerivation,
  type AtomicGraphTransition,
  type CanonicalJson,
  type DerivationVersions,
  type GraphRevision,
  type RevisionContent,
} from "../../../core/ledger";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  assertAuthoritativeLedgerAppend,
  authoritativeAppendRequestDigest,
  type AuthoritativeAppendOrigin,
  type AuthoritativeLedgerAppend,
  type NonFormationAppendReason,
} from "../stores/authoritative-ledger-repository";
import {
  normalizeDurableMemoryWorkResultJson,
  parseStagedDurableMemoryWorkResult,
  type NormalizedDurableMemoryWorkResultJson,
  type StagedDurableMemoryWorkResult,
} from "../stores/durable-memory-work-result-repository";

export const DURABLE_MEMORY_GRAPH_PLAN_VERSION = "durable-memory-graph-plan-v1" as const;
const DIGEST = /^[a-f0-9]{64}$/;
const TOKEN = /^[\x21-\x7e]{1,256}$/;

export interface DurableMemoryGraphPlanTemplate {
  readonly origin: AuthoritativeAppendOrigin;
  readonly input_revisions: readonly RevisionContent[];
  readonly placement: AtomicGraphTransition["placement"];
  readonly revisions: readonly GraphRevision[];
  readonly adjacency: AtomicGraphTransition["adjacency"];
  readonly artifacts: AtomicGraphTransition["artifacts"];
  readonly identity_authority_context: AtomicGraphTransition["identity_authority_context"] | null;
  readonly derived_identity_support: AtomicGraphTransition["derived_identity_support"] | null;
  readonly committed_revisions: AtomicGraphTransition["committed_revisions"] | null;
}

export interface DurableMemoryGraphPlan extends DurableMemoryGraphPlanTemplate {
  readonly version: typeof DURABLE_MEMORY_GRAPH_PLAN_VERSION;
  readonly plan_digest: string;
  readonly owner_account_id: string;
  readonly job_id: string;
  readonly accepted_work_digest: string;
  readonly account_epoch: number;
  readonly work_kind: DurableMemoryWorkKind;
  readonly input_frontier: string;
  readonly input_digest: string;
  readonly execution_contract_digest: string;
  readonly result_contract_version: string;
}

const fail = (code: string): never => { throw new TypeError(`durable memory graph plan ${code}`); };

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) fail(code);
  const objectValue = value as object;
  if (isProxy(objectValue) || Object.getPrototypeOf(objectValue) !== Object.prototype) fail(code);
  const actualKeys = Reflect.ownKeys(objectValue);
  if (actualKeys.some((key) => typeof key !== "string")) fail(code);
  const actual = (actualKeys as string[]).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) fail(code);
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(objectValue, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const token = (value: unknown): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail("invalid_coordinate");
  return value as string;
};

const digest = (value: unknown): string => {
  if (typeof value !== "string" || !DIGEST.test(value)) fail("invalid_coordinate");
  return value as string;
};

const reasonFor = (workKind: DurableMemoryWorkKind): NonFormationAppendReason | null => {
  if (workKind === "promotion") return "promotion";
  if (workKind === "identity_cluster") return "identity_consolidation";
  if (workKind === "predicate_batch") return "predicate_alignment";
  return null;
};

const revisionContent = (revision: GraphRevision): CanonicalJson => {
  if (revision.kind === "claim") return revision.claim as unknown as CanonicalJson;
  if (revision.kind === "entity") return revision.entity as unknown as CanonicalJson;
  if (revision.kind === "predicate") return revision.predicate as unknown as CanonicalJson;
  if (revision.kind === "predicate_assertion") return revision.assertion as unknown as CanonicalJson;
  if (revision.kind === "identity") return revision.constraint as unknown as CanonicalJson;
  if (revision.kind === "event") return revision.event as unknown as CanonicalJson;
  if (revision.kind === "evidence") return revision.evidence as unknown as CanonicalJson;
  if (revision.kind === "mention") return revision.mention as unknown as CanonicalJson;
  if (revision.kind === "identity_authorization") return revision.authorization as unknown as CanonicalJson;
  return revision.support as unknown as CanonicalJson;
};

const versionsFor = (strategy: Readonly<RegisteredMemoryStrategy>): DerivationVersions => ({
  strategy_version: strategy.coordinates.strategy_version,
  model_version: strategy.coordinates.model_version,
  prompt_version: strategy.coordinates.prompt_version,
  policy_version: strategy.coordinates.policy_version,
  code_version: strategy.coordinates.code_version,
  schema_version: strategy.coordinates.schema_version,
  tokenizer_version: strategy.coordinates.tokenizer_version,
  tool_version: strategy.coordinates.tool_version,
});

const coreForDigest = (plan: Omit<DurableMemoryGraphPlan, "plan_digest">): CanonicalJson =>
  plan as unknown as CanonicalJson;

const parseOrigin = (
  value: unknown,
  workKind: DurableMemoryWorkKind,
  ownerAccountId: string,
  inputFrontier: string,
): AuthoritativeAppendOrigin => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)) {
    fail("invalid_origin");
  }
  const kindDescriptor = Object.getOwnPropertyDescriptor(value, "kind");
  const kind = kindDescriptor && "value" in kindDescriptor && kindDescriptor.enumerable
    ? kindDescriptor.value : fail("invalid_origin");
  if (workKind === "formation") {
    const input = exactRecord(value, ["kind", "outcome"], "invalid_origin");
    if (kind !== "formation") fail("origin_work_kind_mismatch");
    const outcome = parseFormationOutcomeEnvelope(input["outcome"]);
    if (outcome.owner_account_id !== ownerAccountId || outcome.input_frontier !== inputFrontier) {
      fail("formation_coordinate_mismatch");
    }
    return Object.freeze({ kind: "formation" as const, outcome });
  }
  const input = exactRecord(value, ["kind", "reason"], "invalid_origin");
  const expectedReason = reasonFor(workKind);
  if (kind !== "non_formation" || input["reason"] !== expectedReason) {
    fail("origin_work_kind_mismatch");
  }
  return Object.freeze({ kind: "non_formation" as const, reason: expectedReason! });
};

const parsePlan = (value: unknown): Readonly<DurableMemoryGraphPlan> => {
  const normalized = normalizeDurableMemoryWorkResultJson(value);
  const input = exactRecord(normalized, [
    "version", "plan_digest", "owner_account_id", "job_id", "accepted_work_digest",
    "account_epoch", "work_kind", "input_frontier", "input_digest",
    "execution_contract_digest", "result_contract_version", "origin", "input_revisions",
    "placement", "revisions", "adjacency", "artifacts", "identity_authority_context",
    "derived_identity_support", "committed_revisions",
  ], "invalid_plan");
  if (input["version"] !== DURABLE_MEMORY_GRAPH_PLAN_VERSION) fail("invalid_plan");
  const workKind = input["work_kind"];
  if (workKind !== "formation" && workKind !== "promotion"
    && workKind !== "identity_cluster" && workKind !== "predicate_batch") fail("invalid_plan");
  if (!Number.isSafeInteger(input["account_epoch"]) || (input["account_epoch"] as number) < 0) {
    fail("invalid_coordinate");
  }
  const normalizedWorkKind = workKind as DurableMemoryWorkKind;
  const core = {
    version: DURABLE_MEMORY_GRAPH_PLAN_VERSION,
    owner_account_id: token(input["owner_account_id"]),
    job_id: token(input["job_id"]),
    accepted_work_digest: digest(input["accepted_work_digest"]),
    account_epoch: input["account_epoch"] as number,
    work_kind: normalizedWorkKind,
    input_frontier: token(input["input_frontier"]),
    input_digest: digest(input["input_digest"]),
    execution_contract_digest: digest(input["execution_contract_digest"]),
    result_contract_version: token(input["result_contract_version"]),
    origin: parseOrigin(
      input["origin"], normalizedWorkKind, input["owner_account_id"] as string, input["input_frontier"] as string,
    ),
    input_revisions: input["input_revisions"] as readonly RevisionContent[],
    placement: input["placement"] as AtomicGraphTransition["placement"],
    revisions: input["revisions"] as readonly GraphRevision[],
    adjacency: input["adjacency"] as AtomicGraphTransition["adjacency"],
    artifacts: input["artifacts"] as AtomicGraphTransition["artifacts"],
    identity_authority_context: input["identity_authority_context"] as AtomicGraphTransition["identity_authority_context"] | null,
    derived_identity_support: input["derived_identity_support"] as AtomicGraphTransition["derived_identity_support"] | null,
    committed_revisions: input["committed_revisions"] as AtomicGraphTransition["committed_revisions"] | null,
  } satisfies Omit<DurableMemoryGraphPlan, "plan_digest">;
  const planDigest = digest(input["plan_digest"]);
  if (sha256CanonicalContent(coreForDigest(core)) !== planDigest) fail("plan_digest_mismatch");
  return Object.freeze({ ...core, plan_digest: planDigest });
};

const assertMatchesJobAndStrategy = (
  plan: Readonly<DurableMemoryGraphPlan>,
  jobValue: DurableMemoryWorkJob,
  strategyValue: RegisteredMemoryStrategy,
): { job: Readonly<DurableMemoryWorkJob>; strategy: Readonly<RegisteredMemoryStrategy> } => {
  const job = parseDurableMemoryWorkJob(jobValue);
  const strategy = parseRegisteredMemoryStrategy(strategyValue);
  if (job.state !== "leased" || job.lease === null) fail("job_not_leased");
  if (plan.result_contract_version !== DURABLE_MEMORY_GRAPH_PLAN_VERSION
    || strategy.coordinates.result_contract_version !== DURABLE_MEMORY_GRAPH_PLAN_VERSION) {
    fail("unsupported_result_contract");
  }
  if (plan.owner_account_id !== job.owner_account_id || plan.job_id !== job.job_id
    || plan.accepted_work_digest !== job.accepted_work_digest
    || plan.account_epoch !== job.account_epoch || plan.work_kind !== job.work_kind
    || plan.input_frontier !== job.input_frontier || plan.input_digest !== job.input_digest
    || plan.execution_contract_digest !== job.execution_contract_digest
    || strategy.work_kind !== job.work_kind
    || strategy.execution_contract_digest !== job.execution_contract_digest
    || plan.result_contract_version !== strategy.coordinates.result_contract_version) {
    fail("job_strategy_mismatch");
  }
  if (plan.origin.kind === "formation") {
    const coordinates = plan.origin.outcome.coordinates;
    if (plan.origin.outcome.work_id !== job.job_id
      || coordinates.strategy_version !== strategy.coordinates.strategy_version
      || coordinates.model_version !== strategy.coordinates.model_version
      || coordinates.prompt_version !== strategy.coordinates.prompt_version
      || coordinates.policy_version !== strategy.coordinates.policy_version
      || coordinates.code_version !== strategy.coordinates.code_version
      || coordinates.schema_version !== strategy.coordinates.schema_version
      || coordinates.tokenizer_version !== strategy.coordinates.tokenizer_version
      || coordinates.tool_version !== strategy.coordinates.tool_version
      || coordinates.speaker_strategy_version !== strategy.coordinates.speaker_strategy_version
      || coordinates.boundary_strategy_version !== strategy.coordinates.boundary_strategy_version) {
      fail("formation_strategy_mismatch");
    }
  }
  return { job, strategy };
};

const transitionFor = (
  plan: Readonly<DurableMemoryGraphPlan>,
  strategy: Readonly<RegisteredMemoryStrategy>,
  parentCommit: string | null,
): AtomicGraphTransition => {
  if (parentCommit !== null) token(parentCommit);
  const materializationDigest = sha256CanonicalContent({
    contract_version: "durable-memory-graph-plan-materialization-v1",
    owner_account_id: plan.owner_account_id,
    job_id: plan.job_id,
    accepted_work_digest: plan.accepted_work_digest,
    plan_digest: plan.plan_digest,
    parent_commit: parentCommit,
  });
  const derivation = prepareDerivation({
    attempt_id: `attempt:memory-plan:${materializationDigest}`,
    commit_id: `commit:memory-plan:${materializationDigest}`,
    owner_account_id: plan.owner_account_id,
    parent_commit: parentCommit,
    idempotency_key: `append:memory-plan:${materializationDigest}`,
    input_revisions: plan.input_revisions,
    output_revisions: plan.revisions.map((revision) => ({
      revision_id: revision.revision_id,
      content: revisionContent(revision),
    })),
    versions: versionsFor(strategy),
    success_kind: "success",
  });
  return {
    placement: plan.placement,
    derivation,
    revisions: plan.revisions,
    adjacency: plan.adjacency,
    artifacts: plan.artifacts,
    ...(plan.identity_authority_context === null ? {} : { identity_authority_context: plan.identity_authority_context }),
    ...(plan.derived_identity_support === null ? {} : { derived_identity_support: plan.derived_identity_support }),
    ...(plan.committed_revisions === null ? {} : { committed_revisions: plan.committed_revisions }),
  };
};

const appendFor = (
  context: AuthorizedLedgerWriteContext,
  plan: Readonly<DurableMemoryGraphPlan>,
  strategy: Readonly<RegisteredMemoryStrategy>,
  parentCommit: string | null,
): AuthoritativeLedgerAppend => {
  const transition = transitionFor(plan, strategy, parentCommit);
  const request: AuthoritativeLedgerAppend = {
    append_attempt: {
      idempotency_key: transition.derivation.commit.idempotency_key,
      expected_parent_commit: parentCommit,
      request_digest: authoritativeAppendRequestDigest(transition, plan.origin),
    },
    origin: plan.origin,
    transition,
  };
  return assertAuthoritativeLedgerAppend(context, request);
};

export const createDurableMemoryGraphPlan = (
  contextValue: AuthorizedLedgerWriteContext,
  jobValue: DurableMemoryWorkJob,
  strategyValue: RegisteredMemoryStrategy,
  template: DurableMemoryGraphPlanTemplate,
): Readonly<DurableMemoryGraphPlan> => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  if (context.capability !== "memories.work.execute") fail("capability_denied");
  const job = parseDurableMemoryWorkJob(jobValue);
  const strategy = parseRegisteredMemoryStrategy(strategyValue);
  const core: Omit<DurableMemoryGraphPlan, "plan_digest"> = {
    version: DURABLE_MEMORY_GRAPH_PLAN_VERSION,
    owner_account_id: job.owner_account_id,
    job_id: job.job_id,
    accepted_work_digest: job.accepted_work_digest,
    account_epoch: job.account_epoch,
    work_kind: job.work_kind,
    input_frontier: job.input_frontier,
    input_digest: job.input_digest,
    execution_contract_digest: job.execution_contract_digest,
    result_contract_version: strategy.coordinates.result_contract_version,
    ...template,
  };
  const plan = parsePlan({ ...core, plan_digest: sha256CanonicalContent(coreForDigest(core)) });
  assertMatchesJobAndStrategy(plan, job, strategy);
  appendFor(context, plan, strategy, null);
  return plan;
};

export const materializeDurableMemoryGraphPlan = (
  contextValue: AuthorizedLedgerWriteContext,
  jobValue: DurableMemoryWorkJob,
  stagedValue: StagedDurableMemoryWorkResult,
  strategyValue: RegisteredMemoryStrategy,
  parentCommit: string | null,
): Readonly<{ kind: "ready"; result_kind: "successful"; authoritative_append: AuthoritativeLedgerAppend }> => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  if (context.capability !== "memories.work.execute") fail("capability_denied");
  const job = parseDurableMemoryWorkJob(jobValue);
  const staged = parseStagedDurableMemoryWorkResult(stagedValue, job);
  const strategy = parseRegisteredMemoryStrategy(strategyValue);
  if (staged.result_contract_version !== strategy.coordinates.result_contract_version) {
    fail("staged_result_contract_mismatch");
  }
  const plan = parsePlan(staged.normalized_result);
  assertMatchesJobAndStrategy(plan, job, strategy);
  if (plan.origin.kind === "formation" && plan.origin.outcome.response_digest !== staged.response_digest) {
    fail("formation_response_mismatch");
  }
  return Object.freeze({
    kind: "ready" as const,
    result_kind: "successful" as const,
    authoritative_append: appendFor(context, plan, strategy, parentCommit),
  });
};

export const normalizeDurableMemoryGraphPlan = (
  value: unknown,
): NormalizedDurableMemoryWorkResultJson =>
  parsePlan(value) as unknown as NormalizedDurableMemoryWorkResultJson;
