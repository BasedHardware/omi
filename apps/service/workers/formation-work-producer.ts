import type { DurableMemoryWorkErrorCode, DurableMemoryWorkJob } from "../../../core/consolidate/state-machine";
import { isProxy } from "node:util/types";
import {
  MEMORY_FORMATION_OUTCOME_CONTRACT_VERSION,
  formationCandidateManifestDigest,
  parseFormationOutcomeEnvelope,
  type PlacementOutcome,
} from "../../../core/consolidate/formation-outcome";
import { parseRegisteredMemoryStrategy, type RegisteredMemoryStrategy } from "../../../core/consolidate/strategy-assignment";
import {
  extractGrounded,
  GROUNDED_EXTRACTION_PROMPT_VERSION,
  GROUNDED_MENTION_STRATEGY_VERSION,
  materializeGroundedExtractionOutcomes,
  materializeGroundedMentions,
  materializeGroundedProvisional,
} from "../../../core/extract/grounded";
import type { IdentityAuthorityContext } from "../../../core/resolve/identity-authority";
import type { WritingContext } from "../../../core/retrieve/writing-context";
import { persistValidTime, type ReferenceClock } from "../../../core/retrieve/temporal";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import type {
  Entity, Evidence, IdentityAuthorization, L1Event,
} from "../../../core/schema";
import type { CanonicalJson } from "../../../core/ledger";
import { parseDurableMemoryWorkJob } from "../../../core/consolidate/state-machine";
import type { AuthorizedLedgerWriteContext } from "../auth/authorized-context";
import {
  assertAuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  durableMemoryWorkInputManifestDigest,
  type DurableMemoryWorkInputManifestEntry,
} from "../stores/durable-memory-work-repository";
import type { StagedDurableMemoryWorkResult } from "../stores/durable-memory-work-result-repository";
import type { ModelPort } from "../../../drivers/model/port";
import {
  planSessionStmToLtmTransition,
  sessionStmLtmPlanningInputRevisions,
  type SessionStmLtmPlanningRequest,
} from "../../../drivers/model/stm-ltm-transition";
import {
  DURABLE_MEMORY_GRAPH_PLAN_VERSION,
  createDurableMemoryGraphPlan,
  materializeDurableMemoryGraphPlan,
} from "./durable-memory-graph-plan";
import type {
  DurableMemoryWorkMaterializeOutcome,
  DurableMemoryWorkProduceOutcome,
} from "./durable-memory-work-runner";
import { normalizeDurableMemoryWorkResultJson } from "../stores/durable-memory-work-result-repository";

export const FORMATION_INPUT_SNAPSHOT_VERSION = "formation-input-snapshot-v1" as const;
const TOKEN = /^[\x21-\x7e]{1,256}$/;

export interface FormationInputSnapshot {
  readonly version: typeof FORMATION_INPUT_SNAPSHOT_VERSION;
  readonly owner_account_id: string;
  readonly work_id: string;
  readonly session_id: string;
  readonly input_frontier: string;
  readonly graph_frontier: number;
  readonly observed_at: string;
  readonly source_language: string;
  readonly account_timezone: string;
  readonly reference_clock: Readonly<Required<ReferenceClock>>;
  readonly context: Readonly<WritingContext>;
  readonly predicate_registry: readonly string[];
  readonly entity_registry: readonly string[];
  readonly target_evidence_ids: readonly string[];
  readonly evidence: readonly Evidence[];
  readonly events: readonly L1Event[];
  readonly entities: readonly Entity[];
  readonly identity_authorizations: readonly IdentityAuthorization[];
  readonly identity_authority_context: Readonly<IdentityAuthorityContext> | null;
}

export type FormationInputLoadOutcome =
  | Readonly<{ kind: "found"; snapshot: FormationInputSnapshot }>
  | Readonly<{ kind: "not_found" }>
  | Readonly<{ kind: "failed"; error_code: DurableMemoryWorkErrorCode }>;

export type FormationParentLoadOutcome =
  | Readonly<{ kind: "found"; parent_commit: string | null }>
  | Readonly<{ kind: "failed"; error_code: DurableMemoryWorkErrorCode }>;

export interface FormationWorkAdapterDependencies {
  readonly load_input: (
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
  ) => Promise<FormationInputLoadOutcome>;
  readonly resolve_model: (
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
    strategy: Readonly<RegisteredMemoryStrategy>,
  ) => Promise<ModelPort | null>;
  readonly load_current_parent: (
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
  ) => Promise<FormationParentLoadOutcome>;
  readonly classify_model_error?: (error: unknown) => DurableMemoryWorkErrorCode;
}

export interface FormationWorkAdapter {
  produce(
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
    strategy: Readonly<RegisteredMemoryStrategy>,
  ): Promise<DurableMemoryWorkProduceOutcome>;
  materialize(
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
    staged: StagedDurableMemoryWorkResult,
    strategy: Readonly<RegisteredMemoryStrategy>,
  ): Promise<DurableMemoryWorkMaterializeOutcome>;
}

const fail = (code: string): never => { throw new TypeError(`formation work producer ${code}`); };
const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value as string;
};

/** Graph planning legitimately references the same immutable claim from its
 * derivation input and revision output. Durable JSON has no reference identity,
 * so detach each occurrence while still rejecting cycles and exotic objects. */
const detachPlainTree = <Value>(value: Value): Value => {
  const ancestors = new WeakSet<object>();
  let nodes = 0;
  const visit = (node: unknown, depth: number): unknown => {
    nodes += 1;
    if (nodes > 100_000 || depth > 64) fail("result_too_large");
    if (node === null || typeof node === "string" || typeof node === "boolean") return node;
    if (typeof node === "number") {
      if (!Number.isFinite(node)) fail("invalid_result");
      return node;
    }
    if (typeof node !== "object" || node === null) fail("invalid_result");
    const objectNode = node as object;
    if (isProxy(objectNode) || ancestors.has(objectNode)) fail("invalid_result");
    const array = Array.isArray(objectNode);
    const prototype = Object.getPrototypeOf(objectNode);
    if (array ? prototype !== Array.prototype : prototype !== Object.prototype && prototype !== null) {
      fail("invalid_result");
    }
    ancestors.add(objectNode);
    const output: unknown[] | Record<string, unknown> = array ? [] : {};
    const keys = Reflect.ownKeys(objectNode);
    if (keys.some((key) => typeof key !== "string")) fail("invalid_result");
    for (const key of keys as string[]) {
      if (array && key === "length") continue;
      const descriptor = Object.getOwnPropertyDescriptor(objectNode, key);
      if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("invalid_result");
      const copied = visit((descriptor as PropertyDescriptor & { value: unknown }).value, depth + 1);
      if (array) (output as unknown[])[Number(key)] = copied;
      else (output as Record<string, unknown>)[key] = copied;
    }
    ancestors.delete(objectNode);
    return output;
  };
  return visit(value, 0) as Value;
};

const exactRoot = (value: unknown): Record<string, unknown> => {
  const normalized = normalizeDurableMemoryWorkResultJson(value);
  const expected = [
    "version", "owner_account_id", "work_id", "session_id", "input_frontier",
    "graph_frontier", "observed_at", "source_language", "account_timezone",
    "reference_clock", "context", "predicate_registry", "entity_registry",
    "target_evidence_ids", "evidence", "events", "entities",
    "identity_authorizations", "identity_authority_context",
  ].sort();
  const actual = Object.keys(normalized).sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    fail("invalid_input_snapshot");
  }
  return normalized;
};

const stringArray = (value: unknown, code: string, allowEmpty = true): readonly string[] => {
  if (!Array.isArray(value) || (!allowEmpty && value.length === 0)) fail(code);
  const output = (value as unknown[]).map((item) => token(item, code));
  if (new Set(output).size !== output.length) fail(code);
  return Object.freeze(output);
};

export const parseFormationInputSnapshot = (value: unknown): Readonly<FormationInputSnapshot> => {
  const input = exactRoot(value);
  if (input["version"] !== FORMATION_INPUT_SNAPSHOT_VERSION
    || !Number.isSafeInteger(input["graph_frontier"])
    || (input["graph_frontier"] as number) < 0) fail("invalid_input_snapshot");
  const reference = input["reference_clock"] as Record<string, unknown>;
  if (!reference || typeof reference !== "object" || Array.isArray(reference)
    || Object.keys(reference).sort().join(",") !== "capture_at,query_at") fail("invalid_input_snapshot");
  const snapshot = {
    version: FORMATION_INPUT_SNAPSHOT_VERSION,
    owner_account_id: token(input["owner_account_id"], "invalid_input_snapshot"),
    work_id: token(input["work_id"], "invalid_input_snapshot"),
    session_id: token(input["session_id"], "invalid_input_snapshot"),
    input_frontier: token(input["input_frontier"], "invalid_input_snapshot"),
    graph_frontier: input["graph_frontier"] as number,
    observed_at: token(input["observed_at"], "invalid_input_snapshot"),
    source_language: token(input["source_language"], "invalid_input_snapshot"),
    account_timezone: token(input["account_timezone"], "invalid_input_snapshot"),
    reference_clock: Object.freeze({
      query_at: token(reference["query_at"], "invalid_input_snapshot"),
      capture_at: token(reference["capture_at"], "invalid_input_snapshot"),
    }),
    context: input["context"] as unknown as Readonly<WritingContext>,
    predicate_registry: stringArray(input["predicate_registry"], "invalid_input_snapshot"),
    entity_registry: stringArray(input["entity_registry"], "invalid_input_snapshot"),
    target_evidence_ids: stringArray(input["target_evidence_ids"], "invalid_input_snapshot", false),
    evidence: input["evidence"] as unknown as readonly Evidence[],
    events: input["events"] as unknown as readonly L1Event[],
    entities: input["entities"] as unknown as readonly Entity[],
    identity_authorizations: input["identity_authorizations"] as unknown as readonly IdentityAuthorization[],
    identity_authority_context: input["identity_authority_context"] as unknown as Readonly<IdentityAuthorityContext> | null,
  } satisfies FormationInputSnapshot;
  if (!Array.isArray(snapshot.evidence) || !Array.isArray(snapshot.events)
    || !Array.isArray(snapshot.entities) || !Array.isArray(snapshot.identity_authorizations)
    || snapshot.context === null || typeof snapshot.context !== "object") fail("invalid_input_snapshot");
  // Validate the timezone even when a response contains no temporal claim.
  try { new Intl.DateTimeFormat("en-US", { timeZone: snapshot.account_timezone }); }
  catch { return fail("invalid_input_snapshot"); }
  return Object.freeze(snapshot);
};

export const formationWorkInputManifest = (
  snapshotValue: FormationInputSnapshot,
): readonly Readonly<DurableMemoryWorkInputManifestEntry>[] => {
  const snapshot = parseFormationInputSnapshot(snapshotValue);
  const entries: DurableMemoryWorkInputManifestEntry[] = [
    {
      input_kind: "graph_frontier",
      input_ref: snapshot.input_frontier,
      input_digest: sha256CanonicalContent({
        contract_version: FORMATION_INPUT_SNAPSHOT_VERSION,
        owner_account_id: snapshot.owner_account_id,
        work_id: snapshot.work_id,
        session_id: snapshot.session_id,
        input_frontier: snapshot.input_frontier,
        graph_frontier: snapshot.graph_frontier,
        observed_at: snapshot.observed_at,
        source_language: snapshot.source_language,
        account_timezone: snapshot.account_timezone,
        reference_clock: snapshot.reference_clock,
        context: snapshot.context,
        predicate_registry: snapshot.predicate_registry,
        entity_registry: snapshot.entity_registry,
        target_evidence_ids: snapshot.target_evidence_ids,
        entities: snapshot.entities,
        identity_authorizations: snapshot.identity_authorizations,
        identity_authority_context: snapshot.identity_authority_context,
      }),
    },
    ...snapshot.events.map((event) => ({
      input_kind: "event_revision" as const,
      input_ref: event.event_revision_id,
      input_digest: sha256CanonicalContent(event),
    })),
    ...snapshot.evidence.map((evidence) => ({
      input_kind: "evidence_revision" as const,
      input_ref: `evidence-revision:${evidence.evidence_id}`,
      input_digest: sha256CanonicalContent(evidence),
    })),
  ];
  return Object.freeze(entries);
};

export const assertFormationInputSnapshotMatchesJob = (
  snapshot: Readonly<FormationInputSnapshot>,
  job: Readonly<DurableMemoryWorkJob>,
): void => {
  if (snapshot.owner_account_id !== job.owner_account_id || snapshot.work_id !== job.job_id
    || snapshot.input_frontier !== job.input_frontier
    || snapshot.context.frontier?.graph_head !== job.input_frontier
    || String(snapshot.graph_frontier) !== job.input_frontier) fail("input_job_mismatch");
  const evidenceIds = new Set(snapshot.evidence.map((item) => item.evidence_id));
  const eventIds = new Set(snapshot.events.map((item) => item.event_revision_id));
  if (evidenceIds.size !== snapshot.evidence.length || eventIds.size !== snapshot.events.length
    || snapshot.target_evidence_ids.some((id) => !evidenceIds.has(id))
    || snapshot.events.some((item) => item.owner_account_id !== job.owner_account_id)
    || snapshot.evidence.some((item) => !eventIds.has(item.event_revision_id))
    || snapshot.entities.some((item) => item.owner_account_id !== job.owner_account_id)
    || snapshot.identity_authorizations.some((item) => item.owner_account_id !== job.owner_account_id)) {
    fail("input_job_mismatch");
  }
  if (durableMemoryWorkInputManifestDigest(formationWorkInputManifest(snapshot)) !== job.input_digest) {
    fail("input_digest_mismatch");
  }
};

const placementOutcomes = (
  request: SessionStmLtmPlanningRequest,
  transition: Awaited<ReturnType<typeof planSessionStmToLtmTransition>>,
): readonly PlacementOutcome[] => transition.placement.results.map((result) => {
  if (result.disposition === "admit") {
    const canonicalId = transition.placement.allocations[result.input_provisional_revision_id];
    const canonical = transition.revisions.find((revision) => revision.kind === "claim"
      && revision.revision_id === canonicalId && revision.placement_status === "canonical");
    if (!canonicalId || !canonical || canonical.kind !== "claim" || canonical.claim.lifecycle !== "canonical") {
      return fail("invalid_placement_plan");
    }
    return Object.freeze({
      kind: "admitted" as const,
      input_provisional_revision_id: result.input_provisional_revision_id,
      canonical_claim_revision_id: canonicalId,
      boundary_decision: "accept_ltm" as const,
      scope_locality: canonical.claim.scope.locality,
    });
  }
  if (result.disposition !== "defer_review") fail("invalid_placement_plan");
  if (!request.provisionals.some((claim) => claim.claim_revision_id === result.input_provisional_revision_id)) {
    fail("invalid_placement_plan");
  }
  return Object.freeze({
    kind: "abstained" as const,
    input_provisional_revision_id: result.input_provisional_revision_id,
    boundary_decision: "abstain" as const,
    reason_code: "placement_deferred",
    reconsideration_trigger: result.re_resolution_trigger ?? null,
  });
});

const strategyVersions = (strategy: Readonly<RegisteredMemoryStrategy>) => ({
  strategy_version: strategy.coordinates.strategy_version,
  model_version: strategy.coordinates.model_version,
  prompt_version: strategy.coordinates.prompt_version,
  policy_version: strategy.coordinates.policy_version,
  code_version: strategy.coordinates.code_version,
  schema_version: strategy.coordinates.schema_version,
  tokenizer_version: strategy.coordinates.tokenizer_version,
  tool_version: strategy.coordinates.tool_version,
});

const failed = (error_code: DurableMemoryWorkErrorCode): DurableMemoryWorkProduceOutcome =>
  Object.freeze({ kind: "failed" as const, error_code });

export const defineFormationWorkAdapter = (
  dependencies: FormationWorkAdapterDependencies,
): FormationWorkAdapter => Object.freeze({
  async produce(
    contextValue: AuthorizedLedgerWriteContext,
    jobValue: Readonly<DurableMemoryWorkJob>,
    strategyValue: Readonly<RegisteredMemoryStrategy>,
  ) {
    let context: AuthorizedLedgerWriteContext;
    let job: Readonly<DurableMemoryWorkJob>;
    let strategy: Readonly<RegisteredMemoryStrategy>;
    try {
      context = assertAuthorizedLedgerWriteContext(contextValue);
      job = parseDurableMemoryWorkJob(jobValue);
      strategy = parseRegisteredMemoryStrategy(strategyValue);
      if (context.capability !== "memories.work.execute" || job.work_kind !== "formation"
        || job.state !== "leased" || strategy.work_kind !== "formation"
        || strategy.execution_contract_digest !== job.execution_contract_digest
        || strategy.coordinates.result_contract_version !== DURABLE_MEMORY_GRAPH_PLAN_VERSION
        || strategy.coordinates.prompt_version !== GROUNDED_EXTRACTION_PROMPT_VERSION
        || strategy.coordinates.speaker_strategy_version !== GROUNDED_MENTION_STRATEGY_VERSION
        || (strategy.coordinates.boundary_strategy_version !== "v4"
          && strategy.coordinates.boundary_strategy_version !== "v5")) {
        return failed("dependency_unavailable");
      }
    } catch {
      return failed("dependency_unavailable");
    }
    let loaded: FormationInputLoadOutcome;
    let snapshot: Readonly<FormationInputSnapshot>;
    let model: ModelPort | null;
    try {
      loaded = await dependencies.load_input(context, job);
      if (loaded.kind === "failed") return failed(loaded.error_code);
      if (loaded.kind !== "found") return failed("dependency_unavailable");
      snapshot = parseFormationInputSnapshot(loaded.snapshot);
      assertFormationInputSnapshotMatchesJob(snapshot, job);
    } catch {
      return failed("dependency_unavailable");
    }
    try {
      model = await dependencies.resolve_model(context, job, strategy);
      if (model === null) return failed("dependency_unavailable");
    } catch {
      return failed("dependency_unavailable");
    }
    try {
      const extraction = await extractGrounded(model, {
        context: snapshot.context,
        predicate_registry: snapshot.predicate_registry,
        entity_registry: snapshot.entity_registry,
        evidence: snapshot.evidence,
        target_evidence_ids: snapshot.target_evidence_ids,
        version: strategy.coordinates.prompt_version,
      });
      const provisionalPairs = extraction.claims.map((emission, claimIndex) => ({
        candidate_ref: emission.candidate_ref,
        claim: materializeGroundedProvisional({
          owner_account_id: job.owner_account_id,
          session_id: snapshot.session_id,
          work_id: job.job_id,
          observed_at: snapshot.observed_at,
          source_language: snapshot.source_language,
          context: snapshot.context,
          claim_index: claimIndex,
          emission,
          evidence: snapshot.evidence,
        }),
      }));
      const mentions = provisionalPairs.flatMap(({ claim }, claimIndex) =>
        materializeGroundedMentions({
          owner_account_id: job.owner_account_id,
          session_id: snapshot.session_id,
          work_id: job.job_id,
          claim,
          claim_index: claimIndex,
          mentions: extraction.mentions,
        }));
      const validTimes = Object.fromEntries(provisionalPairs.map(({ claim }, index) => [
        claim.claim_revision_id,
        persistValidTime(
          extraction.claims[index]!.temporal_expression,
          snapshot.reference_clock,
          snapshot.account_timezone,
        ),
      ]));
      const boundaryVersion = strategy.coordinates.boundary_strategy_version as "v4" | "v5";
      const planning: SessionStmLtmPlanningRequest = {
        model,
        session_id: snapshot.session_id,
        formation_work_id: job.job_id,
        owner_account_id: job.owner_account_id,
        graph_frontier: snapshot.graph_frontier,
        provisionals: provisionalPairs.map((item) => item.claim),
        mentions,
        entities: snapshot.entities,
        evidence: snapshot.evidence,
        events: snapshot.events,
        valid_times: validTimes,
        parent_commit: null,
        boundary_version: boundaryVersion,
        versions: strategyVersions(strategy),
        identity_authorizations: snapshot.identity_authorizations,
        ...(snapshot.identity_authority_context === null
          ? {} : { identity_authority_context: snapshot.identity_authority_context }),
      };
      const transition = await planSessionStmToLtmTransition(planning);
      const extractionOutcomes = materializeGroundedExtractionOutcomes({
        extraction,
        provisionals: provisionalPairs,
      });
      const outcome = parseFormationOutcomeEnvelope({
        contract_version: MEMORY_FORMATION_OUTCOME_CONTRACT_VERSION,
        owner_account_id: job.owner_account_id,
        work_id: job.job_id,
        input_frontier: job.input_frontier,
        response_digest: extraction.response_digest,
        candidate_count: extractionOutcomes.length,
        candidate_manifest_digest: formationCandidateManifestDigest(extractionOutcomes.length),
        coordinates: {
          contract_version: MEMORY_FORMATION_OUTCOME_CONTRACT_VERSION,
          strategy_version: strategy.coordinates.strategy_version,
          model_version: strategy.coordinates.model_version,
          prompt_version: strategy.coordinates.prompt_version,
          policy_version: strategy.coordinates.policy_version,
          code_version: strategy.coordinates.code_version,
          schema_version: strategy.coordinates.schema_version,
          tokenizer_version: strategy.coordinates.tokenizer_version,
          tool_version: strategy.coordinates.tool_version,
          speaker_strategy_version: strategy.coordinates.speaker_strategy_version,
          boundary_strategy_version: strategy.coordinates.boundary_strategy_version,
        },
        extraction_outcomes: extractionOutcomes,
        placement_outcomes: placementOutcomes(planning, transition),
      });
      const plan = createDurableMemoryGraphPlan(context, job, strategy, detachPlainTree({
        origin: { kind: "formation", outcome },
        input_revisions: sessionStmLtmPlanningInputRevisions(planning),
        placement: transition.placement,
        revisions: transition.revisions,
        adjacency: transition.adjacency,
        artifacts: transition.artifacts,
        identity_authority_context: transition.identity_authority_context ?? null,
        derived_identity_support: transition.derived_identity_support ?? null,
        committed_revisions: transition.committed_revisions ?? null,
      }));
      return Object.freeze({
        kind: "produced" as const,
        result_contract_version: DURABLE_MEMORY_GRAPH_PLAN_VERSION,
        response_digest: extraction.response_digest,
        normalized_result: plan as unknown as Readonly<Record<string, CanonicalJson>>,
      });
    } catch (error) {
      const classified = dependencies.classify_model_error?.(error) ?? "model_response_invalid";
      return failed(classified);
    }
  },

  async materialize(
    context: AuthorizedLedgerWriteContext,
    job: Readonly<DurableMemoryWorkJob>,
    staged: StagedDurableMemoryWorkResult,
    strategy: Readonly<RegisteredMemoryStrategy>,
  ) {
    let loaded: FormationParentLoadOutcome;
    try { loaded = await dependencies.load_current_parent(context, job); }
    catch { return Object.freeze({ kind: "failed" as const, error_code: "dependency_unavailable" }); }
    if (loaded.kind === "failed") return Object.freeze({ kind: "failed" as const, error_code: loaded.error_code });
    try {
      return materializeDurableMemoryGraphPlan(context, job, staged, strategy, loaded.parent_commit);
    } catch {
      return Object.freeze({ kind: "failed" as const, error_code: "model_response_invalid" });
    }
  },
});
