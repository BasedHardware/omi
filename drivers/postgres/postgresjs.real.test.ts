import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { randomUUID } from "node:crypto";
import postgres, { type Sql } from "postgres";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import {
  emitDurableMemoryWorkBacklogTelemetry,
} from "../../apps/service/observability/durable-memory-work-backlog";
import { authoritativeAppendRequestDigest, type AuthoritativeLedgerAppend } from "../../apps/service/stores/authoritative-ledger-repository";
import {
  productProjectionWriteRequestDigest,
  type ProductProjectionPayload,
  type ProductProjectionWriteBody,
} from "../../apps/service/stores/product-projection-repository";
import { defineMemoryEvaluationEvidenceSource } from "../../apps/service/stores/memory-evaluation-evidence-source";
import { materializeFinalizedMemoryReadGrounding } from "../../apps/service/stores/memory-read-grounding-repository";
import {
  materializeMemoryEvaluationResult,
  memoryEvaluationStageRequestDigest,
  pairMemoryEvaluationResults,
  type MemoryEvaluationRole,
  type MemoryEvaluationStageRequest,
} from "../../apps/service/stores/memory-shadow-result-repository";
import {
  durableMemoryWorkAcceptanceRequestDigest,
  durableMemoryWorkInputManifestDigest,
  type DurableMemoryWorkAcceptanceRequest,
  type DurableMemoryWorkInputManifestEntry,
} from "../../apps/service/stores/durable-memory-work-repository";
import {
  durableMemoryWorkNormalizedResultDigest,
  durableMemoryWorkResultStageRequestDigest,
  type DurableMemoryWorkResultStageBody,
} from "../../apps/service/stores/durable-memory-work-result-repository";
import {
  durableMemoryWorkSuccessRequestDigest,
  type DurableMemoryWorkSuccessBody,
} from "../../apps/service/stores/durable-memory-work-success-repository";
import {
  formationWorkInputStageRequestDigest,
} from "../../apps/service/workers/formation-work-input-repository";
import { DURABLE_MEMORY_GRAPH_PLAN_VERSION } from "../../apps/service/workers/durable-memory-graph-plan";
import { buildMemoryReadEvaluationResult } from "../../apps/service/workers/memory-read-evaluation-result";
import {
  PREDICATE_BATCH_SCHEDULING_SNAPSHOT_VERSION,
  definePredicateBatchWorkScheduler,
} from "../../apps/service/workers/predicate-batch-work-scheduler";
import {
  definePredicateBatchWorkInputRepository,
  materializeStagedPredicateBatchWorkInput,
} from "../../apps/service/workers/predicate-batch-work-input-repository";
import {
  FORMATION_INPUT_SNAPSHOT_VERSION,
  formationWorkInputManifest,
  parseFormationInputSnapshot,
  type FormationInputSnapshot,
} from "../../apps/service/workers/formation-work-producer";
import {
  formationCandidateManifestDigest,
  parseFormationOutcomeEnvelope,
} from "../../core/consolidate/formation-outcome";
import { predicateIdForName, predicateRevisionForObservation } from "../../core/consolidate/predicate-identity";
import {
  DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
  registerDurableMemoryWorkExecutionPolicy,
} from "../../core/consolidate/execution-policy";
import {
  MEMORY_STRATEGY_VERSION,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
} from "../../core/consolidate/strategy-assignment";
import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  type AcceptedDurableMemoryWork,
} from "../../core/consolidate/state-machine";
import {
  GROUNDED_EXTRACTION_PROMPT_VERSION,
  GROUNDED_MENTION_STRATEGY_VERSION,
} from "../../core/extract/grounded";
import { prepareDerivation, type AtomicGraphTransition } from "../../core/ledger";
import {
  createOperationalTelemetryEmitter,
  type OperationalTelemetryEvent,
} from "../../core/observability/operational-telemetry";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import { buildContentSafeRecallTrace } from "../../core/retrieve/recall-integrity";
import {
  birthProductProposition,
  buildProductProjectionRevision,
} from "../../core/retrieve/product-projection";
import { parseSynthesizedPageJson } from "@omi-core/ratified-contracts/projections/synthesized";
import { produceQaRenders } from "../../apps/qa/renders";
import type { IdentityAuthorization, IdentityConstraint, Predicate, ProvisionalClaim } from "../../core/schema";
import {
  createPostgresAuthoritativeLedgerRepository,
  createPostgresSuccessfulEmptyLedgerRepository,
} from "./authoritative-ledger-repository";
import { createPostgresAuthoritativeGraphSnapshotRepository } from "./authoritative-graph-snapshot";
import type { CheckedOutPostgresConnection, PostgresTransactionPool, SqlStatement } from "./connection";
import { createPostgresDurableMemoryWorkAcceptanceRepository } from "./durable-memory-work-acceptance";
import { createPostgresDurableMemoryWorkBacklogSource } from "./durable-memory-work-backlog";
import { createPostgresDurableMemoryWorkExecutionRepository } from "./durable-memory-work-execution";
import { createPostgresDurableMemoryWorkResultRepository } from "./durable-memory-work-result";
import { createPostgresDurableMemoryWorkSuccessRepository } from "./durable-memory-work-success";
import { createPostgresFormationWorkInputRepository } from "./formation-work-input";
import { createPostgresFormationOneShotRuntime } from "./formation-one-shot-runtime";
import {
  createPostgresFirebaseAuthorizedGraphSnapshotRuntime,
  projectFirebaseAuthorizedGraphSnapshotLoad,
} from "./firebase-authorized-graph-snapshot-runtime";
import { createPostgresFirebaseAuthorizedMemoryReadRuntime } from
  "./firebase-authorized-memory-read-runtime";
import { createPostgresFirebaseAuthorizedLedgerRuntime } from "./firebase-authorized-ledger-runtime";
import { createPostgresPredicateBatchWorkInputRepository } from "./predicate-batch-work-input";
import { createPostgresPredicateBatchOneShotRuntime } from "./predicate-batch-one-shot-runtime";
import { createPostgresProductProjectionWriteRepository } from "./product-projection-repository";
import {
  createPostgresMemoryReadGroundingRepository,
  createPostgresMemoryShadowResultRepository,
} from "./memory-experiment-repository";
import {
  createPostgresMemoryQueryEvaluationGraphSource,
  createPostgresMemoryQueryEvaluationInputRepository,
} from "./memory-query-evaluation-source";
import { createPostgresMemoryQueryEvaluationOneShotRuntime } from
  "./memory-query-evaluation-one-shot-runtime";
import { POSTGRES_MIGRATIONS } from "./migrations/manifest";
import { runPostgresMigrations } from "./migrations/runner";
import { createPostgresJsTransactionPool, type CloseablePostgresTransactionPool } from "./postgresjs";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";
import { SqliteLedger } from "../sqlite";
import { DeterministicFakeModel, type ModelInvokeRequest } from "../model/port";

const explicitTestUrl = process.env["OMI_TEST_POSTGRES_URL"];
const realTest = explicitTestUrl ? describe : describe.skip;

const productRequest = <Body extends ProductProjectionWriteBody>(
  body: Body,
): Body & { request_digest: string } => ({
  ...body,
  request_digest: productProjectionWriteRequestDigest(body),
});

const nonemptyAppend = (
  accountId: string,
  suffix: string,
  parentCommit: string | null,
): AuthoritativeLedgerAppend => {
  const event = {
    event_id: `event:${suffix}`, event_revision_id: `event:${suffix}:r1`,
    owner_account_id: accountId, capture_session_id: `session:${suffix}`,
    stream_id: `stream:${suffix}`, event_kind: "transcript",
    payload_schema_ref: "schema:event:v1", schema_version: "schema:v1",
    payload: { redacted: true }, event_time: "2026-08-11T20:00:00Z",
    ingest_time: null, source_sequence: 1,
    evidence_addressable_refs: [`evidence:${suffix}`], source_trust: "owner_attested",
    policy_labels: [], canonical_redacted_hash: "5".repeat(64),
  };
  const evidence = {
    evidence_id: `evidence:${suffix}`, event_revision_id: event.event_revision_id,
    source_unit_ref: `unit:${suffix}`, range: { start: 0, end: 4 }, excerpt: "test",
    source_identity_ref: {
      namespace_instance_ref: `namespace:${suffix}`, local_key: `speaker:${suffix}`,
      producer: { producer_ref: null, contract_ref: null },
      asserted_identity: { domain: null, scope_ref: null },
    },
    speaker_rendering: null, source_local_mention_ref: null, state: "active" as const,
    source_trust: "owner_attested", policy_labels: [],
    source_independence_key: `root:${suffix}`,
  };
  const claim: ProvisionalClaim = {
    claim_lineage_id: `lineage:${suffix}`, claim_revision_id: `claim:${suffix}`,
    owner_account_id: accountId, predicate: "noted",
    arguments: [{
      slot_id: "subject", role: "subject",
      value: { kind: "source_local_ref", ref: `speaker:${suffix}` },
    }],
    temporal_scope: {
      observed_at: "2026-08-11T20:00:00Z", precision: "instant",
      valid_time: {
        typed_expression: {
          kind: "absolute", granularity: "instant", value: "2026-08-11T20:00:00Z",
        },
        resolved_interval: {
          kind: "instant", start: "2026-08-11T20:00:00Z",
          end: "2026-08-11T20:00:00Z", timezone: "UTC", granularity: "instant",
        },
        derivation: { resolver_version: "qualification:v1", timezone: "UTC" },
      },
    },
    evidence_refs: [evidence.evidence_id], policy_labels: [], source_language: "en",
    scope: { locality: "source_local", scope_ref: `speaker:${suffix}` },
    lifecycle: "provisional", ambiguity_markers: ["source_local"], context_packet: null,
  };
  const revisions: AtomicGraphTransition["revisions"] = [
    { kind: "evidence", revision_id: `evidence:${suffix}:r1`, evidence },
    { kind: "claim", revision_id: claim.claim_revision_id, claim, placement_status: "provisional_abstained" },
    { kind: "event", revision_id: event.event_revision_id, event },
  ];
  const transition: AtomicGraphTransition = {
    placement: {
      offline_experiment: true, allocations: {},
      results: [{
        input_provisional_revision_id: claim.claim_revision_id,
        disposition: "defer_review", operation: null,
        re_resolution_trigger: "new_identity_evidence",
      }],
    },
    derivation: prepareDerivation({
      attempt_id: `attempt:graph:${suffix}`, commit_id: `commit:graph:${suffix}`,
      owner_account_id: accountId, parent_commit: parentCommit,
      idempotency_key: `append:graph:${suffix}`, input_revisions: [],
      output_revisions: revisions.map((revision) => ({
        revision_id: revision.revision_id,
        content: revision.kind === "event" ? revision.event
          : revision.kind === "evidence" ? revision.evidence
            : revision.kind === "claim" ? revision.claim : {},
      })),
      versions: {
        strategy_version: "qualification-graph-v1", model_version: "none",
        prompt_version: "none", policy_version: "qualification-v1",
        code_version: "qualification-v1", schema_version: "qualification-v1",
        tokenizer_version: "none", tool_version: "qualification-v1",
      },
      success_kind: "success",
    }),
    revisions, adjacency: [],
    artifacts: [{
      artifact_id: `artifact:${suffix}`, kind: "abstention_set",
      provisional_revision_id: claim.claim_revision_id,
      canonical_claim_revision_id: null, margin: "low", risk_markers: ["low_margin"],
      unit_boundary_decision: "abstain", scope_locality: null,
    }],
  };
  const origin = { kind: "non_formation" as const, reason: "repair" as const };
  return {
    append_attempt: {
      idempotency_key: transition.derivation.commit.idempotency_key,
      expected_parent_commit: parentCommit,
      request_digest: authoritativeAppendRequestDigest(transition, origin),
    },
    origin, transition,
  };
};

const formationAppend = (
  accountId: string,
  suffix: string,
  parentCommit: string | null,
): AuthoritativeLedgerAppend => {
  const base = nonemptyAppend(accountId, suffix, parentCommit);
  const provisional = base.transition.revisions.find((revision) => revision.kind === "claim");
  const evidence = base.transition.revisions.find((revision) => revision.kind === "evidence");
  if (!provisional || provisional.kind !== "claim"
    || !evidence || evidence.kind !== "evidence") throw new Error("invalid formation fixture");
  const transition: AtomicGraphTransition = {
    ...base.transition,
    derivation: prepareDerivation({
      attempt_id: base.transition.derivation.commit.attempt_id,
      commit_id: base.transition.derivation.commit.commit_id,
      owner_account_id: accountId,
      parent_commit: parentCommit,
      idempotency_key: base.transition.derivation.commit.idempotency_key,
      input_revisions: [{
        revision_id: `formation-input:${suffix}`,
        content: { input_frontier: `frontier:${suffix}` },
      }],
      output_revisions: base.transition.revisions.map((revision) => ({
        revision_id: revision.revision_id,
        content: revision.kind === "event" ? revision.event
          : revision.kind === "evidence" ? revision.evidence
            : revision.kind === "claim" ? revision.claim : {},
      })),
      versions: base.transition.derivation.commit.versions,
      success_kind: "success",
    }),
  };
  const origin = {
    kind: "formation" as const,
    outcome: {
      contract_version: "memory-formation-outcome-v2" as const,
      owner_account_id: accountId,
      work_id: `work:${suffix}`,
      input_frontier: `frontier:${suffix}`,
      response_digest: "6".repeat(64),
      candidate_count: 1,
      candidate_manifest_digest: formationCandidateManifestDigest(1),
      coordinates: {
        contract_version: "memory-formation-outcome-v2" as const,
        strategy_version: "qualification-formation-v1",
        model_version: "none", prompt_version: "none",
        policy_version: "qualification-v1", code_version: "qualification-v1",
        schema_version: "qualification-v1", tokenizer_version: "none",
        tool_version: "qualification-v1", speaker_strategy_version: "none",
        boundary_strategy_version: "qualification-v1",
      },
      extraction_outcomes: [{
        kind: "accepted" as const, candidate_ref: "candidate:1",
        claim_revision_id: provisional.revision_id,
        evidence_ids: [evidence.evidence.evidence_id], repair_codes: [],
      }],
      placement_outcomes: [{
        kind: "abstained" as const,
        input_provisional_revision_id: provisional.revision_id,
        boundary_decision: "abstain" as const,
        reason_code: "subject_unresolved", reconsideration_trigger: null,
      }],
    },
  };
  return {
    ...base, transition,
    append_attempt: {
      ...base.append_attempt,
      request_digest: authoritativeAppendRequestDigest(transition, origin),
    },
    origin,
  };
};

const identityAppend = (
  accountId: string,
  suffix: string,
  parentCommit: string,
): AuthoritativeLedgerAppend => {
  const sourceIdentity = {
    namespace_instance_ref: `namespace:${suffix}`, local_key: `speaker:${suffix}`,
    producer: { producer_ref: null, contract_ref: null },
    asserted_identity: { domain: null, scope_ref: null },
  };
  const entityId = `entity:${suffix}`;
  const authorization: IdentityAuthorization = {
    authorization_id: `authorization:${suffix}`, owner_account_id: accountId,
    endpoints: [
      { kind: "source_identity", source_identity_ref: sourceIdentity },
      { kind: "entity", entity_id: entityId },
    ],
    relation: "same",
    support: { kind: "owner_confirmation", confirmation_ref: `confirmation:${suffix}` },
    standing_policy_ref: null,
    namespace_scope: {
      namespace_instance_ref: sourceIdentity.namespace_instance_ref,
      identity_domain: null, scope_ref: null,
    },
    authority_policy_version: "identity-policy:v1", evaluated_frontier: 1,
    actor_provenance: { actor_ref: accountId, producer_ref: null },
    lifecycle: "active", superseded_by: null,
  };
  const event = {
    event_id: `event:${suffix}`, event_revision_id: `event:${suffix}:r1`,
    owner_account_id: accountId, capture_session_id: `session:${suffix}`,
    stream_id: `stream:${suffix}`, event_kind: "transcript",
    payload_schema_ref: "schema:event:v1", schema_version: "schema:v1",
    payload: { redacted: true }, event_time: "2026-08-11T20:00:00Z",
    ingest_time: null, source_sequence: 1,
    evidence_addressable_refs: [`evidence:${suffix}`], source_trust: "owner_attested",
    policy_labels: [], canonical_redacted_hash: "7".repeat(64),
  };
  const evidence = {
    evidence_id: `evidence:${suffix}`, event_revision_id: event.event_revision_id,
    source_unit_ref: `unit:${suffix}`, range: { start: 0, end: 5 }, excerpt: "Alice",
    source_identity_ref: sourceIdentity, speaker_rendering: "Alice",
    source_local_mention_ref: `mention:${suffix}`, state: "active" as const,
    source_trust: "owner_attested", policy_labels: [],
    source_independence_key: `root:${suffix}`,
  };
  const validTime = {
    typed_expression: {
      kind: "absolute" as const, granularity: "instant" as const,
      value: "2026-08-11T20:00:00Z",
    },
    resolved_interval: {
      kind: "instant" as const, start: "2026-08-11T20:00:00Z",
      end: "2026-08-11T20:00:00Z", timezone: "UTC", granularity: "instant" as const,
    },
    derivation: { resolver_version: "qualification:v1", timezone: "UTC" },
  };
  const provisional: ProvisionalClaim = {
    claim_lineage_id: `lineage:${suffix}:provisional`,
    claim_revision_id: `claim:${suffix}:provisional`,
    owner_account_id: accountId, predicate: "is_person",
    arguments: [{
      slot_id: "subject", role: "subject", surface: "Alice", span: { start: 0, end: 5 },
      value: { kind: "entity_ref", ref: entityId },
    }],
    temporal_scope: {
      observed_at: "2026-08-11T20:00:00Z", precision: "instant", valid_time: validTime,
    },
    evidence_refs: [evidence.evidence_id], policy_labels: [], source_language: "en",
    scope: { locality: "durable", scope_ref: entityId }, lifecycle: "provisional",
    ambiguity_markers: [], context_packet: null,
  };
  const canonical = {
    ...provisional, claim_lineage_id: `lineage:${suffix}:canonical`,
    claim_revision_id: `claim:${suffix}:canonical`, lifecycle: "canonical" as const,
    canonical_claim_id: `canonical:${suffix}`,
    source_provisional_revision_ids: [provisional.claim_revision_id],
  };
  delete (canonical as { ambiguity_markers?: unknown }).ambiguity_markers;
  delete (canonical as { context_packet?: unknown }).context_packet;
  const entity = {
    entity_id: entityId, owner_account_id: accountId,
    entity_revision_id: `${entityId}:r1`, handle: `alice:${suffix}`, labels: ["Alice"],
  };
  const mention = {
    mention_id: `mention:${suffix}`, owner_account_id: accountId,
    claim_revision_id: provisional.claim_revision_id, span: { start: 0, end: 5 },
    evidence_id: evidence.evidence_id, source_identity_ref: sourceIdentity,
    speaker_rendering: "Alice", slot_id: "subject", surface: "Alice",
    antecedent_handle: null, resolution: "resolved" as const, entity_id: entityId,
  };
  const constraint: IdentityConstraint = {
    constraint_id: `constraint:${suffix}`, owner_account_id: accountId,
    endpoints: authorization.endpoints,
    left_handle: `source:${suffix}`, right_handle: `alice:${suffix}`,
    relation: "same", identity_authorization: authorization,
    effective_at: 1, reversed_at: null,
  };
  const revisions: AtomicGraphTransition["revisions"] = [
    { kind: "claim", revision_id: provisional.claim_revision_id, claim: provisional, placement_status: "consumed" },
    { kind: "claim", revision_id: canonical.claim_revision_id, claim: canonical, placement_status: "canonical" },
    { kind: "mention", revision_id: `mention:${suffix}:r1`, mention },
    { kind: "identity_authorization", revision_id: `authorization:${suffix}:r1`, authorization },
    { kind: "entity", revision_id: entity.entity_revision_id, entity },
    { kind: "identity", revision_id: `constraint:${suffix}:r1`, constraint },
    { kind: "event", revision_id: event.event_revision_id, event },
    { kind: "evidence", revision_id: `evidence:${suffix}:r1`, evidence },
  ];
  const content = (revision: AtomicGraphTransition["revisions"][number]) =>
    revision.kind === "claim" ? revision.claim
      : revision.kind === "mention" ? revision.mention
        : revision.kind === "identity_authorization" ? revision.authorization
          : revision.kind === "entity" ? revision.entity
            : revision.kind === "identity" ? revision.constraint
              : revision.kind === "event" ? revision.event
                : revision.kind === "evidence" ? revision.evidence : {};
  const transition: AtomicGraphTransition = {
    placement: {
      offline_experiment: true,
      allocations: { [provisional.claim_revision_id]: canonical.claim_revision_id },
      results: [{
        input_provisional_revision_id: provisional.claim_revision_id,
        disposition: "admit",
        operation: { kind: "identity_linkage", entity_id: entityId },
      }],
    },
    derivation: prepareDerivation({
      attempt_id: `attempt:identity:${suffix}`, commit_id: `commit:identity:${suffix}`,
      owner_account_id: accountId, parent_commit: parentCommit,
      idempotency_key: `append:identity:${suffix}`, input_revisions: [],
      output_revisions: revisions.map((revision) => ({
        revision_id: revision.revision_id, content: content(revision),
      })),
      versions: {
        strategy_version: "qualification-identity-v1", model_version: "none",
        prompt_version: "none", policy_version: "qualification-v1",
        code_version: "qualification-v1", schema_version: "qualification-v1",
        tokenizer_version: "none", tool_version: "qualification-v1",
      },
      success_kind: "success",
    }),
    revisions,
    adjacency: [{
      claim_revision_id: canonical.claim_revision_id,
      entity_id: entityId, role_slot_id: "subject",
    }],
    artifacts: [{
      artifact_id: `artifact:${suffix}`, kind: "auto_placement_log",
      provisional_revision_id: provisional.claim_revision_id,
      canonical_claim_revision_id: canonical.claim_revision_id,
      margin: "high", risk_markers: [], unit_boundary_decision: "accept_ltm",
      scope_locality: "durable",
    }],
    identity_authority_context: {
      owner_confirmations: [{
        confirmation_ref: `confirmation:${suffix}`, owner_account_id: accountId,
        endpoints: authorization.endpoints, relation: "same",
      }],
      producer_assertions: [], standing_policies: [],
    },
  };
  const origin = { kind: "non_formation" as const, reason: "identity_consolidation" as const };
  return {
    append_attempt: {
      idempotency_key: transition.derivation.commit.idempotency_key,
      expected_parent_commit: parentCommit,
      request_digest: authoritativeAppendRequestDigest(transition, origin),
    },
    origin, transition,
  };
};

const durableWorkAcceptanceRequest = (
  accountId: string,
  suffix: string,
  acceptedAtEventTime: number,
  leaseDurationSeconds = 30,
  retryDelaySeconds = 10,
): DurableMemoryWorkAcceptanceRequest => {
  const strategy = registerMemoryStrategy({
    version: MEMORY_STRATEGY_VERSION,
    strategy_id: "strategy:qualification:formation:authority",
    work_kind: "formation",
    coordinates: {
      strategy_version: "formation:qualification:v1", model_version: "deepseek-flash:v1",
      prompt_version: "prompt:qualification:v1", policy_version: "policy:qualification:v1",
      code_version: "code:qualification:v1", schema_version: "schema:qualification:v1",
      tokenizer_version: "tokenizer:qualification:v1", tool_version: "none",
      result_contract_version: "formation-result:v2", speaker_strategy_version: "speaker:v1",
      boundary_strategy_version: "boundary:deepseek:v1",
    },
  });
  const policy = defineMemoryStrategyAssignmentPolicy({
    policy_id: "policy:qualification:formation:v1", work_kind: "formation",
    unit_kind: "session", key_version: "assignment-key:qualification:v1",
    authority_strategy_id: strategy.strategy_id, shadow_candidates: [],
  }, [strategy]);
  const assignment = createMemoryStrategyAssigner(new Uint8Array(32).fill(11)).assign({
    owner_account_id: accountId, unit_ref: `session:${suffix}`, policy, strategies: [strategy],
  });
  const inputs: readonly DurableMemoryWorkInputManifestEntry[] = formationWorkInputManifest(
    durableWorkFormationSnapshot(accountId, suffix),
  );
  const accepted: AcceptedDurableMemoryWork = {
    version: DURABLE_MEMORY_WORK_VERSION, job_id: `job:formation:${suffix}`,
    owner_account_id: accountId, account_epoch: 12,
    lifecycle_state: "active", deletion_epoch: null, work_kind: "formation",
    input_frontier: "0", input_digest: durableMemoryWorkInputManifestDigest(inputs),
    execution_contract_digest: assignment.authority.execution_contract_digest,
    accepted_at_event_time: acceptedAtEventTime, max_attempts: 2,
  };
  const pending = acceptDurableMemoryWork(accepted);
  const executionPolicy = registerDurableMemoryWorkExecutionPolicy({
    version: DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
    policy_id: "execution-policy:qualification:formation:v1",
    work_kind: "formation",
    execution_contract_digest: assignment.authority.execution_contract_digest,
    max_attempts: 2,
    lease_duration_seconds: leaseDurationSeconds,
    retry_delays_seconds: [retryDelaySeconds],
  });
  return Object.freeze({
    accepted_work: accepted, input_manifest: inputs, strategy_assignment: assignment,
    execution_policy: executionPolicy,
    request_digest: durableMemoryWorkAcceptanceRequestDigest(
      pending, inputs, assignment, executionPolicy,
    ),
  });
};

const durableWorkFormationSnapshot = (
  accountId: string,
  suffix: string,
): Readonly<FormationInputSnapshot> => {
  const event = {
    event_id: `event:work:${suffix}`, event_revision_id: `event:work:${suffix}:r1`,
    owner_account_id: accountId, capture_session_id: `session:${suffix}`,
    stream_id: `stream:${suffix}`, event_kind: "text",
    payload_schema_ref: "text:v1", schema_version: "schema:v1", payload: {},
    event_time: "2026-08-12T00:00:00Z", ingest_time: "2026-08-12T00:00:01Z",
    source_sequence: 0, evidence_addressable_refs: [`evidence:work:${suffix}`],
    source_trust: "test", policy_labels: [], canonical_redacted_hash: "e".repeat(64),
  };
  const evidence = {
    evidence_id: `evidence:work:${suffix}`, event_revision_id: event.event_revision_id,
    source_unit_ref: `unit:${suffix}`, range: { start: 0, end: 16 },
    excerpt: "Alice uses Atlas",
    source_identity_ref: {
      namespace_instance_ref: `source:${suffix}`, local_key: "speaker:unknown",
      producer: { producer_ref: null, contract_ref: null },
      asserted_identity: { domain: null, scope_ref: null },
    },
    speaker_rendering: null, source_local_mention_ref: null, state: "active" as const,
    source_trust: "test", policy_labels: [], source_independence_key: `capture:${suffix}`,
  };
  return parseFormationInputSnapshot({
    version: FORMATION_INPUT_SNAPSHOT_VERSION,
    owner_account_id: accountId, work_id: `job:formation:${suffix}`,
    session_id: `session:${suffix}`, input_frontier: "0", graph_frontier: 0,
    observed_at: "2026-08-12T00:00:00Z", source_language: "en",
    account_timezone: "UTC",
    reference_clock: {
      query_at: "2026-08-12T00:00:00Z", capture_at: "2026-08-12T00:00:00Z",
    },
    context: {
      frontier: {
        graph_head: "0", policy_version: "policy:qualification:v1",
        predicate_alias_generation: "alias:0", authorization_generation: "authorization:0",
        stm_generation: "stm:0",
      },
      entity_candidates: [], predicate_signatures: [], open_propositions: [],
    },
    predicate_registry: [], entity_registry: [], target_evidence_ids: [evidence.evidence_id],
    evidence: [evidence], events: [event], entities: [], identity_authorizations: [],
    identity_authority_context: null,
  });
};

realTest("PostgreSQL 18.4 real adapter qualification scaffold", () => {
  let ownerSql: Sql<Record<string, never>>;
  let pool: CloseablePostgresTransactionPool;

  beforeAll(() => {
    if (!explicitTestUrl) throw new Error("OMI_TEST_POSTGRES_URL is required");
    const parsed = new URL(explicitTestUrl);
    if (parsed.hostname !== "127.0.0.1" || parsed.protocol !== "postgres:") {
      throw new Error("postgres_test_not_loopback_only");
    }
    ownerSql = postgres(explicitTestUrl, { max: 2, prepare: true });
    pool = createPostgresJsTransactionPool({ connectionString: explicitTestUrl, maxConnections: 1 });
  });

  afterAll(async () => {
    await pool?.close();
    await ownerSql?.end({ timeout: 5 });
  });

  test("runs the pinned server, creates only the test role, and reapplies all migrations as no-ops", async () => {
    const version = await ownerSql.unsafe<{ server_version_num: string }[]>("SHOW server_version_num");
    expect(Number(version[0]?.server_version_num)).toBe(180004);
    expect(process.env["OMI_TEST_POSTGRES_IMAGE"]).toBe(
      "postgres:18.4-bookworm@sha256:882236b897e39051d2368c5ccc6cda944904723506b2dfc97f2a8f5bc9afa382",
    );
    await ownerSql.unsafe(`
      DO $role$
      BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omi_platform_application') THEN
          CREATE ROLE omi_platform_application NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
        END IF;
      END
      $role$
    `, [], { prepare: false });

    const first = await runPostgresMigrations(ownerSql);
    const second = await runPostgresMigrations(ownerSql);
    expect([...first.appliedVersions, ...first.skippedVersions].sort((left, right) => left - right)).toEqual(
      POSTGRES_MIGRATIONS.map((entry) => entry.version),
    );
    expect(second.appliedVersions).toEqual([]);
    expect(second.skippedVersions).toEqual(POSTGRES_MIGRATIONS.map((entry) => entry.version));
  }, 120_000);

  test("one reserved connection owns the transaction and SET LOCAL clears after rollback", async () => {
    let firstBackend: number | undefined;
    await expect(pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async (connection: CheckedOutPostgresConnection) => {
        const rows = await connection.query<{ backend_pid: number }>({
          name: "qualification.backend_and_local",
          text: `SELECT pg_backend_pid() AS backend_pid,
                        set_config('omi.account_id', $1, true) AS local_account`,
          values: ["account:qualification"],
        });
        firstBackend = rows[0]?.backend_pid;
        throw new Error("force rollback");
      },
    )).rejects.toThrow("force rollback");

    await pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async (connection: CheckedOutPostgresConnection) => {
        const rows = await connection.query<{ backend_pid: number; local_account: string | null }>({
          name: "qualification.local_cleared",
          text: `SELECT pg_backend_pid() AS backend_pid,
                        nullif(current_setting('omi.account_id', true), '') AS local_account`,
          values: [],
        });
        if (firstBackend === undefined) throw new Error("missing qualification backend");
        expect(rows[0]?.backend_pid).toBe(firstBackend);
        expect(rows[0]?.local_account).toBeNull();
      },
    );
  });

  test("backend termination rolls back the first write and the size-one pool reconnects", async () => {
    const killedAccount = `account:terminated:${randomUUID()}`;
    let killedBackend: number | undefined;

    let terminationError: unknown;
    try {
      await pool.withTransaction(
        { isolationLevel: "serializable", accessMode: "read write" },
        async (connection) => {
          const backend = await connection.query<{ backend_pid: number }>({
            name: "qualification.termination_backend",
            text: "SELECT pg_backend_pid() AS backend_pid",
            values: [],
          });
          killedBackend = backend[0]?.backend_pid;
          if (killedBackend === undefined) throw new Error("missing_termination_backend");
          await connection.execute({
            name: "qualification.termination_first_write",
            text: "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)",
            values: [killedAccount],
          });
          const terminated = await ownerSql.unsafe<{ terminated: boolean }[]>(
            "SELECT pg_terminate_backend($1) AS terminated",
            [killedBackend],
          );
          expect(terminated[0]?.terminated).toBe(true);
          // This is the named pre-commit checkpoint: no query is in flight while
          // Postgres.js observes the socket close. The pool must refuse COMMIT on
          // the lost lease and reconnect its size-one slot for the next request.
          await Bun.sleep(100);
        },
      );
    } catch (error) {
      terminationError = error;
    }
    expect(["57P01", "CONNECTION_CLOSED", "CONNECTION_DESTROYED"]).toContain(
      terminationError && typeof terminationError === "object"
        ? Reflect.get(terminationError, "code") : null,
    );

    const rolledBack = await ownerSql.unsafe<{ count: number }[]>(
      "SELECT count(*)::int AS count FROM omi_memory.platform_accounts WHERE account_id = $1",
      [killedAccount],
    );
    expect([...rolledBack]).toEqual([{ count: 0 }]);

    await pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async (connection) => {
        const recovered = await connection.query<{
          backend_pid: number; local_account: string | null;
        }>({
          name: "qualification.termination_recovered_pool",
          text: `SELECT pg_backend_pid() AS backend_pid,
                        nullif(current_setting('omi.account_id', true), '') AS local_account`,
          values: [],
        });
        if (killedBackend === undefined) throw new Error("missing_termination_backend");
        expect(recovered[0]?.backend_pid).not.toBe(killedBackend);
        expect(recovered[0]?.local_account).toBeNull();
      },
    );
  }, 30_000);

  test("request cancellation rolls back and clears transaction-local authority before pool reuse", async () => {
    const controller = new AbortController();
    let cancelledBackend: number | undefined;
    const pending = pool.withTransaction(
      {
        isolationLevel: "serializable", accessMode: "read write",
        signal: controller.signal,
      },
      async (connection) => {
        const backend = await connection.query<{ backend_pid: number }>({
          name: "qualification.cancellation_backend",
          text: `SELECT pg_backend_pid() AS backend_pid,
                        set_config('omi.account_id', $1, true) AS local_account`,
          values: ["account:cancelled"],
        });
        cancelledBackend = backend[0]?.backend_pid;
        setTimeout(() => controller.abort(new Error("qualification_cancelled")), 50);
        await connection.query({
          name: "qualification.cancellation_sleep",
          text: "SELECT pg_sleep(30)", values: [],
        });
      },
    );
    await expect(pending).rejects.toMatchObject({ code: "57014" });

    await pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async (connection) => {
        const recovered = await connection.query<{
          backend_pid: number; local_account: string | null;
        }>({
          name: "qualification.cancellation_reuse",
          text: `SELECT pg_backend_pid() AS backend_pid,
                        nullif(current_setting('omi.account_id', true), '') AS local_account`,
          values: [],
        });
        expect(recovered[0]?.backend_pid).toBe(cancelledBackend);
        expect(recovered[0]?.local_account).toBeNull();
      },
    );
  }, 30_000);

  test("application role accepts exact durable work before inference and revalidates authority before replay", async () => {
    const suffix = randomUUID();
    const accountId = `account:work-acceptance:${suffix}`;
    const principalId = `principal:work-acceptance:${suffix}`;
    const applicationId = "app:qualification-work";
    const credentialId = `credential:work:${suffix}`;
    const grantId = `grant:work:${suffix}`;
    const executeGrantId = `grant:work-execute:${suffix}`;
    const controlHash = "a".repeat(64);
    const credentialHash = "b".repeat(64);
    const grantHash = "c".repeat(64);
    const now = Math.floor(Date.now() / 1_000);
    // The managed VM clock is synchronized independently from the host. Keep
    // accepted work safely in the past so a sub-second host/guest skew cannot
    // turn an immediately leaseable job into a transient none_available.
    const acceptedAt = now - 5;

    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(
        "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)", [accountId],
      );
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
          (account_id, control_revision, account_generation, account_epoch,
           lifecycle_state, deletion_epoch, observed_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, 17, 'new', 12, 'active', NULL, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountId, controlHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
          (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 17, 12, 17)`, [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_revisions
          (account_id, principal_id, application_id, credential_id,
           credential_generation, credential_kind, lifecycle,
           authentication_strength, expires_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, $2, $3, $4, 4, 'firebase', 'active', 'service-workload',
                to_timestamp($5), 'credential-v1', '{}'::jsonb, $6)`,
      [accountId, principalId, applicationId, credentialId, now + 7_200, credentialHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_heads
          (account_id, application_id, credential_id, credential_generation)
        VALUES ($1, $2, $3, 4)`, [accountId, applicationId, credentialId]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 4, 'memories.work.accept', $4, 9, 'active', true,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
      [accountId, applicationId, credentialId, grantId, grantHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_heads
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version)
        VALUES ($1, $2, $3, 4, 'memories.work.accept', $4, 9)`,
      [accountId, applicationId, credentialId, grantId]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 4, 'memories.work.execute', $4, 1, 'active', true,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
      [accountId, applicationId, credentialId, executeGrantId, "e".repeat(64)]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_heads
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version)
        VALUES ($1, $2, $3, 4, 'memories.work.execute', $4, 1)`,
      [accountId, applicationId, credentialId, executeGrantId]);
    });

    const authorityRow: AuthorityStateRow = {
      account_id: accountId, principal_id: principalId, application_id: applicationId,
      credential_id: credentialId, credential_generation: 4,
      capability: "memories.work.accept", grant_id: grantId, grant_version: 9,
      account_epoch: 12, control_conflict_reason: null, control_conflict_at_revision: null,
      destination_activation_epoch: 12, destination_activation_revision: 17,
      lifecycle_state: "active", deletion_epoch: null, account_generation: "new",
      credential_lifecycle: "active", grant_lifecycle: "active", grant_enabled: true,
      authentication_strength: "service-workload",
      credential_expires_at_epoch_seconds: now + 7_200, control_revision: 17,
      control_content_hash: controlHash, credential_content_hash: credentialHash,
      grant_content_hash: grantHash, db_now_epoch_seconds: now,
    };
    const context = createAuthorizedLedgerWriteContextIssuer().issue({
      context_version: "authorized-ledger-write-context-v1", principal_id: principalId,
      account_id: accountId, application_id: applicationId, credential_id: credentialId,
      credential_generation: 4, capability: "memories.work.accept", grant_id: grantId,
      grant_version: 9, account_epoch: 12, destination_activation_revision: 17,
      lifecycle_state: "active", deletion_epoch: null, authentication_strength: "service-workload",
      issued_at_epoch_seconds: now - 60, expires_at_epoch_seconds: now + 3_600,
      authorization_state_digest: authorizationStateDigest(authorityRow),
    }, now);
    const executionAuthorityRow: AuthorityStateRow = {
      ...authorityRow,
      capability: "memories.work.execute",
      grant_id: executeGrantId,
      grant_version: 1,
      grant_content_hash: "e".repeat(64),
    };
    const executionContext = createAuthorizedLedgerWriteContextIssuer().issue({
      context_version: "authorized-ledger-write-context-v1", principal_id: principalId,
      account_id: accountId, application_id: applicationId, credential_id: credentialId,
      credential_generation: 4, capability: "memories.work.execute", grant_id: executeGrantId,
      grant_version: 1, account_epoch: 12, destination_activation_revision: 17,
      lifecycle_state: "active", deletion_epoch: null, authentication_strength: "service-workload",
      issued_at_epoch_seconds: now - 60, expires_at_epoch_seconds: now + 3_600,
      authorization_state_digest: authorizationStateDigest(executionAuthorityRow),
    }, now);
    let lastWorkAcceptanceStatement = "none";
    let lastWorkAcceptanceProviderCode = "none";
    let lastWorkAcceptanceConstraint = "none";
    const appRolePool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(
        options: Parameters<PostgresTransactionPool["withTransaction"]>[0],
        callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
      ) => pool.withTransaction(options, async (connection) => {
        await connection.query({
          name: "qualification.work_acceptance_set_role",
          text: "SET LOCAL ROLE omi_platform_application", values: [],
        });
        const role = await connection.query<{ current_user: string }>({
          name: "qualification.work_acceptance_assert_role", text: "SELECT current_user", values: [],
        });
        expect(role).toEqual([{ current_user: "omi_platform_application" }]);
        return callback(Object.freeze({
          connectionIdentity: connection.connectionIdentity,
          query: async <Row extends Record<string, unknown>>(statement: SqlStatement) => {
            lastWorkAcceptanceStatement = statement.name;
            return connection.query<Row>(statement);
          },
          execute: async (statement: SqlStatement) => {
            lastWorkAcceptanceStatement = statement.name;
            try {
              if (statement.name === "work.execution_policy.insert") {
                const validation = await connection.query<{
                  valid: boolean; kind: string; count: number; item_kind: string;
                  item_text: string; integer_shape: boolean; in_range: boolean;
                }>({
                  name: "qualification.execution_policy_shape",
                  text: `SELECT
                           omi_memory.valid_memory_work_retry_delays(
                             ($1::text)::jsonb, $2::integer
                           ) AS valid,
                           jsonb_typeof(($1::text)::jsonb) AS kind,
                           jsonb_array_length(($1::text)::jsonb) AS count,
                           jsonb_typeof(value) AS item_kind,
                           value::text AS item_text,
                           value::text ~ '^[0-9]+$' AS integer_shape,
                           value::text::integer BETWEEN 1 AND 86400 AS in_range
                         FROM jsonb_array_elements(($1::text)::jsonb)`,
                  values: [statement.values[8]!, Number(statement.values[6]) - 1],
                });
                const expectedDelay = JSON.parse(String(statement.values[8]))[0];
                expect(validation).toEqual([{
                  valid: true, kind: "array", count: 1, item_kind: "number",
                  item_text: String(expectedDelay), integer_shape: true, in_range: true,
                }]);
              }
              return await connection.execute(statement);
            } catch (error) {
              const code = error && typeof error === "object" ? Reflect.get(error, "code") : null;
              const constraint = error && typeof error === "object"
                ? Reflect.get(error, "constraint_name") : null;
              lastWorkAcceptanceProviderCode = typeof code === "string" ? code : "unknown";
              lastWorkAcceptanceConstraint = typeof constraint === "string" ? constraint : "unknown";
              throw error;
            }
          },
        }));
      }),
    });
    const repository = createPostgresDurableMemoryWorkAcceptanceRepository({ pool: appRolePool });
    const inputRepository = createPostgresFormationWorkInputRepository({ pool: appRolePool });
    const stageInput = async (
      request: DurableMemoryWorkAcceptanceRequest,
      inputSuffix: string,
    ) => {
      const pending = acceptDurableMemoryWork(request.accepted_work);
      const body = {
        pending_job: pending,
        snapshot: durableWorkFormationSnapshot(accountId, inputSuffix),
      };
      return inputRepository.stage(context, {
        ...body,
        request_digest: formationWorkInputStageRequestDigest(body),
      });
    };
    await expect(repository.accept(
      context,
      durableWorkAcceptanceRequest(accountId, `${suffix}:missing-input`, acceptedAt, 2, 1),
    )).rejects.toMatchObject({ code: "persistence_failed", message: "persistence_failed" });
    const acceptedRequest = durableWorkAcceptanceRequest(accountId, suffix, acceptedAt, 2, 1);

    await expect(stageInput(acceptedRequest, suffix)).resolves.toMatchObject({
      kind: "staged", input: { snapshot: { work_id: `job:formation:${suffix}` } },
    });
    await expect(stageInput(acceptedRequest, suffix)).resolves.toMatchObject({ kind: "replayed" });

    try {
      expect(await repository.accept(context, acceptedRequest)).toMatchObject({
        kind: "accepted", job: { job_id: `job:formation:${suffix}`, state: "pending" },
      });
    } catch (error) {
      const code = error && typeof error === "object" && "code" in error
        ? String(Reflect.get(error, "code")) : "assertion_or_unknown";
      throw new Error(
        `work_acceptance_failure_at:${lastWorkAcceptanceStatement}:${lastWorkAcceptanceProviderCode}`
        + `:${lastWorkAcceptanceConstraint}:${code}`,
      );
    }
    await expect(repository.accept(context, acceptedRequest)).resolves.toMatchObject({
      kind: "replayed", job: { state: "pending" },
    });
    await expect(repository.accept(
      context, durableWorkAcceptanceRequest(accountId, suffix, acceptedAt + 1),
    )).resolves.toEqual({ kind: "idempotency_conflict" });
    const policyDriftRequest = durableWorkAcceptanceRequest(
      accountId, `${suffix}:policy-drift`, acceptedAt, 3, 1,
    );
    await expect(stageInput(policyDriftRequest, `${suffix}:policy-drift`))
      .resolves.toMatchObject({ kind: "staged" });
    await expect(repository.accept(context, policyDriftRequest))
      .resolves.toEqual({ kind: "idempotency_conflict" });

    const persisted = await ownerSql.unsafe<{
      definitions: number; policies: number; bundles: number; execution_policies: number;
      acceptances: number;
      inputs: number; states: number; heads: number; state: string; state_revision: string;
      execution_max_attempts: number; execution_lease_seconds: number;
      execution_retry_delays: unknown;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_strategy_definitions WHERE account_id = $1) AS definitions,
        (SELECT count(*)::int FROM omi_memory.memory_strategy_assignment_policies WHERE account_id = $1) AS policies,
        (SELECT count(*)::int FROM omi_memory.memory_strategy_assignment_bundles WHERE account_id = $1) AS bundles,
        (SELECT count(*)::int FROM omi_memory.memory_work_execution_policies WHERE account_id = $1) AS execution_policies,
        (SELECT count(*)::int FROM omi_memory.memory_work_acceptances WHERE account_id = $1) AS acceptances,
        (SELECT count(*)::int FROM omi_memory.memory_work_input_manifest WHERE account_id = $1) AS inputs,
        (SELECT count(*)::int FROM omi_memory.memory_work_state_revisions WHERE account_id = $1) AS states,
        (SELECT count(*)::int FROM omi_memory.memory_work_heads WHERE account_id = $1) AS heads,
        (SELECT state FROM omi_memory.memory_work_state_revisions WHERE account_id = $1) AS state,
        (SELECT state_revision::text FROM omi_memory.memory_work_heads WHERE account_id = $1) AS state_revision,
        (SELECT max_attempts FROM omi_memory.memory_work_execution_policies WHERE account_id = $1) AS execution_max_attempts,
        (SELECT lease_duration_seconds FROM omi_memory.memory_work_execution_policies WHERE account_id = $1) AS execution_lease_seconds,
        (SELECT retry_delays_seconds FROM omi_memory.memory_work_execution_policies WHERE account_id = $1) AS execution_retry_delays
    `, [accountId]);
    expect([...persisted]).toEqual([{
      definitions: 1, policies: 1, bundles: 1, execution_policies: 1, acceptances: 1,
      inputs: 3, states: 1, heads: 1, state: "pending", state_revision: "0",
      execution_max_attempts: 2, execution_lease_seconds: 2, execution_retry_delays: [1],
    }]);

    const backlogEvents: OperationalTelemetryEvent[] = [];
    const backlogTelemetry = createOperationalTelemetryEmitter((event) => {
      backlogEvents.push(event);
    });
    const backlogSource = createPostgresDurableMemoryWorkBacklogSource({ pool: appRolePool });
    await expect(emitDurableMemoryWorkBacklogTelemetry(
      backlogSource, executionContext, backlogTelemetry,
    )).resolves.toEqual({ kind: "available" });
    expect(backlogEvents).toEqual([
      {
        version: "operational-telemetry-v1", family: "backlog", work_kind: "formation",
        outcome: "available", ready: 1, leased: 0, retry_wait: 0, dead: 0,
        oldest_ready_age_ms: expect.any(Number),
      },
      {
        version: "operational-telemetry-v1", family: "backlog", work_kind: "promotion",
        outcome: "available", ready: 0, leased: 0, retry_wait: 0, dead: 0,
        oldest_ready_age_ms: null,
      },
      {
        version: "operational-telemetry-v1", family: "backlog", work_kind: "identity_cluster",
        outcome: "available", ready: 0, leased: 0, retry_wait: 0, dead: 0,
        oldest_ready_age_ms: null,
      },
      {
        version: "operational-telemetry-v1", family: "backlog", work_kind: "predicate_batch",
        outcome: "available", ready: 0, leased: 0, retry_wait: 0, dead: 0,
        oldest_ready_age_ms: null,
      },
    ]);
    expect((backlogEvents[0] as { oldest_ready_age_ms: number }).oldest_ready_age_ms)
      .toBeGreaterThanOrEqual(5_000);

    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(`UPDATE omi_memory.memory_work_heads
        SET job_id = job_id WHERE account_id = $1`, [accountId]);
    })).rejects.toMatchObject({ code: "42501" });
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(`UPDATE omi_memory.memory_work_execution_policies
        SET lease_duration_seconds = 31 WHERE account_id = $1`, [accountId]);
    })).rejects.toMatchObject({ code: "42501" });

    const rollbackSuffix = `${suffix}:rollback`;
    const rollbackRequest = durableWorkAcceptanceRequest(accountId, rollbackSuffix, acceptedAt, 2, 1);
    await expect(stageInput(rollbackRequest, rollbackSuffix)).resolves.toMatchObject({ kind: "staged" });
    try {
      await ownerSql.unsafe(`
        CREATE OR REPLACE FUNCTION omi_memory.qualification_reject_work_acceptance()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'qualification injected rollback'; END
        $$;
        DROP TRIGGER IF EXISTS reject_work_acceptance ON omi_memory.memory_work_state_revisions;
        CREATE TRIGGER reject_work_acceptance
        AFTER INSERT ON omi_memory.memory_work_state_revisions
        FOR EACH ROW EXECUTE FUNCTION omi_memory.qualification_reject_work_acceptance()
      `, [], { prepare: false });
      await expect(repository.accept(context, rollbackRequest))
        .rejects.toMatchObject({ code: "persistence_failed", message: "persistence_failed" });
    } finally {
      await ownerSql.unsafe(`
        DROP TRIGGER IF EXISTS reject_work_acceptance ON omi_memory.memory_work_state_revisions;
        DROP FUNCTION IF EXISTS omi_memory.qualification_reject_work_acceptance()
      `, [], { prepare: false });
    }
    const rolledBack = await ownerSql.unsafe<{ count: number }[]>(`
      SELECT count(*)::int AS count FROM omi_memory.memory_work_acceptances
      WHERE account_id = $1 AND job_id = $2
    `, [accountId, `job:formation:${rollbackSuffix}`]);
    expect([...rolledBack]).toEqual([{ count: 0 }]);

    const executionRepository = createPostgresDurableMemoryWorkExecutionRepository({
      pool: appRolePool,
    });
    const firstLease = await executionRepository.leaseNext(executionContext, {
      work_kinds: ["formation"],
    });
    expect(firstLease).toMatchObject({
      kind: "leased",
      job: { job_id: acceptedRequest.accepted_work.job_id, attempt: 1, lease_fence: 1 },
    });
    if (firstLease.kind !== "leased" || !firstLease.job.lease) {
      throw new Error("qualification_missing_first_lease");
    }
    await expect(inputRepository.load(executionContext, firstLease.job)).resolves.toMatchObject({
      kind: "found", snapshot: { work_id: acceptedRequest.accepted_work.job_id },
    });
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(`SELECT * FROM omi_memory.memory_formation_work_inputs
        WHERE account_id = $1`, [accountId]);
    })).rejects.toMatchObject({ code: "42501" });
    expect(firstLease.job.lease.expires_at_event_time
      - firstLease.job.lease.leased_at_event_time).toBe(2);
    const resultRepository = createPostgresDurableMemoryWorkResultRepository({
      pool: appRolePool,
    });
    const normalizedResult = { claims: [{ candidate_ref: "candidate:qualification:1" }] };
    const resultContractVersion = "formation-result:v2";
    const normalizedResultDigest = durableMemoryWorkNormalizedResultDigest(
      resultContractVersion, normalizedResult,
    );
    const stageBody: DurableMemoryWorkResultStageBody = {
      leased_job: firstLease.job,
      result_contract_version: resultContractVersion,
      response_digest: "7".repeat(64),
      normalized_result_digest: normalizedResultDigest,
      normalized_result: normalizedResult,
    };
    const stageRequest = {
      ...stageBody,
      request_digest: durableMemoryWorkResultStageRequestDigest(stageBody),
    };
    await expect(resultRepository.load(executionContext, { leased_job: firstLease.job }))
      .resolves.toEqual({ kind: "missing" });
    await expect(resultRepository.stage(executionContext, stageRequest))
      .resolves.toMatchObject({
        kind: "staged",
        result: { produced_attempt: 1, normalized_result: normalizedResult },
      });
    await expect(resultRepository.stage(executionContext, stageRequest))
      .resolves.toMatchObject({ kind: "replayed" });
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(`SELECT * FROM omi_memory.memory_work_staged_results
        WHERE account_id = $1`, [accountId]);
    })).rejects.toMatchObject({ code: "42501" });
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe("SELECT set_config('omi.account_id', $1, true)", [accountId]);
      await transaction.unsafe("SELECT set_config('omi.capability', 'memories.work.execute', true)");
      await transaction.unsafe("SELECT set_config('omi.principal_id', 'worker:other', true)");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.read_durable_work_staged_result($1, $2)",
        [accountId, firstLease.job.job_id],
      );
    })).rejects.toMatchObject({ code: "42501" });
    await expect(executionRepository.recordFailure(executionContext, {
      job_id: firstLease.job.job_id,
      lease_fence: firstLease.job.lease_fence,
      error_code: "model_timeout",
    })).resolves.toMatchObject({
      kind: "recorded",
      job: { state: "retryable_failed", outcome: { error_code: "model_timeout" } },
    });
    // Cross the database-time retry boundary with a full second of scheduling margin.
    await Bun.sleep(2_100);
    const secondLease = await executionRepository.leaseNext(executionContext, {
      work_kinds: ["formation"],
    });
    expect(secondLease).toMatchObject({
      kind: "leased", job: { job_id: firstLease.job.job_id, attempt: 2, lease_fence: 2 },
    });
    if (secondLease.kind !== "leased") throw new Error("qualification_missing_second_lease");
    await expect(resultRepository.load(executionContext, { leased_job: secondLease.job }))
      .resolves.toMatchObject({
        kind: "found",
        result: { produced_attempt: 1, producer_worker_id: executionContext.principal_id },
      });
    await expect(executionRepository.recordFailure(executionContext, {
      job_id: secondLease.job.job_id,
      lease_fence: secondLease.job.lease_fence,
      error_code: "model_response_invalid",
    })).resolves.toMatchObject({
      kind: "recorded",
      job: { state: "dead_letter", attempt: 2, outcome: { attempts: 2 } },
    });

    const recoverySuffix = `${suffix}:recovery`;
    const recoveryRequest = durableWorkAcceptanceRequest(accountId, recoverySuffix, acceptedAt, 2, 1);
    await expect(stageInput(recoveryRequest, recoverySuffix)).resolves.toMatchObject({ kind: "staged" });
    await expect(repository.accept(context, recoveryRequest))
      .resolves.toMatchObject({ kind: "accepted", job: { state: "pending" } });
    const recoveryLease = await executionRepository.leaseNext(executionContext, {
      work_kinds: ["formation"],
    });
    expect(recoveryLease).toMatchObject({
      kind: "leased", job: { job_id: `job:formation:${recoverySuffix}`, attempt: 1 },
    });
    if (recoveryLease.kind !== "leased") throw new Error("qualification_missing_recovery_lease");
    // Cross the database-time lease expiry with a full second of scheduling margin.
    await Bun.sleep(3_100);
    await expect(executionRepository.recoverExpired(executionContext, {
      job_id: recoveryLease.job.job_id,
    })).resolves.toMatchObject({
      kind: "recovered",
      job: { state: "retryable_failed", outcome: { error_code: "worker_lost" } },
    });
    await Bun.sleep(2_100);
    const recoveredSecondLease = await executionRepository.leaseNext(executionContext, {
      work_kinds: ["formation"],
    });
    if (recoveredSecondLease.kind !== "leased") {
      throw new Error("qualification_missing_recovered_second_lease");
    }
    await expect(executionRepository.recordFailure(executionContext, {
      job_id: recoveredSecondLease.job.job_id,
      lease_fence: recoveredSecondLease.job.lease_fence,
      error_code: "worker_lost",
    })).resolves.toMatchObject({ kind: "recorded", job: { state: "dead_letter" } });

    const successSuffix = `${suffix}:success`;
    const successAcceptance = durableWorkAcceptanceRequest(accountId, successSuffix, acceptedAt, 2, 1);
    await expect(stageInput(successAcceptance, successSuffix)).resolves.toMatchObject({ kind: "staged" });
    await expect(repository.accept(context, successAcceptance)).resolves.toMatchObject({
      kind: "accepted", job: { state: "pending" },
    });
    const successLease = await executionRepository.leaseNext(executionContext, {
      work_kinds: ["formation"],
    });
    expect(successLease).toMatchObject({
      kind: "leased", job: { job_id: `job:formation:${successSuffix}`, attempt: 1 },
    });
    if (successLease.kind !== "leased") throw new Error("qualification_missing_success_lease");
    const successNormalized = { claims: [{ candidate_ref: "candidate:success:1" }] };
    const successContractVersion = "formation-result:v2";
    const successNormalizedDigest = durableMemoryWorkNormalizedResultDigest(
      successContractVersion, successNormalized,
    );
    const successStageBody: DurableMemoryWorkResultStageBody = {
      leased_job: successLease.job,
      result_contract_version: successContractVersion,
      response_digest: "8".repeat(64),
      normalized_result_digest: successNormalizedDigest,
      normalized_result: successNormalized,
    };
    const successStage = await resultRepository.stage(executionContext, {
      ...successStageBody,
      request_digest: durableMemoryWorkResultStageRequestDigest(successStageBody),
    });
    expect(successStage).toMatchObject({ kind: "staged" });
    if (successStage.kind !== "staged") throw new Error("qualification_missing_success_stage");
    const baseSuccessAppend = formationAppend(accountId, successSuffix, null);
    if (baseSuccessAppend.origin.kind !== "formation") {
      throw new Error("qualification_success_origin_invalid");
    }
    const successOrigin = {
      kind: "formation" as const,
      outcome: parseFormationOutcomeEnvelope({
        ...baseSuccessAppend.origin.outcome,
        work_id: successLease.job.job_id,
        input_frontier: successLease.job.input_frontier,
        response_digest: successStage.result.response_digest,
      }),
    };
    const successAppend: AuthoritativeLedgerAppend = {
      transition: baseSuccessAppend.transition,
      origin: successOrigin,
      append_attempt: {
        ...baseSuccessAppend.append_attempt,
        expected_parent_commit: null,
        request_digest: authoritativeAppendRequestDigest(
          baseSuccessAppend.transition, successOrigin,
        ),
      },
    };
    const successBody: DurableMemoryWorkSuccessBody = {
      leased_job: successLease.job,
      result_kind: "successful",
      response_digest: successStage.result.response_digest,
      result_digest: successAppend.append_attempt.request_digest,
      staged_result: successStage.result,
      authoritative_append: successAppend,
    };
    const successRequest = {
      ...successBody,
      request_digest: durableMemoryWorkSuccessRequestDigest(successBody),
    };
    const successRepository = createPostgresDurableMemoryWorkSuccessRepository({
      pool: appRolePool,
    });
    const successRacePhysicalPool = createPostgresJsTransactionPool({
      connectionString: explicitTestUrl!, maxConnections: 2,
    });
    const successRaceRolePool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(
        options: Parameters<PostgresTransactionPool["withTransaction"]>[0],
        callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
      ) => successRacePhysicalPool.withTransaction(options, async (connection) => {
        await connection.query({
          name: "qualification.success_race_set_application_role",
          text: "SET LOCAL ROLE omi_platform_application", values: [],
        });
        return callback(connection);
      }),
    });
    try {
      const raceRepository = createPostgresDurableMemoryWorkSuccessRepository({
        pool: successRaceRolePool,
      });
      const raceOutcomes = await Promise.all([
        raceRepository.commit(executionContext, successRequest),
        raceRepository.commit(executionContext, successRequest),
      ]);
      expect(raceOutcomes.filter((outcome) => outcome.kind === "committed")).toHaveLength(1);
      expect(raceOutcomes.filter((outcome) =>
        outcome.kind === "replayed" || outcome.kind === "serialization_retryable"))
        .toHaveLength(1);
    } finally {
      await successRacePhysicalPool.close();
    }
    await expect(successRepository.commit(executionContext, successRequest))
      .resolves.toMatchObject({
        kind: "replayed", job: { state: "succeeded" },
        commit_id: successAppend.transition.derivation.commit.commit_id, sequence: 1,
      });
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(`SELECT * FROM omi_memory.memory_work_success_results
        WHERE account_id = $1`, [accountId]);
    })).rejects.toMatchObject({ code: "42501" });
    const successRows = await ownerSql.unsafe<{
      successes: number; success_outbox: number; graph_sequence: string;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_work_success_results
          WHERE account_id = $1) AS successes,
        (SELECT count(*)::int FROM omi_memory.memory_work_outbox_events
          WHERE account_id = $1 AND event_kind = 'memory_work_succeeded') AS success_outbox,
        (SELECT sequence::text FROM omi_memory.memory_graph_heads
          WHERE account_id = $1) AS graph_sequence
    `, [accountId]);
    expect([...successRows]).toEqual([{
      successes: 1, success_outbox: 1, graph_sequence: "1",
    }]);

    const runtimeSuffix = `${suffix}:one-shot-runtime`;
    const runtimeBaseSnapshot = durableWorkFormationSnapshot(accountId, runtimeSuffix);
    const runtimeSnapshot = parseFormationInputSnapshot({
      ...runtimeBaseSnapshot,
      input_frontier: "1",
      graph_frontier: 1,
      context: {
        ...runtimeBaseSnapshot.context,
        frontier: { ...runtimeBaseSnapshot.context.frontier, graph_head: "1" },
      },
    });
    const runtimeStrategy = registerMemoryStrategy({
      version: MEMORY_STRATEGY_VERSION,
      strategy_id: "strategy:qualification:formation:one-shot:v1",
      work_kind: "formation",
      coordinates: {
        strategy_version: "formation:qualification:one-shot:v1",
        model_version: "deterministic-fake:v1",
        prompt_version: GROUNDED_EXTRACTION_PROMPT_VERSION,
        policy_version: "policy:qualification:one-shot:v1",
        code_version: "code:qualification:one-shot:v1",
        schema_version: "schema:qualification:one-shot:v1",
        tokenizer_version: "none",
        tool_version: "none",
        result_contract_version: DURABLE_MEMORY_GRAPH_PLAN_VERSION,
        speaker_strategy_version: GROUNDED_MENTION_STRATEGY_VERSION,
        boundary_strategy_version: "v4",
      },
    });
    const runtimeAssignmentPolicy = defineMemoryStrategyAssignmentPolicy({
      policy_id: "policy:qualification:formation:one-shot:v1",
      work_kind: "formation",
      unit_kind: "work",
      key_version: "assignment-key:qualification:one-shot:v1",
      authority_strategy_id: runtimeStrategy.strategy_id,
      shadow_candidates: [],
    }, [runtimeStrategy]);
    const runtimeAssignment = createMemoryStrategyAssigner(new Uint8Array(32).fill(23)).assign({
      owner_account_id: accountId,
      unit_ref: runtimeSnapshot.work_id,
      policy: runtimeAssignmentPolicy,
      strategies: [runtimeStrategy],
    });
    const runtimeExecutionPolicy = registerDurableMemoryWorkExecutionPolicy({
      version: DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
      policy_id: "execution-policy:qualification:formation:one-shot:v1",
      work_kind: "formation",
      execution_contract_digest: runtimeStrategy.execution_contract_digest,
      max_attempts: 2,
      lease_duration_seconds: 2,
      retry_delays_seconds: [1],
    });
    let runtimeModelCalls = 0;
    const runtimeModel = new DeterministicFakeModel((request: ModelInvokeRequest) => {
      runtimeModelCalls += 1;
      if (request.strategy === "grounded-extraction") return {
        claims: [{
          relation: "uses",
          arguments: [
            { slot_id: "person", role: "person", surface: "Alice" },
            { slot_id: "tool", role: "tool", surface: "Atlas" },
          ],
          polarity: "positive",
          temporal_expression: {
            kind: "absolute", granularity: "day", value: "2026-08-12",
          },
          evidence: "e1",
          observed_speaker_slot_id: null,
        }, {
          relation: "operates",
          arguments: [
            { slot_id: "person", role: "person", surface: "Alice" },
            { slot_id: "tool", role: "tool", surface: "Atlas" },
          ],
          polarity: "positive",
          temporal_expression: {
            kind: "absolute", granularity: "day", value: "2026-08-12",
          },
          evidence: "e1",
          observed_speaker_slot_id: null,
        }],
      };
      if (request.strategy === "local-handle-durable-entity") return { decision: "abstain" };
      if (request.strategy === "scope-role-binding") return {
        bindings: { person: null, tool: null },
        scope: { locality: "durable", scope_ref: "global" },
      };
      if (request.strategy === "stm-ltm-unit-boundary") return { decision: "accept_ltm" };
      throw new Error("unexpected_formation_model_strategy");
    });
    const formationRuntime = createPostgresFormationOneShotRuntime({
      pool: appRolePool,
      strategies: [runtimeStrategy],
      resolve_model: async () => runtimeModel,
      max_parent_rematerializations: 3,
      observability: {
        telemetry: createOperationalTelemetryEmitter((event) => {
          backlogEvents.push(event);
        }),
      },
    });
    const runtimeIngestion = {
      snapshot: runtimeSnapshot,
      strategy_assignment: runtimeAssignment,
      execution_policy: runtimeExecutionPolicy,
      accepted_at_event_time: now,
    };

    try {
      await ownerSql.unsafe(`
        CREATE OR REPLACE FUNCTION omi_memory.qualification_reject_one_shot_acceptance()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'qualification injected one-shot acceptance rollback'; END
        $$;
        DROP TRIGGER IF EXISTS reject_one_shot_acceptance
          ON omi_memory.memory_work_state_revisions;
        CREATE TRIGGER reject_one_shot_acceptance
        AFTER INSERT ON omi_memory.memory_work_state_revisions
        FOR EACH ROW EXECUTE FUNCTION omi_memory.qualification_reject_one_shot_acceptance()
      `, [], { prepare: false });
      await expect(formationRuntime.accept(context, runtimeIngestion))
        .rejects.toMatchObject({ code: "persistence_failed", message: "persistence_failed" });
    } finally {
      await ownerSql.unsafe(`
        DROP TRIGGER IF EXISTS reject_one_shot_acceptance
          ON omi_memory.memory_work_state_revisions;
        DROP FUNCTION IF EXISTS omi_memory.qualification_reject_one_shot_acceptance()
      `, [], { prepare: false });
    }
    const stagedBeforeAcceptance = await ownerSql.unsafe<{
      staged_inputs: number; acceptances: number;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_formation_work_inputs
          WHERE account_id = $1 AND job_id = $2) AS staged_inputs,
        (SELECT count(*)::int FROM omi_memory.memory_work_acceptances
          WHERE account_id = $1 AND job_id = $2) AS acceptances
    `, [accountId, runtimeSnapshot.work_id]);
    expect([...stagedBeforeAcceptance]).toEqual([{ staged_inputs: 1, acceptances: 0 }]);
    await expect(formationRuntime.accept(context, runtimeIngestion)).resolves.toMatchObject({
      kind: "accepted", job: { job_id: runtimeSnapshot.work_id, state: "pending" },
    });

    try {
      await ownerSql.unsafe(`
        CREATE OR REPLACE FUNCTION omi_memory.qualification_reject_one_shot_success()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'qualification injected one-shot process loss'; END
        $$;
        DROP TRIGGER IF EXISTS reject_one_shot_success
          ON omi_memory.memory_work_outbox_events;
        CREATE TRIGGER reject_one_shot_success
        BEFORE INSERT ON omi_memory.memory_work_outbox_events
        FOR EACH ROW WHEN (NEW.event_kind = 'memory_work_succeeded')
        EXECUTE FUNCTION omi_memory.qualification_reject_one_shot_success()
      `, [], { prepare: false });
      await expect(formationRuntime.runNext(executionContext)).resolves.toMatchObject({
        kind: "stopped", stop_code: "storage_retryable", leased: 1,
      });
    } finally {
      await ownerSql.unsafe(`
        DROP TRIGGER IF EXISTS reject_one_shot_success
          ON omi_memory.memory_work_outbox_events;
        DROP FUNCTION IF EXISTS omi_memory.qualification_reject_one_shot_success()
      `, [], { prepare: false });
    }
    expect(runtimeModelCalls).toBeGreaterThan(0);
    const callsAfterStaging = runtimeModelCalls;
    const stagedAfterProcessLoss = await ownerSql.unsafe<{
      staged_results: number; successes: number; state: string;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_work_staged_results
          WHERE account_id = $1 AND job_id = $2) AS staged_results,
        (SELECT count(*)::int FROM omi_memory.memory_work_success_results
          WHERE account_id = $1 AND job_id = $2) AS successes,
        (SELECT s.state FROM omi_memory.memory_work_heads AS h
          JOIN omi_memory.memory_work_state_revisions AS s
            ON s.account_id = h.account_id AND s.job_id = h.job_id
           AND s.state_revision = h.state_revision
          WHERE h.account_id = $1 AND h.job_id = $2) AS state
    `, [accountId, runtimeSnapshot.work_id]);
    expect([...stagedAfterProcessLoss]).toEqual([{
      staged_results: 1, successes: 0, state: "leased",
    }]);

    await Bun.sleep(3_100);
    await expect(formationRuntime.recoverExpired(executionContext, runtimeSnapshot.work_id))
      .resolves.toMatchObject({
        kind: "recovered",
        job: { state: "retryable_failed", outcome: { error_code: "worker_lost" } },
      });
    await Bun.sleep(2_100);
    await expect(formationRuntime.runNext(executionContext)).resolves.toMatchObject({
      kind: "completed", result: "succeeded", leased: 1,
      producer_calls: 0, materialization_attempts: 1,
    });
    expect(runtimeModelCalls).toBe(callsAfterStaging);
    expect(backlogEvents.filter((event) => event.family === "worker")).toEqual([{
      version: "operational-telemetry-v1", family: "worker", work_kind: "formation",
      stage: "append", outcome: "success", duration_ms: expect.any(Number), attempt: 2,
      producer_calls: 0, materialization_attempts: 1,
    }]);
    const oneShotCommitted = await ownerSql.unsafe<{
      staged_results: number; successes: number; success_outbox: number;
      formation_outcomes: number; graph_sequence: string;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_work_staged_results
          WHERE account_id = $1 AND job_id = $2) AS staged_results,
        (SELECT count(*)::int FROM omi_memory.memory_work_success_results
          WHERE account_id = $1 AND job_id = $2) AS successes,
        (SELECT count(*)::int FROM omi_memory.memory_work_outbox_events
          WHERE account_id = $1 AND job_id = $2
            AND event_kind = 'memory_work_succeeded') AS success_outbox,
        (SELECT count(*)::int FROM omi_memory.memory_formation_outcomes
          WHERE account_id = $1 AND formation_work_id = $2) AS formation_outcomes,
        (SELECT sequence::text FROM omi_memory.memory_graph_heads
          WHERE account_id = $1) AS graph_sequence
    `, [accountId, runtimeSnapshot.work_id]);
    expect([...oneShotCommitted]).toEqual([{
      staged_results: 1, successes: 1, success_outbox: 1,
      formation_outcomes: 1, graph_sequence: "2",
    }]);

    const predicateStrategy = registerMemoryStrategy({
      version: MEMORY_STRATEGY_VERSION,
      strategy_id: `strategy:predicate:${suffix}`,
      work_kind: "predicate_batch",
      coordinates: {
        strategy_version: "predicate-alignment-v3",
        model_version: "model:qualification:v1",
        prompt_version: "predicate-prompt-v2",
        policy_version: "predicate-policy-v1",
        code_version: "relations-exhaustive-v3",
        schema_version: "predicate-response-v2",
        tokenizer_version: "none",
        tool_version: "none",
        result_contract_version: DURABLE_MEMORY_GRAPH_PLAN_VERSION,
        speaker_strategy_version: "none",
        boundary_strategy_version: "none",
      },
    });
    const predicatePolicy = defineMemoryStrategyAssignmentPolicy({
      policy_id: `policy:predicate:${suffix}`,
      work_kind: "predicate_batch",
      unit_kind: "account",
      key_version: "assignment-key:qualification:v1",
      authority_strategy_id: predicateStrategy.strategy_id,
      shadow_candidates: [],
    }, [predicateStrategy]);
    const predicateAssignment = createMemoryStrategyAssigner(new Uint8Array(32).fill(29)).assign({
      owner_account_id: accountId,
      unit_ref: accountId,
      policy: predicatePolicy,
      strategies: [predicateStrategy],
    });
    const predicateExecutionPolicy = registerDurableMemoryWorkExecutionPolicy({
      version: DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
      policy_id: `execution-policy:predicate:${suffix}`,
      work_kind: "predicate_batch",
      execution_contract_digest: predicateStrategy.execution_contract_digest,
      max_attempts: 2,
      lease_duration_seconds: 30,
      retry_delays_seconds: [1],
    });
    const predicate = (name: string): Predicate => predicateRevisionForObservation({
      owner_account_id: accountId,
      predicate_id: predicateIdForName(name),
      display_name: name,
      roles: ["subject"],
      lifecycle: "canonical",
    }).predicate;
    const predicateSnapshot = {
      version: PREDICATE_BATCH_SCHEDULING_SNAPSHOT_VERSION,
      owner_account_id: accountId,
      input_frontier: "graph:predicate:qualification:one",
      predicates: [predicate("uses"), predicate("works_with")],
      successful_questions: [],
    } as const;
    const predicateInputRepository = createPostgresPredicateBatchWorkInputRepository({
      pool: appRolePool,
    });
    const predicateScheduler = definePredicateBatchWorkScheduler(
      repository,
      predicateInputRepository,
    );
    const predicateScheduleRequest = {
      snapshot: predicateSnapshot,
      strategy_assignment: predicateAssignment,
      execution_policy: predicateExecutionPolicy,
      accepted_at_event_time: now,
      max_jobs_per_invocation: 1,
    } as const;

    const missingInputScheduler = definePredicateBatchWorkScheduler(
      repository,
      definePredicateBatchWorkInputRepository({
        async stage(_authorized, request) {
          return { kind: "staged", input: materializeStagedPredicateBatchWorkInput(request) };
        },
        async load() { return { kind: "not_found" }; },
      }),
    );
    const missingInput = await missingInputScheduler.schedule(context, predicateScheduleRequest);
    expect(missingInput).toMatchObject({
      kind: "halted", scheduled: [], halt: { code: "repository_unavailable" },
    });
    const missingInputJobId = missingInput.halt?.job_id;
    if (!missingInputJobId) throw new Error("qualification_missing_unstaged_predicate_job");
    const rejectedUnstaged = await ownerSql.unsafe<{
      staged_inputs: number; acceptances: number;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_predicate_batch_work_inputs
          WHERE account_id = $1 AND job_id = $2) AS staged_inputs,
        (SELECT count(*)::int FROM omi_memory.memory_work_acceptances
          WHERE account_id = $1 AND job_id = $2) AS acceptances
    `, [accountId, missingInputJobId]);
    expect([...rejectedUnstaged]).toEqual([{ staged_inputs: 0, acceptances: 0 }]);

    try {
      await ownerSql.unsafe(`
        CREATE OR REPLACE FUNCTION omi_memory.qualification_reject_predicate_acceptance()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'qualification injected predicate acceptance rollback'; END
        $$;
        DROP TRIGGER IF EXISTS reject_predicate_acceptance
          ON omi_memory.memory_work_state_revisions;
        CREATE TRIGGER reject_predicate_acceptance
        AFTER INSERT ON omi_memory.memory_work_state_revisions
        FOR EACH ROW EXECUTE FUNCTION omi_memory.qualification_reject_predicate_acceptance()
      `, [], { prepare: false });
      await expect(predicateScheduler.schedule(context, predicateScheduleRequest))
        .resolves.toMatchObject({
          kind: "halted",
          scheduled: [],
          halt: { code: "repository_unavailable" },
        });
    } finally {
      await ownerSql.unsafe(`
        DROP TRIGGER IF EXISTS reject_predicate_acceptance
          ON omi_memory.memory_work_state_revisions;
        DROP FUNCTION IF EXISTS omi_memory.qualification_reject_predicate_acceptance()
      `, [], { prepare: false });
    }
    const predicateJob = (await predicateScheduler.schedule(context, predicateScheduleRequest));
    expect(predicateJob).toMatchObject({
      kind: "accepted",
      scheduled: [{ acceptance: "accepted" }],
    });
    const predicateJobId = predicateJob.scheduled[0]?.job_id;
    if (!predicateJobId) throw new Error("qualification_missing_predicate_job");
    expect(predicateJobId).toBe(missingInputJobId);
    const predicatePersisted = await ownerSql.unsafe<{
      staged_inputs: number; acceptances: number;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_predicate_batch_work_inputs
          WHERE account_id = $1 AND job_id = $2) AS staged_inputs,
        (SELECT count(*)::int FROM omi_memory.memory_work_acceptances
          WHERE account_id = $1 AND job_id = $2) AS acceptances
    `, [accountId, predicateJobId]);
    expect([...predicatePersisted]).toEqual([{ staged_inputs: 1, acceptances: 1 }]);
    await expect(predicateScheduler.schedule(context, predicateScheduleRequest))
      .resolves.toMatchObject({ scheduled: [{ job_id: predicateJobId, acceptance: "replayed" }] });
    await expect(predicateScheduler.schedule(context, {
      ...predicateScheduleRequest,
      accepted_at_event_time: now + 1,
    })).resolves.toMatchObject({
      kind: "halted",
      scheduled: [],
      halt: { job_id: predicateJobId, code: "idempotency_conflict" },
    });

    const predicateLease = await executionRepository.leaseNext(executionContext, {
      work_kinds: ["predicate_batch"],
    });
    expect(predicateLease).toMatchObject({
      kind: "leased", job: { job_id: predicateJobId, state: "leased" },
    });
    if (predicateLease.kind !== "leased") throw new Error("qualification_missing_predicate_lease");
    await expect(predicateInputRepository.load(executionContext, predicateLease.job))
      .resolves.toMatchObject({
        kind: "found",
        snapshot: { job_id: predicateJobId, predicates: [{}, {}] },
      });
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(`SELECT * FROM omi_memory.memory_predicate_batch_work_inputs
        WHERE account_id = $1`, [accountId]);
    })).rejects.toMatchObject({ code: "42501" });

    const predicateRuntimePolicy = registerDurableMemoryWorkExecutionPolicy({
      version: DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
      policy_id: `execution-policy:predicate-runtime:${suffix}`,
      work_kind: "predicate_batch",
      execution_contract_digest: predicateStrategy.execution_contract_digest,
      max_attempts: 2,
      lease_duration_seconds: 2,
      retry_delays_seconds: [1],
    });
    let predicateModelCalls = 0;
    const predicateRuntime = createPostgresPredicateBatchOneShotRuntime({
      pool: appRolePool,
      strategies: [predicateStrategy],
      resolve_model: async () => new DeterministicFakeModel(() => {
        predicateModelCalls += 1;
        return { assertions: [] };
      }),
      max_parent_rematerializations: 3,
    });
    const predicateRuntimeRequest = {
      snapshot: {
        ...predicateSnapshot,
        input_frontier: "graph:predicate:qualification:runtime",
        predicates: [predicate("alpha_relation"), predicate("bravo_relation")],
      },
      strategy_assignment: predicateAssignment,
      execution_policy: predicateRuntimePolicy,
      accepted_at_event_time: now,
      max_jobs_per_invocation: 1,
    } as const;
    const predicateRuntimeAcceptance = await predicateRuntime.schedule(
      context,
      predicateRuntimeRequest,
    );
    expect(predicateRuntimeAcceptance).toMatchObject({
      kind: "accepted", scheduled: [{ acceptance: "accepted" }],
    });
    const predicateRuntimeJobId = predicateRuntimeAcceptance.scheduled[0]?.job_id;
    if (!predicateRuntimeJobId) throw new Error("qualification_missing_predicate_runtime_job");

    try {
      await ownerSql.unsafe(`
        CREATE OR REPLACE FUNCTION omi_memory.qualification_reject_predicate_success()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'qualification injected predicate process loss'; END
        $$;
        DROP TRIGGER IF EXISTS reject_predicate_success
          ON omi_memory.memory_work_outbox_events;
        CREATE TRIGGER reject_predicate_success
        BEFORE INSERT ON omi_memory.memory_work_outbox_events
        FOR EACH ROW WHEN (NEW.event_kind = 'memory_work_succeeded')
        EXECUTE FUNCTION omi_memory.qualification_reject_predicate_success()
      `, [], { prepare: false });
      await expect(predicateRuntime.runNext(executionContext)).resolves.toMatchObject({
        kind: "stopped", stop_code: "storage_retryable", leased: 1,
      });
    } finally {
      await ownerSql.unsafe(`
        DROP TRIGGER IF EXISTS reject_predicate_success
          ON omi_memory.memory_work_outbox_events;
        DROP FUNCTION IF EXISTS omi_memory.qualification_reject_predicate_success()
      `, [], { prepare: false });
    }
    expect(predicateModelCalls).toBe(1);
    const predicateCallsAfterStaging = predicateModelCalls;
    const predicateStaged = await ownerSql.unsafe<{
      staged_results: number; successes: number; state: string;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_work_staged_results
          WHERE account_id = $1 AND job_id = $2) AS staged_results,
        (SELECT count(*)::int FROM omi_memory.memory_work_success_results
          WHERE account_id = $1 AND job_id = $2) AS successes,
        (SELECT s.state FROM omi_memory.memory_work_heads AS h
          JOIN omi_memory.memory_work_state_revisions AS s
            ON s.account_id = h.account_id AND s.job_id = h.job_id
           AND s.state_revision = h.state_revision
          WHERE h.account_id = $1 AND h.job_id = $2) AS state
    `, [accountId, predicateRuntimeJobId]);
    expect([...predicateStaged]).toEqual([{
      staged_results: 1, successes: 0, state: "leased",
    }]);

    await Bun.sleep(3_100);
    await expect(predicateRuntime.recoverExpired(executionContext, predicateRuntimeJobId))
      .resolves.toMatchObject({
        kind: "recovered",
        job: { state: "retryable_failed", outcome: { error_code: "worker_lost" } },
      });
    await Bun.sleep(2_100);
    await expect(predicateRuntime.runNext(executionContext)).resolves.toMatchObject({
      kind: "completed", result: "succeeded", leased: 1,
      producer_calls: 0, materialization_attempts: 1,
    });
    expect(predicateModelCalls).toBe(predicateCallsAfterStaging);
    const predicateCompleted = await ownerSql.unsafe<{
      staged_results: number; successes: number; success_outbox: number;
      state: string; graph_sequence: string;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_work_staged_results
          WHERE account_id = $1 AND job_id = $2) AS staged_results,
        (SELECT count(*)::int FROM omi_memory.memory_work_success_results
          WHERE account_id = $1 AND job_id = $2) AS successes,
        (SELECT count(*)::int FROM omi_memory.memory_work_outbox_events
          WHERE account_id = $1 AND job_id = $2
            AND event_kind = 'memory_work_succeeded') AS success_outbox,
        (SELECT s.state FROM omi_memory.memory_work_heads AS h
          JOIN omi_memory.memory_work_state_revisions AS s
            ON s.account_id = h.account_id AND s.job_id = h.job_id
           AND s.state_revision = h.state_revision
          WHERE h.account_id = $1 AND h.job_id = $2) AS state,
        (SELECT sequence::text FROM omi_memory.memory_graph_heads
          WHERE account_id = $1) AS graph_sequence
    `, [accountId, predicateRuntimeJobId]);
    expect([...predicateCompleted]).toEqual([{
      staged_results: 1, successes: 1, success_outbox: 1,
      state: "succeeded", graph_sequence: "2",
    }]);

    const assertionPredicates = [
      predicateRevisionForObservation({
        owner_account_id: accountId,
        predicate_id: predicateIdForName("uses"),
        display_name: "uses",
        roles: ["person", "tool"],
        lifecycle: "canonical",
      }).predicate,
      predicateRevisionForObservation({
        owner_account_id: accountId,
        predicate_id: predicateIdForName("operates"),
        display_name: "operates",
        roles: ["person", "tool"],
        lifecycle: "canonical",
      }).predicate,
    ] as const;
    let predicateAssertionModelCalls = 0;
    const predicateAssertionRuntime = createPostgresPredicateBatchOneShotRuntime({
      pool: appRolePool,
      strategies: [predicateStrategy],
      resolve_model: async () => new DeterministicFakeModel(() => {
        predicateAssertionModelCalls += 1;
        return { assertions: [{
          predicate_id: assertionPredicates[0].predicate_id,
          target_predicate_id: assertionPredicates[1].predicate_id,
          slot_aliases: [
            { from_slot_id: "person", to_slot_id: "person" },
            { from_slot_id: "tool", to_slot_id: "tool" },
          ],
        }] };
      }),
      max_parent_rematerializations: 3,
    });
    const predicateAssertionAcceptance = await predicateAssertionRuntime.schedule(context, {
      snapshot: {
        ...predicateSnapshot,
        input_frontier: "graph:predicate:qualification:assertion",
        predicates: assertionPredicates,
      },
      strategy_assignment: predicateAssignment,
      execution_policy: predicateRuntimePolicy,
      accepted_at_event_time: now,
      max_jobs_per_invocation: 1,
    });
    expect(predicateAssertionAcceptance).toMatchObject({
      kind: "accepted", scheduled: [{ acceptance: "accepted" }],
    });
    const predicateAssertionJobId = predicateAssertionAcceptance.scheduled[0]?.job_id;
    if (!predicateAssertionJobId) throw new Error("qualification_missing_predicate_assertion_job");
    await expect(predicateAssertionRuntime.runNext(executionContext)).resolves.toMatchObject({
      kind: "completed", result: "succeeded", leased: 1,
      producer_calls: 1, materialization_attempts: 1,
    });
    expect(predicateAssertionModelCalls).toBe(1);
    const predicateAssertionCommitted = await ownerSql.unsafe<{
      assertions: number; successes: number; state: string; graph_sequence: string;
      predicate_id: string; target_predicate_id: string;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_predicate_assertion_revisions AS a
          JOIN omi_memory.memory_revisions AS r
            ON r.account_id = a.account_id AND r.revision_id = a.revision_id
          WHERE a.account_id = $1 AND r.commit_id = s.graph_commit_id) AS assertions,
        (SELECT count(*)::int FROM omi_memory.memory_work_success_results
          WHERE account_id = $1 AND job_id = $2) AS successes,
        h.state,
        gh.sequence::text AS graph_sequence,
        a.predicate_id,
        a.target_predicate_id
      FROM omi_memory.memory_work_success_results AS s
      JOIN omi_memory.memory_work_heads AS wh
        ON wh.account_id = s.account_id AND wh.job_id = s.job_id
      JOIN omi_memory.memory_work_state_revisions AS h
        ON h.account_id = wh.account_id AND h.job_id = wh.job_id
       AND h.state_revision = wh.state_revision
      JOIN omi_memory.memory_graph_heads AS gh ON gh.account_id = s.account_id
      JOIN omi_memory.memory_predicate_assertion_revisions AS a
        ON a.account_id = s.account_id
      JOIN omi_memory.memory_revisions AS ar
        ON ar.account_id = a.account_id AND ar.revision_id = a.revision_id
       AND ar.commit_id = s.graph_commit_id
      WHERE s.account_id = $1 AND s.job_id = $2
    `, [accountId, predicateAssertionJobId]);
    expect([...predicateAssertionCommitted]).toEqual([{
      assertions: 1, successes: 1, state: "succeeded", graph_sequence: "3",
      predicate_id: assertionPredicates[0].predicate_id,
      target_predicate_id: assertionPredicates[1].predicate_id,
    }]);

    const rollbackSuccessSuffix = `${suffix}:success-rollback`;
    const rollbackSuccessAcceptance = durableWorkAcceptanceRequest(
      accountId, rollbackSuccessSuffix, now, 2, 1,
    );
    await expect(stageInput(rollbackSuccessAcceptance, rollbackSuccessSuffix))
      .resolves.toMatchObject({ kind: "staged" });
    await expect(repository.accept(context, rollbackSuccessAcceptance))
      .resolves.toMatchObject({ kind: "accepted", job: { state: "pending" } });
    const rollbackSuccessLease = await executionRepository.leaseNext(executionContext, {
      work_kinds: ["formation"],
    });
    if (rollbackSuccessLease.kind !== "leased") {
      throw new Error("qualification_missing_rollback_success_lease");
    }
    const rollbackNormalized = { claims: [] };
    const rollbackNormalizedDigest = durableMemoryWorkNormalizedResultDigest(
      successContractVersion, rollbackNormalized,
    );
    const rollbackStageBody: DurableMemoryWorkResultStageBody = {
      leased_job: rollbackSuccessLease.job,
      result_contract_version: successContractVersion,
      response_digest: "9".repeat(64),
      normalized_result_digest: rollbackNormalizedDigest,
      normalized_result: rollbackNormalized,
    };
    const rollbackStage = await resultRepository.stage(executionContext, {
      ...rollbackStageBody,
      request_digest: durableMemoryWorkResultStageRequestDigest(rollbackStageBody),
    });
    if (rollbackStage.kind !== "staged") throw new Error("qualification_missing_rollback_stage");
    const rollbackSuccessBody: DurableMemoryWorkSuccessBody = {
      leased_job: rollbackSuccessLease.job,
      result_kind: "successful_empty",
      response_digest: rollbackStage.result.response_digest,
      result_digest: rollbackStage.result.normalized_result_digest,
      staged_result: rollbackStage.result,
      authoritative_append: null,
    };
    const rollbackSuccessRequest = {
      ...rollbackSuccessBody,
      request_digest: durableMemoryWorkSuccessRequestDigest(rollbackSuccessBody),
    };
    try {
      await ownerSql.unsafe(`
        CREATE OR REPLACE FUNCTION omi_memory.qualification_reject_work_success_outbox()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'qualification injected success rollback'; END
        $$;
        DROP TRIGGER IF EXISTS reject_work_success_outbox
          ON omi_memory.memory_work_outbox_events;
        CREATE TRIGGER reject_work_success_outbox
        BEFORE INSERT ON omi_memory.memory_work_outbox_events
        FOR EACH ROW WHEN (NEW.event_kind = 'memory_work_succeeded')
        EXECUTE FUNCTION omi_memory.qualification_reject_work_success_outbox()
      `, [], { prepare: false });
      await expect(successRepository.commit(executionContext, rollbackSuccessRequest))
        .rejects.toMatchObject({ code: "persistence_failed", message: "persistence_failed" });
      const rolledBackSuccess = await ownerSql.unsafe<{
        state: string; successes: number; success_outbox: number; graph_sequence: string;
      }[]>(`
        SELECT
          (SELECT s.state FROM omi_memory.memory_work_heads AS h
           JOIN omi_memory.memory_work_state_revisions AS s
             ON s.account_id = h.account_id AND s.job_id = h.job_id
            AND s.state_revision = h.state_revision
           WHERE h.account_id = $1 AND h.job_id = $2) AS state,
          (SELECT count(*)::int FROM omi_memory.memory_work_success_results
           WHERE account_id = $1 AND job_id = $2) AS successes,
          (SELECT count(*)::int FROM omi_memory.memory_work_outbox_events
           WHERE account_id = $1 AND job_id = $2) AS success_outbox,
          (SELECT sequence::text FROM omi_memory.memory_graph_heads
           WHERE account_id = $1) AS graph_sequence
      `, [accountId, rollbackSuccessLease.job.job_id]);
      expect([...rolledBackSuccess]).toEqual([{
        state: "leased", successes: 0, success_outbox: 0, graph_sequence: "3",
      }]);
    } finally {
      await ownerSql.unsafe(`
        DROP TRIGGER IF EXISTS reject_work_success_outbox
          ON omi_memory.memory_work_outbox_events;
        DROP FUNCTION IF EXISTS omi_memory.qualification_reject_work_success_outbox()
      `, [], { prepare: false }).catch(() => undefined);
    }

    const executionRows = await ownerSql.unsafe<{
      dead_letters: number; retryable_failures: number; outbox: number;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_work_state_revisions
          WHERE account_id = $1 AND state = 'dead_letter') AS dead_letters,
        (SELECT count(*)::int FROM omi_memory.memory_work_state_revisions
          WHERE account_id = $1 AND state = 'retryable_failed') AS retryable_failures,
        (SELECT count(*)::int FROM omi_memory.memory_work_outbox_events
          WHERE account_id = $1 AND event_kind = 'memory_work_dead_letter') AS outbox
    `, [accountId]);
    expect([...executionRows]).toEqual([{
      dead_letters: 2, retryable_failures: 4, outbox: 2,
    }]);
    for (const forbiddenSql of [
      "UPDATE omi_memory.memory_work_state_revisions SET state = 'pending' WHERE account_id = $1",
      "DELETE FROM omi_memory.memory_work_outbox_events WHERE account_id = $1",
    ]) {
      await expect(ownerSql.begin(async (transaction) => {
        await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
        await transaction.unsafe(forbiddenSql, [accountId]);
      })).rejects.toMatchObject({ code: "42501" });
    }

    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 4, 'memories.work.execute', $4, 2, 'revoked', false,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
      [accountId, applicationId, credentialId, executeGrantId, "f".repeat(64)]);
      await transaction.unsafe(`UPDATE omi_memory.application_grant_heads
        SET grant_version = 2, updated_at = transaction_timestamp()
        WHERE account_id = $1 AND application_id = $2 AND credential_id = $3
          AND credential_generation = 4 AND capability = 'memories.work.execute'`,
      [accountId, applicationId, credentialId]);
    });
    await expect(executionRepository.load(executionContext, {
      job_id: acceptedRequest.accepted_work.job_id,
    })).resolves.toEqual({ kind: "authorization_denied", reason: "grant_inactive" });
    const priorBacklogEventCount = backlogEvents.length;
    await expect(emitDurableMemoryWorkBacklogTelemetry(
      backlogSource, executionContext, backlogTelemetry,
    )).resolves.toEqual({ kind: "unavailable" });
    expect(backlogEvents.slice(priorBacklogEventCount)).toEqual(
      ["formation", "promotion", "identity_cluster", "predicate_batch"].map((work_kind) => ({
        version: "operational-telemetry-v1", family: "backlog", work_kind,
        outcome: "unavailable", ready: null, leased: null, retry_wait: null, dead: null,
        oldest_ready_age_ms: null,
      })),
    );

    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 4, 'memories.work.accept', $4, 10, 'revoked', false,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
      [accountId, applicationId, credentialId, grantId, "d".repeat(64)]);
      await transaction.unsafe(`UPDATE omi_memory.application_grant_heads
        SET grant_version = 10, updated_at = transaction_timestamp()
        WHERE account_id = $1 AND application_id = $2 AND credential_id = $3
          AND credential_generation = 4 AND capability = 'memories.work.accept'`,
      [accountId, applicationId, credentialId]);
    });
    await expect(repository.accept(context, acceptedRequest)).resolves.toEqual({
      kind: "authorization_denied", reason: "grant_inactive",
    });
  }, 120_000);

  test("application-role authority adapter commits empty, graph, and formation work with exact replay and rollback", async () => {
    const suffix = randomUUID();
    const accountId = `account:pg-kernel:${suffix}`;
    const principalId = `principal:pg-kernel:${suffix}`;
    const applicationId = "app:qualification";
    const credentialId = `credential:${suffix}`;
    const grantId = `grant:${suffix}`;
    const readGrantId = `grant:${suffix}:read`;
    const firebaseProjectId = `firebase-project-${suffix}`;
    const firebaseUid = `firebase-user-${suffix}`;
    const controlHash = "1".repeat(64);
    const credentialHash = "2".repeat(64);
    const grantHash = "3".repeat(64);
    const readGrantHash = "5".repeat(64);
    const now = Math.floor(Date.now() / 1_000);

    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(
        "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)",
        [accountId],
      );
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
          (account_id, control_revision, account_generation, account_epoch,
           lifecycle_state, deletion_epoch, observed_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, 17, 'new', 12, 'active', NULL, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountId, controlHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
          (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 17, 12, 17)`, [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_revisions
          (account_id, principal_id, application_id, credential_id,
           credential_generation, credential_kind, lifecycle,
           authentication_strength, expires_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, $2, $3, $4, 4, 'firebase', 'active', 'firebase-id-token',
                to_timestamp($5), 'credential-v1', '{}'::jsonb, $6)`,
      [accountId, principalId, applicationId, credentialId, now + 7_200, credentialHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_heads
          (account_id, application_id, credential_id, credential_generation)
        VALUES ($1, $2, $3, 4)`, [accountId, applicationId, credentialId]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 4, 'memories.write', $4, 9, 'active', true,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
      [accountId, applicationId, credentialId, grantId, grantHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_heads
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version)
        VALUES ($1, $2, $3, 4, 'memories.write', $4, 9)`,
      [accountId, applicationId, credentialId, grantId]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 4, 'memories.read', $4, 1, 'active', true,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
      [accountId, applicationId, credentialId, readGrantId, readGrantHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_heads
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version)
        VALUES ($1, $2, $3, 4, 'memories.read', $4, 1)`,
      [accountId, applicationId, credentialId, readGrantId]);
      await transaction.unsafe(`INSERT INTO omi_memory.firebase_identity_bindings
          (firebase_project_id, firebase_uid, account_id, principal_id,
           source_control_revision)
        VALUES ($1, $2, $3, $4, 17)`,
      [firebaseProjectId, firebaseUid, accountId, principalId]);
      await transaction.unsafe(`INSERT INTO omi_memory.firebase_application_credential_bindings
          (account_id, firebase_project_id, firebase_uid, principal_id,
           application_id, credential_id)
        VALUES ($1, $2, $3, $4, $5, $6)`,
      [accountId, firebaseProjectId, firebaseUid, principalId, applicationId, credentialId]);
    });

    const authorityRow: AuthorityStateRow = {
      account_id: accountId,
      principal_id: principalId,
      application_id: applicationId,
      credential_id: credentialId,
      credential_generation: 4,
      capability: "memories.write",
      grant_id: grantId,
      grant_version: 9,
      account_epoch: 12,
      control_conflict_reason: null,
      control_conflict_at_revision: null,
      destination_activation_epoch: 12,
      destination_activation_revision: 17,
      lifecycle_state: "active",
      deletion_epoch: null,
      account_generation: "new",
      credential_lifecycle: "active",
      grant_lifecycle: "active",
      grant_enabled: true,
      authentication_strength: "firebase-id-token",
      credential_expires_at_epoch_seconds: now + 7_200,
      control_revision: 17,
      control_content_hash: controlHash,
      credential_content_hash: credentialHash,
      grant_content_hash: grantHash,
      db_now_epoch_seconds: now,
    };
    const context = createAuthorizedLedgerWriteContextIssuer().issue({
      context_version: "authorized-ledger-write-context-v1",
      principal_id: principalId,
      account_id: accountId,
      application_id: applicationId,
      credential_id: credentialId,
      credential_generation: 4,
      capability: "memories.write",
      grant_id: grantId,
      grant_version: 9,
      account_epoch: 12,
      destination_activation_revision: 17,
      lifecycle_state: "active",
      deletion_epoch: null,
      authentication_strength: "firebase-id-token",
      issued_at_epoch_seconds: now - 60,
      expires_at_epoch_seconds: now + 3_600,
      authorization_state_digest: authorizationStateDigest(authorityRow),
    }, now);

    const accountB = `account:pg-kernel-b:${suffix}`;
    const principalB = `principal:pg-kernel-b:${suffix}`;
    const credentialB = `credential:b:${suffix}`;
    const grantB = `grant:b:${suffix}`;
    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(
        "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)", [accountB],
      );
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
          (account_id, control_revision, account_generation, account_epoch,
           lifecycle_state, deletion_epoch, observed_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, 17, 'new', 12, 'active', NULL, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountB, controlHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
          (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 17, 12, 17)`, [accountB]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_revisions
          (account_id, principal_id, application_id, credential_id,
           credential_generation, credential_kind, lifecycle,
           authentication_strength, expires_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, $2, $3, $4, 4, 'firebase', 'active', 'firebase-id-token',
                to_timestamp($5), 'credential-v1', '{}'::jsonb, $6)`,
      [accountB, principalB, applicationId, credentialB, now + 7_200, credentialHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_heads
          (account_id, application_id, credential_id, credential_generation)
        VALUES ($1, $2, $3, 4)`, [accountB, applicationId, credentialB]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 4, 'memories.write', $4, 9, 'active', true,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
      [accountB, applicationId, credentialB, grantB, grantHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_heads
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version)
        VALUES ($1, $2, $3, 4, 'memories.write', $4, 9)`,
      [accountB, applicationId, credentialB, grantB]);
    });
    const authorityRowB: AuthorityStateRow = {
      ...authorityRow, account_id: accountB, principal_id: principalB,
      credential_id: credentialB, grant_id: grantB,
    };
    const contextB = createAuthorizedLedgerWriteContextIssuer().issue({
      context_version: "authorized-ledger-write-context-v1",
      principal_id: principalB, account_id: accountB, application_id: applicationId,
      credential_id: credentialB, credential_generation: 4, capability: "memories.write",
      grant_id: grantB, grant_version: 9, account_epoch: 12,
      destination_activation_revision: 17, lifecycle_state: "active", deletion_epoch: null,
      authentication_strength: "firebase-id-token", issued_at_epoch_seconds: now - 60,
      expires_at_epoch_seconds: now + 3_600,
      authorization_state_digest: authorizationStateDigest(authorityRowB),
    }, now);

    let lastRepositoryStatement = "none";
    let lastProviderCode = "none";
    let lastProviderConstraint = "none";
    const appRolePool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(options: Parameters<PostgresTransactionPool["withTransaction"]>[0], callback: (connection: CheckedOutPostgresConnection) => Promise<Result>) =>
        pool.withTransaction(options, async (connection) => {
          await connection.query({
            name: "qualification.set_application_role",
            text: "SET LOCAL ROLE omi_platform_application",
            values: [],
          });
          const roles = await connection.query<{ current_user: string }>({
            name: "qualification.assert_application_role",
            text: "SELECT current_user",
            values: [],
          });
          expect(roles).toEqual([{ current_user: "omi_platform_application" }]);
          const tracked: CheckedOutPostgresConnection = Object.freeze({
            connectionIdentity: connection.connectionIdentity,
            query: async <Row extends Record<string, unknown>>(statement: Parameters<CheckedOutPostgresConnection["query"]>[0]) => {
              lastRepositoryStatement = statement.name;
              return connection.query<Row>(statement);
            },
            execute: async (statement: SqlStatement) => {
              lastRepositoryStatement = statement.name;
              try {
                return await connection.execute(statement);
              } catch (error) {
                const code = error && typeof error === "object" ? Reflect.get(error, "code") : null;
                const constraint = error && typeof error === "object" ? Reflect.get(error, "constraint_name") : null;
                lastProviderCode = typeof code === "string" ? code : "unknown";
                lastProviderConstraint = typeof constraint === "string" ? constraint : "unknown";
                throw error;
              }
            },
          });
          return callback(tracked);
        }),
    });
    const repository = createPostgresSuccessfulEmptyLedgerRepository({ pool: appRolePool });
    const append = (
      commitId: string,
      key: string,
      parent: string | null,
      ownerAccountId = accountId,
    ): AuthoritativeLedgerAppend => {
      const transition: AtomicGraphTransition = {
        placement: { offline_experiment: true, allocations: {}, results: [] },
        derivation: prepareDerivation({
          attempt_id: `attempt:${commitId}`,
          commit_id: commitId,
          owner_account_id: ownerAccountId,
          parent_commit: parent,
          idempotency_key: key,
          input_revisions: [],
          output_revisions: [],
          versions: {
            strategy_version: "qualification-v1", model_version: "none", prompt_version: "none",
            policy_version: "qualification-v1", code_version: "qualification-v1",
            schema_version: "qualification-v1", tokenizer_version: "none", tool_version: "qualification-v1",
          },
          success_kind: "successful_empty",
        }),
        revisions: [], adjacency: [], artifacts: [],
      };
      const origin = { kind: "non_formation" as const, reason: "repair" as const };
      return {
        append_attempt: {
          idempotency_key: key,
          expected_parent_commit: parent,
          request_digest: authoritativeAppendRequestDigest(transition, origin),
        },
        origin,
        transition,
      };
    };

    const first = append(`commit:${suffix}:one`, `append:${suffix}:same`, null);
    try {
      expect(await repository.append(context, first)).toEqual({
        kind: "committed", commit_id: first.transition.derivation.commit.commit_id, sequence: 1,
      });
    } catch (error) {
      const code = error && typeof error === "object" && "code" in error
        ? String(Reflect.get(error, "code")) : "assertion_or_unknown";
      throw new Error(`kernel_real_failure_at:${lastRepositoryStatement}:${lastProviderCode}:${lastProviderConstraint}:${code}`);
    }
    await expect(repository.append(context, first)).resolves.toEqual({
      kind: "replayed", commit_id: first.transition.derivation.commit.commit_id, sequence: 1,
    });
    const changed = append(`commit:${suffix}:changed`, first.append_attempt.idempotency_key, null);
    await expect(repository.append(context, changed)).resolves.toEqual({ kind: "idempotency_conflict" });
    const stale = append(`commit:${suffix}:stale`, `append:${suffix}:stale`, null);
    await expect(repository.append(context, stale)).resolves.toEqual({ kind: "stale_parent" });

    const persisted = await ownerSql.unsafe<{
      attempts: number; commits: number; receipts: number; head_sequence: string;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_derivation_attempts WHERE account_id = $1) AS attempts,
        (SELECT count(*)::int FROM omi_memory.memory_derivation_commits WHERE account_id = $1) AS commits,
        (SELECT count(*)::int FROM omi_memory.memory_idempotency_receipts WHERE account_id = $1) AS receipts,
        (SELECT sequence::text FROM omi_memory.memory_graph_heads WHERE account_id = $1) AS head_sequence
    `, [accountId]);
    expect([...persisted]).toEqual([{ attempts: 1, commits: 1, receipts: 1, head_sequence: "1" }]);

    const sameKeyOtherAccount = append(
      `commit:${suffix}:account-b`, first.append_attempt.idempotency_key, null, accountB,
    );
    await expect(repository.append(contextB, sameKeyOtherAccount)).resolves.toEqual({
      kind: "committed",
      commit_id: sameKeyOtherAccount.transition.derivation.commit.commit_id,
      sequence: 1,
    });
    const isolatedReceipts = await ownerSql.unsafe<{ account_id: string; count: number }[]>(`
      SELECT account_id, count(*)::int AS count
      FROM omi_memory.memory_idempotency_receipts
      WHERE account_id IN ($1, $2) AND idempotency_key = $3
      GROUP BY account_id ORDER BY account_id
    `, [accountId, accountB, first.append_attempt.idempotency_key]);
    expect(isolatedReceipts).toHaveLength(2);
    expect([...isolatedReceipts]).toEqual(expect.arrayContaining([
      { account_id: accountId, count: 1 },
      { account_id: accountB, count: 1 },
    ]));

    const racePhysicalPool = createPostgresJsTransactionPool({
      connectionString: explicitTestUrl!, maxConnections: 2,
    });
    const raceRolePool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(
        options: Parameters<PostgresTransactionPool["withTransaction"]>[0],
        callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
      ) => racePhysicalPool.withTransaction(options, async (connection) => {
        await connection.query({
          name: "qualification.race_set_application_role",
          text: "SET LOCAL ROLE omi_platform_application", values: [],
        });
        return callback(connection);
      }),
    });
    try {
      const raceRepository = createPostgresSuccessfulEmptyLedgerRepository({ pool: raceRolePool });
      const raceParent = sameKeyOtherAccount.transition.derivation.commit.commit_id;
      const contenders = [
        append(`commit:${suffix}:race-a`, `append:${suffix}:race-a`, raceParent, accountB),
        append(`commit:${suffix}:race-b`, `append:${suffix}:race-b`, raceParent, accountB),
      ];
      const outcomes = await Promise.all(contenders.map((contender) =>
        raceRepository.append(contextB, contender)));
      expect(outcomes.filter((outcome) => outcome.kind === "committed")).toHaveLength(1);
      expect(outcomes.filter((outcome) =>
        outcome.kind === "stale_parent" || outcome.kind === "serialization_retryable"))
        .toHaveLength(1);
      const raceRows = await ownerSql.unsafe<{
        attempts: number; commits: number; receipts: number; head_sequence: string;
      }[]>(`
        SELECT
          (SELECT count(*)::int FROM omi_memory.memory_derivation_attempts WHERE account_id = $1) AS attempts,
          (SELECT count(*)::int FROM omi_memory.memory_derivation_commits WHERE account_id = $1) AS commits,
          (SELECT count(*)::int FROM omi_memory.memory_idempotency_receipts WHERE account_id = $1) AS receipts,
          (SELECT sequence::text FROM omi_memory.memory_graph_heads WHERE account_id = $1) AS head_sequence
      `, [accountB]);
      expect([...raceRows]).toEqual([{ attempts: 2, commits: 2, receipts: 2, head_sequence: "2" }]);
    } finally {
      await racePhysicalPool.close();
    }

    for (const forbiddenSql of [
      "CREATE TABLE omi_memory.qualification_forbidden (id integer)",
      "DELETE FROM omi_memory.memory_derivation_attempts WHERE account_id = $1",
      "UPDATE omi_memory.memory_derivation_attempts SET success_kind = 'success' WHERE account_id = $1",
    ]) {
      await expect(ownerSql.begin(async (transaction) => {
        await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
        await transaction.unsafe(forbiddenSql, forbiddenSql.includes("$1") ? [accountId] : []);
      })).rejects.toMatchObject({ code: "42501" });
    }

    const graphRepository = createPostgresAuthoritativeLedgerRepository({ pool: appRolePool });
    const graph = nonemptyAppend(
      accountId, suffix, first.transition.derivation.commit.commit_id,
    );
    await expect(graphRepository.append(context, graph)).resolves.toEqual({
      kind: "committed", commit_id: graph.transition.derivation.commit.commit_id, sequence: 2,
    });
    await expect(graphRepository.append(context, graph)).resolves.toEqual({
      kind: "replayed", commit_id: graph.transition.derivation.commit.commit_id, sequence: 2,
    });
    const graphRows = await ownerSql.unsafe<{
      revisions: number; events: number; evidence: number; claims: number;
      consumed: number; artifacts: number; head_sequence: string;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_revisions WHERE account_id = $1) AS revisions,
        (SELECT count(*)::int FROM omi_memory.memory_event_revisions WHERE account_id = $1) AS events,
        (SELECT count(*)::int FROM omi_memory.memory_evidence_revisions WHERE account_id = $1) AS evidence,
        (SELECT count(*)::int FROM omi_memory.memory_claim_revisions WHERE account_id = $1) AS claims,
        (SELECT count(*)::int FROM omi_memory.memory_consumed_markers WHERE account_id = $1) AS consumed,
        (SELECT count(*)::int FROM omi_memory.memory_placement_artifacts WHERE account_id = $1) AS artifacts,
        (SELECT sequence::text FROM omi_memory.memory_graph_heads WHERE account_id = $1) AS head_sequence
    `, [accountId]);
    expect([...graphRows]).toEqual([{
      revisions: 3, events: 1, evidence: 1, claims: 1,
      consumed: 1, artifacts: 1, head_sequence: "2",
    }]);

    const formation = formationAppend(
      accountId, `${suffix}:formation`, graph.transition.derivation.commit.commit_id,
    );
    await expect(graphRepository.append(context, formation)).resolves.toEqual({
      kind: "committed",
      commit_id: formation.transition.derivation.commit.commit_id,
      sequence: 3,
    });
    await expect(graphRepository.append(context, formation)).resolves.toEqual({
      kind: "replayed",
      commit_id: formation.transition.derivation.commit.commit_id,
      sequence: 3,
    });
    const formationRows = await ownerSql.unsafe<{
      inputs: number; outcomes: number; extractions: number; evidence: number; placements: number;
      head_sequence: string;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_derivation_inputs WHERE account_id = $1) AS inputs,
        (SELECT count(*)::int FROM omi_memory.memory_formation_outcomes WHERE account_id = $1) AS outcomes,
        (SELECT count(*)::int FROM omi_memory.memory_formation_extraction_outcomes WHERE account_id = $1) AS extractions,
        (SELECT count(*)::int FROM omi_memory.memory_formation_extraction_evidence WHERE account_id = $1) AS evidence,
        (SELECT count(*)::int FROM omi_memory.memory_formation_placement_outcomes WHERE account_id = $1) AS placements,
        (SELECT sequence::text FROM omi_memory.memory_graph_heads WHERE account_id = $1) AS head_sequence
    `, [accountId]);
    expect([...formationRows]).toEqual([{
      inputs: 1, outcomes: 1, extractions: 1, evidence: 1, placements: 1,
      head_sequence: "3",
    }]);

    const identity = identityAppend(
      accountId, `${suffix}:identity`, formation.transition.derivation.commit.commit_id,
    );
    await expect(graphRepository.append(context, identity)).resolves.toEqual({
      kind: "committed",
      commit_id: identity.transition.derivation.commit.commit_id,
      sequence: 4,
    });
    await expect(graphRepository.append(context, identity)).resolves.toEqual({
      kind: "replayed",
      commit_id: identity.transition.derivation.commit.commit_id,
      sequence: 4,
    });
    const identityRows = await ownerSql.unsafe<{
      authorizations: number; authorization_endpoints: number; mentions: number;
      identities: number; identity_endpoints: number; adjacency: number;
      claim_sources: number; head_sequence: string;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_identity_authorization_revisions WHERE account_id = $1) AS authorizations,
        (SELECT count(*)::int FROM omi_memory.memory_identity_authorization_entity_endpoints WHERE account_id = $1) AS authorization_endpoints,
        (SELECT count(*)::int FROM omi_memory.memory_mention_revisions WHERE account_id = $1) AS mentions,
        (SELECT count(*)::int FROM omi_memory.memory_identity_revisions WHERE account_id = $1) AS identities,
        (SELECT count(*)::int FROM omi_memory.memory_identity_constraint_entity_endpoints WHERE account_id = $1) AS identity_endpoints,
        (SELECT count(*)::int FROM omi_memory.memory_generated_adjacency WHERE account_id = $1) AS adjacency,
        (SELECT count(*)::int FROM omi_memory.memory_claim_source_provisionals WHERE account_id = $1) AS claim_sources,
        (SELECT sequence::text FROM omi_memory.memory_graph_heads WHERE account_id = $1) AS head_sequence
    `, [accountId]);
    expect([...identityRows]).toEqual([{
      authorizations: 1, authorization_endpoints: 1, mentions: 1,
      identities: 1, identity_endpoints: 1, adjacency: 1,
      claim_sources: 1, head_sequence: "4",
    }]);

    const livenessWitness = identity.transition.revisions.find(
      (revision) => revision.kind === "claim" && revision.placement_status === "canonical",
    )!;
    if (livenessWitness.kind !== "claim") throw new Error("missing liveness claim witness");
    const livenessTransition: AtomicGraphTransition = {
      placement: { offline_experiment: true, allocations: {}, results: [] },
      derivation: prepareDerivation({
        attempt_id: `attempt:liveness:${suffix}`, commit_id: `commit:liveness:${suffix}`,
        owner_account_id: accountId,
        parent_commit: identity.transition.derivation.commit.commit_id,
        idempotency_key: `append:liveness:${suffix}`,
        input_revisions: [{ revision_id: livenessWitness.revision_id, content: livenessWitness.claim }],
        output_revisions: [], versions: identity.transition.derivation.commit.versions,
        success_kind: "success",
      }),
      revisions: [], adjacency: [], artifacts: [], committed_revisions: [livenessWitness],
      liveness_fences: [{ claim_revision_id: livenessWitness.revision_id, cause: "purged" }],
    };
    const livenessOrigin = { kind: "non_formation" as const, reason: "manual_liveness" as const };
    const liveness: AuthoritativeLedgerAppend = {
      append_attempt: {
        idempotency_key: livenessTransition.derivation.commit.idempotency_key,
        expected_parent_commit: livenessTransition.derivation.commit.parent_commit,
        request_digest: authoritativeAppendRequestDigest(livenessTransition, livenessOrigin),
      },
      origin: livenessOrigin, transition: livenessTransition,
    };
    await expect(graphRepository.append(context, liveness)).resolves.toEqual({
      kind: "committed", commit_id: livenessTransition.derivation.commit.commit_id, sequence: 5,
    });
    await expect(graphRepository.append(context, liveness)).resolves.toEqual({
      kind: "replayed", commit_id: livenessTransition.derivation.commit.commit_id, sequence: 5,
    });
    const livenessRows = await ownerSql.unsafe<{
      claim_revision_id: string; cause: string; commit_id: string; head_sequence: string;
    }[]>(`
      SELECT f.claim_revision_id, f.cause, f.commit_id, h.sequence::text AS head_sequence
      FROM omi_memory.memory_claim_liveness_fences AS f
      JOIN omi_memory.memory_graph_heads AS h ON h.account_id = f.account_id
      WHERE f.account_id = $1
    `, [accountId]);
    expect([...livenessRows]).toEqual([{
      claim_revision_id: livenessWitness.revision_id, cause: "purged",
      commit_id: livenessTransition.derivation.commit.commit_id, head_sequence: "5",
    }]);

    const snapshotPhysicalPool = createPostgresJsTransactionPool({
      connectionString: explicitTestUrl!, maxConnections: 1,
    });
    const snapshotRolePool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(
        options: Parameters<PostgresTransactionPool["withTransaction"]>[0],
        callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
      ) => snapshotPhysicalPool.withTransaction(options, async (connection) => {
        await connection.query({
          name: "qualification.snapshot_set_application_role",
          text: "SET LOCAL ROLE omi_platform_application", values: [],
        });
        return callback(connection);
      }),
    });
    try {
      const reconstructed = await createPostgresAuthoritativeGraphSnapshotRepository({
        pool: snapshotRolePool,
      }).load(context);
      expect(reconstructed.owner_account_id).toBe(accountId);
      expect(reconstructed.graph_generation).toBe(5);
      expect(reconstructed.claims.map((row) => row.revision_id)).toEqual(expect.arrayContaining([
        graph.transition.revisions.find((row) => row.kind === "claim")?.revision_id,
        identity.transition.revisions.find((row) => row.kind === "claim")?.revision_id,
      ]));
      expect(reconstructed.claims).toHaveLength(4);
      expect(reconstructed.events).toHaveLength(3);
      expect(reconstructed.evidence).toHaveLength(3);
      expect(reconstructed.entities).toHaveLength(1);
      expect(reconstructed.identity_authorizations).toHaveLength(1);
      expect(reconstructed.identity_constraints).toHaveLength(1);
      expect(reconstructed.mentions).toHaveLength(1);
      expect(reconstructed.adjacency).toHaveLength(1);
      expect(reconstructed.source_local_roles).toHaveLength(2);
      expect(reconstructed.placement_artifacts).toHaveLength(3);
      expect(reconstructed.liveness_causes).toEqual({
        purged_claim_revision_ids: [livenessWitness.revision_id],
        forgotten_claim_revision_ids: [],
      });
      const sqliteDatabase = new Database(":memory:");
      try {
        const sqlite = new SqliteLedger(sqliteDatabase);
        for (const sharedTransition of [
          first.transition,
          graph.transition,
          formation.transition,
          identity.transition,
          liveness.transition,
        ]) sqlite.append(sharedTransition);
        expect(sha256CanonicalContent(sqlite.snapshot(accountId)))
          .toBe(sha256CanonicalContent(reconstructed));
      } finally {
        sqliteDatabase.close();
      }
      expect(JSON.stringify(await createPostgresAuthoritativeGraphSnapshotRepository({
        pool: snapshotRolePool,
      }).load(context))).toBe(JSON.stringify(reconstructed));
    } finally {
      await snapshotPhysicalPool.close();
    }

    await pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async (connection) => {
        const cleared = await connection.query<{
          account_id: string | null; principal_id: string | null;
          grant_id: string | null; current_user: string;
        }>({
          name: "qualification.authority_locals_cleared",
          text: `SELECT
              nullif(current_setting('omi.account_id', true), '') AS account_id,
              nullif(current_setting('omi.principal_id', true), '') AS principal_id,
              nullif(current_setting('omi.grant_id', true), '') AS grant_id,
              current_user`,
          values: [],
        });
        expect(cleared).toEqual([{
          account_id: null, principal_id: null, grant_id: null,
          current_user: new URL(explicitTestUrl!).username,
        }]);
      },
    );

    try {
      await ownerSql.unsafe(`
        CREATE OR REPLACE FUNCTION omi_memory.qualification_reject_kernel_commit()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'qualification injected rollback'; END
        $$;
        DROP TRIGGER IF EXISTS reject_kernel_commit ON omi_memory.memory_derivation_commits;
        CREATE TRIGGER reject_kernel_commit
        AFTER INSERT ON omi_memory.memory_derivation_commits
        FOR EACH ROW EXECUTE FUNCTION omi_memory.qualification_reject_kernel_commit()
      `, [], { prepare: false });
      const rollback = append(
        `commit:${suffix}:rollback`,
        `append:${suffix}:rollback`,
        livenessTransition.derivation.commit.commit_id,
      );
      await expect(repository.append(context, rollback)).rejects.toMatchObject({ code: "persistence_failed" });
      const rolledBack = await ownerSql.unsafe<{ attempts: number; commits: number; receipts: number; head_sequence: string }[]>(`
        SELECT
          (SELECT count(*)::int FROM omi_memory.memory_derivation_attempts WHERE account_id = $1) AS attempts,
          (SELECT count(*)::int FROM omi_memory.memory_derivation_commits WHERE account_id = $1) AS commits,
          (SELECT count(*)::int FROM omi_memory.memory_idempotency_receipts WHERE account_id = $1) AS receipts,
          (SELECT sequence::text FROM omi_memory.memory_graph_heads WHERE account_id = $1) AS head_sequence
      `, [accountId]);
      expect([...rolledBack]).toEqual([{ attempts: 5, commits: 5, receipts: 5, head_sequence: "5" }]);
    } finally {
      await ownerSql.unsafe(`
        DROP TRIGGER IF EXISTS reject_kernel_commit ON omi_memory.memory_derivation_commits;
        DROP FUNCTION IF EXISTS omi_memory.qualification_reject_kernel_commit()
      `, [], { prepare: false }).catch(() => undefined);
    }

    const firebaseClaims = {
      aud: firebaseProjectId,
      iss: `https://securetoken.google.com/${firebaseProjectId}`,
      sub: firebaseUid,
      uid: firebaseUid,
      exp: now + 3_600,
      iat: now - 60,
      auth_time: now - 120,
    };
    const firebaseRuntime = createPostgresFirebaseAuthorizedLedgerRuntime({
      pool: appRolePool,
      project_id: firebaseProjectId,
      runtime_mode: "deployed",
      id_token_adapter: {
        verification_source: "firebase_production",
        verifyIdToken: async (_token, checkRevoked) => {
          expect(checkRevoked).toBe(true);
          return firebaseClaims;
        },
      },
      application_id: applicationId,
      context_ttl_seconds: 60,
    });
    const firebaseAppend = append(
      `commit:${suffix}:firebase`,
      `append:${suffix}:firebase`,
      livenessTransition.derivation.commit.commit_id,
    );
    await expect(firebaseRuntime.append("header.payload.signature", now, firebaseAppend))
      .resolves.toEqual({
        kind: "completed",
        outcome: {
          kind: "committed",
          commit_id: firebaseAppend.transition.derivation.commit.commit_id,
          sequence: 6,
        },
      });
    // The preceding canonical claim was intentionally purged by the liveness
    // gate. Add a second, policy-eligible canonical claim so the direct product
    // read proves positive grounded output rather than only a valid empty page.
    const visibleIdentity = identityAppend(
      accountId,
      `${suffix}:visible-product`,
      firebaseAppend.transition.derivation.commit.commit_id,
    );
    await expect(graphRepository.append(context, visibleIdentity)).resolves.toEqual({
      kind: "committed",
      commit_id: visibleIdentity.transition.derivation.commit.commit_id,
      sequence: 7,
    });

    const firebaseReadRuntime = createPostgresFirebaseAuthorizedGraphSnapshotRuntime({
      pool: appRolePool,
      project_id: firebaseProjectId,
      runtime_mode: "deployed",
      id_token_adapter: {
        verification_source: "firebase_production",
        verifyIdToken: async (_token, checkRevoked) => {
          expect(checkRevoked).toBe(true);
          return firebaseClaims;
        },
      },
      application_id: applicationId,
      context_ttl_seconds: 60,
    });
    const authorizedGraph = await firebaseReadRuntime.load(
      "header.payload.signature",
      now,
    );
    expect(authorizedGraph.kind).toBe("loaded");
    if (authorizedGraph.kind !== "loaded") throw new Error("expected authorized graph");
    expect(authorizedGraph.authorization_generation_digest).toMatch(/^[a-f0-9]{64}$/);
    expect(authorizedGraph.db_now_epoch_seconds).toBeGreaterThanOrEqual(now);
    expect(authorizedGraph.snapshot.owner_account_id).toBe(accountId);
    expect(authorizedGraph.snapshot.graph_generation).toBe(7);
    const authorizedProjection = projectFirebaseAuthorizedGraphSnapshotLoad(authorizedGraph, "UTC");
    expect(authorizedProjection.projected.owner_account_id).toBe(accountId);
    expect(authorizedProjection.authorization_generation_digest).toMatch(/^[a-f0-9]{64}$/);
    expect(authorizedProjection.db_now_epoch_seconds).toBe(authorizedGraph.db_now_epoch_seconds);
    let productReadTraces = 0;
    const firebaseProductRead = createPostgresFirebaseAuthorizedMemoryReadRuntime({
      authorization: {
        pool: appRolePool,
        project_id: firebaseProjectId,
        runtime_mode: "deployed",
        id_token_adapter: {
          verification_source: "firebase_production",
          verifyIdToken: async () => firebaseClaims,
        },
        application_id: applicationId,
        context_ttl_seconds: 60,
      },
      product: {
        account_timezone: "UTC",
        codec_root_secret: new Uint8Array(32).fill(0x55),
        produce_renders: produceQaRenders,
        verify_cursor: () => { throw new Error("first page must not verify a cursor"); },
        issue_cursor: () => { throw new Error("bounded qualification page must not issue a cursor"); },
        trace_sink: () => { productReadTraces += 1; },
        accepted_coverage_state: "bypassed",
        stm_coverage_state: "bypassed",
      },
    });
    const productRead = await firebaseProductRead.read(
      "header.payload.signature",
      now,
      { limit: 100, cursor: null },
    );
    expect(productRead.kind).toBe("loaded");
    if (productRead.kind !== "loaded") throw new Error("expected direct product read");
    const productPage = parseSynthesizedPageJson(productRead.canonical_json);
    expect(productPage).not.toBeNull();
    expect(productPage!.items.length).toBeGreaterThan(0);
    expect(productReadTraces).toBe(1);
    await expect(firebaseRuntime.append("header.payload.signature", now, firebaseAppend))
      .resolves.toEqual({
        kind: "completed",
        outcome: {
          kind: "replayed",
          commit_id: firebaseAppend.transition.derivation.commit.commit_id,
          sequence: 6,
        },
      });

    let firebaseTransactions = 0;
    const revokeBeforeAppendPool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(
        options: Parameters<PostgresTransactionPool["withTransaction"]>[0],
        callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
      ) => {
        firebaseTransactions += 1;
        if (firebaseTransactions === 3) {
          await ownerSql.begin(async (transaction) => {
            await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
                (account_id, application_id, credential_id, credential_generation,
                 capability, grant_id, grant_version, lifecycle, enabled, scopes,
                 record_schema_version, record_json, content_hash)
              VALUES ($1, $2, $3, 4, 'memories.write', $4, 10, 'revoked', false,
                      '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
            [accountId, applicationId, credentialId, grantId, "4".repeat(64)]);
            await transaction.unsafe(`UPDATE omi_memory.application_grant_heads
              SET grant_version = 10, updated_at = transaction_timestamp()
              WHERE account_id = $1 AND application_id = $2 AND credential_id = $3
                AND credential_generation = 4 AND capability = 'memories.write'`,
            [accountId, applicationId, credentialId]);
          });
        }
        return appRolePool.withTransaction(options, callback);
      },
    });
    const revocationRaceRuntime = createPostgresFirebaseAuthorizedLedgerRuntime({
      pool: revokeBeforeAppendPool,
      project_id: firebaseProjectId,
      runtime_mode: "deployed",
      id_token_adapter: {
        verification_source: "firebase_production",
        verifyIdToken: async () => firebaseClaims,
      },
      application_id: applicationId,
      context_ttl_seconds: 60,
    });
    const revokedAppend = append(
      `commit:${suffix}:firebase-revoked`,
      `append:${suffix}:firebase-revoked`,
      firebaseAppend.transition.derivation.commit.commit_id,
    );
    await expect(revocationRaceRuntime.append(
      "header.payload.signature", now, revokedAppend,
    )).resolves.toEqual({
      kind: "completed",
      outcome: { kind: "authorization_denied", reason: "grant_inactive" },
    });
    expect(firebaseTransactions).toBe(3);
    const firebaseRows = await ownerSql.unsafe<{
      commits: number; head_sequence: string; revoked_commit: number;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_derivation_commits
          WHERE account_id = $1) AS commits,
        (SELECT sequence::text FROM omi_memory.memory_graph_heads
          WHERE account_id = $1) AS head_sequence,
        (SELECT count(*)::int FROM omi_memory.memory_derivation_commits
          WHERE account_id = $1 AND commit_id = $2) AS revoked_commit
    `, [accountId, revokedAppend.transition.derivation.commit.commit_id]);
    expect([...firebaseRows]).toEqual([{
      commits: 7, head_sequence: "7", revoked_commit: 0,
    }]);

    let readTransactions = 0;
    const revokeBeforeReadPool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(
        options: Parameters<PostgresTransactionPool["withTransaction"]>[0],
        callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
      ) => {
        readTransactions += 1;
        if (readTransactions === 3) {
          await ownerSql.begin(async (transaction) => {
            await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
                (account_id, application_id, credential_id, credential_generation,
                 capability, grant_id, grant_version, lifecycle, enabled, scopes,
                 record_schema_version, record_json, content_hash)
              VALUES ($1, $2, $3, 4, 'memories.read', $4, 2, 'revoked', false,
                      '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
            [accountId, applicationId, credentialId, readGrantId, "6".repeat(64)]);
            await transaction.unsafe(`UPDATE omi_memory.application_grant_heads
              SET grant_version = 2, updated_at = transaction_timestamp()
              WHERE account_id = $1 AND application_id = $2 AND credential_id = $3
                AND credential_generation = 4 AND capability = 'memories.read'`,
            [accountId, applicationId, credentialId]);
          });
        }
        return appRolePool.withTransaction(options, callback);
      },
    });
    const revokedReadRuntime = createPostgresFirebaseAuthorizedGraphSnapshotRuntime({
      pool: revokeBeforeReadPool,
      project_id: firebaseProjectId,
      runtime_mode: "deployed",
      id_token_adapter: {
        verification_source: "firebase_production",
        verifyIdToken: async () => firebaseClaims,
      },
      application_id: applicationId,
      context_ttl_seconds: 60,
    });
    await expect(revokedReadRuntime.load(
      "header.payload.signature",
      now,
    )).resolves.toEqual({ kind: "denied", outcome: "authorization" });
    expect(readTransactions).toBe(3);

    await expect(repository.append(context, first)).resolves.toEqual({
      kind: "authorization_denied", reason: "grant_inactive",
    });
  }, 120_000);

  test("Firebase-authorized reads and writes fail closed across the real lifecycle matrix", async () => {
    const suffix = randomUUID();
    const applicationId = "app:qualification-lifecycle";
    const firebaseProjectId = `firebase-lifecycle-${suffix}`;
    const now = Math.floor(Date.now() / 1_000);
    const deniedCases = [
      { name: "legacy", generation: "legacy", lifecycle: "active", deletion: null, activated: false, conflict: false },
      { name: "migrating", generation: "migrating", lifecycle: "active", deletion: null, activated: false, conflict: false },
      { name: "rolled-back", generation: "rolled_back_stranded", lifecycle: "active", deletion: null, activated: false, conflict: false },
      { name: "unactivated", generation: "new", lifecycle: "active", deletion: null, activated: false, conflict: false },
      { name: "deletion-pending", generation: "new", lifecycle: "deletion_pending", deletion: 12, activated: true, conflict: false },
      { name: "deleted", generation: "new", lifecycle: "deleted", deletion: 12, activated: true, conflict: false },
      { name: "conflicted", generation: "new", lifecycle: "active", deletion: null, activated: true, conflict: true },
    ] as const;
    const allCases = [
      ...deniedCases,
      { name: "race", generation: "new", lifecycle: "active", deletion: null, activated: true, conflict: false },
    ] as const;

    await ownerSql.begin(async (transaction) => {
      for (const selected of allCases) {
        const accountId = `account:lifecycle:${selected.name}:${suffix}`;
        const principalId = `principal:lifecycle:${selected.name}:${suffix}`;
        const credentialId = `credential:lifecycle:${selected.name}:${suffix}`;
        const firebaseUid = `firebase-user-${selected.name}-${suffix}`;
        await transaction.unsafe(
          "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)", [accountId],
        );
        await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
            (account_id, control_revision, account_generation, account_epoch,
             lifecycle_state, deletion_epoch, observed_at, record_schema_version,
             record_json, content_hash)
          VALUES ($1, 1, $2, 11, $3, $4, transaction_timestamp(),
                  'control-v1', '{}'::jsonb, $5)`,
        [accountId, selected.generation, selected.lifecycle, selected.deletion, "1".repeat(64)]);
        await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
            (account_id, control_revision, activated_epoch, activation_control_revision,
             conflict_reason, conflict_at_control_revision)
          VALUES ($1, 1, $2, $3, $4, $5)`, [
          accountId,
          selected.activated ? 11 : null,
          selected.activated ? 1 : null,
          selected.conflict ? "projection_conflicted" : null,
          selected.conflict ? 1 : null,
        ]);
        await transaction.unsafe(`INSERT INTO omi_memory.application_credential_revisions
            (account_id, principal_id, application_id, credential_id,
             credential_generation, credential_kind, lifecycle,
             authentication_strength, expires_at, record_schema_version,
             record_json, content_hash)
          VALUES ($1, $2, $3, $4, 1, 'firebase', 'active', 'firebase-id-token',
                  to_timestamp($5), 'credential-v1', '{}'::jsonb, $6)`,
        [accountId, principalId, applicationId, credentialId, now + 7_200, "2".repeat(64)]);
        await transaction.unsafe(`INSERT INTO omi_memory.application_credential_heads
            (account_id, application_id, credential_id, credential_generation)
          VALUES ($1, $2, $3, 1)`, [accountId, applicationId, credentialId]);
        for (const capability of ["memories.read", "memories.write"] as const) {
          const grantId = `grant:lifecycle:${selected.name}:${capability}:${suffix}`;
          await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
              (account_id, application_id, credential_id, credential_generation,
               capability, grant_id, grant_version, lifecycle, enabled, scopes,
               record_schema_version, record_json, content_hash)
            VALUES ($1, $2, $3, 1, $4, $5, 1, 'active', true,
                    '[]'::jsonb, 'grant-v1', '{}'::jsonb, $6)`,
          [accountId, applicationId, credentialId, capability, grantId, "3".repeat(64)]);
          await transaction.unsafe(`INSERT INTO omi_memory.application_grant_heads
              (account_id, application_id, credential_id, credential_generation,
               capability, grant_id, grant_version)
            VALUES ($1, $2, $3, 1, $4, $5, 1)`,
          [accountId, applicationId, credentialId, capability, grantId]);
        }
        await transaction.unsafe(`INSERT INTO omi_memory.firebase_identity_bindings
            (firebase_project_id, firebase_uid, account_id, principal_id,
             source_control_revision)
          VALUES ($1, $2, $3, $4, 1)`,
        [firebaseProjectId, firebaseUid, accountId, principalId]);
        await transaction.unsafe(`INSERT INTO omi_memory.firebase_application_credential_bindings
            (account_id, firebase_project_id, firebase_uid, principal_id,
             application_id, credential_id)
          VALUES ($1, $2, $3, $4, $5, $6)`,
        [accountId, firebaseProjectId, firebaseUid, principalId, applicationId, credentialId]);
      }
    });

    let transactions = 0;
    const appRolePool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(
        options: Parameters<PostgresTransactionPool["withTransaction"]>[0],
        callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
      ) => {
        transactions += 1;
        return pool.withTransaction(options, async (connection) => {
          await connection.query({
            name: "qualification.lifecycle_set_role",
            text: "SET LOCAL ROLE omi_platform_application", values: [],
          });
          return callback(connection);
        });
      },
    });
    const runtimeOptions = (selected: (typeof allCases)[number]) => ({
      pool: appRolePool,
      project_id: firebaseProjectId,
      runtime_mode: "deployed" as const,
      id_token_adapter: {
        verification_source: "firebase_production" as const,
        verifyIdToken: async () => ({
          aud: firebaseProjectId,
          iss: `https://securetoken.google.com/${firebaseProjectId}`,
          sub: `firebase-user-${selected.name}-${suffix}`,
          uid: `firebase-user-${selected.name}-${suffix}`,
          exp: now + 3_600, iat: now - 60, auth_time: now - 120,
        }),
      },
      application_id: applicationId,
      context_ttl_seconds: 60,
    });

    for (const selected of deniedCases) {
      const readBefore = transactions;
      await expect(createPostgresFirebaseAuthorizedGraphSnapshotRuntime(runtimeOptions(selected))
        .load("header.payload.signature", now))
        .resolves.toEqual({ kind: "denied", outcome: "authorization" });
      expect(transactions - readBefore).toBeLessThanOrEqual(2);

      const writeBefore = transactions;
      const write = nonemptyAppend(
        `account:lifecycle:${selected.name}:${suffix}`,
        `lifecycle:${selected.name}:${suffix}`,
        null,
      );
      await expect(createPostgresFirebaseAuthorizedLedgerRuntime(runtimeOptions(selected))
        .append("header.payload.signature", now, write))
        .resolves.toEqual({ kind: "denied", outcome: "authorization" });
      expect(transactions - writeBefore).toBeLessThanOrEqual(2);
    }

    let raceTransactions = 0;
    const race = allCases[allCases.length - 1]!;
    const raceAccount = `account:lifecycle:${race.name}:${suffix}`;
    const racePool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(
        options: Parameters<PostgresTransactionPool["withTransaction"]>[0],
        callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
      ) => {
        raceTransactions += 1;
        if (raceTransactions === 3) {
          await ownerSql.begin(async (transaction) => {
            await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
                (account_id, control_revision, account_generation, account_epoch,
                 lifecycle_state, deletion_epoch, observed_at, record_schema_version,
                 record_json, content_hash)
              VALUES ($1, 2, 'new', 11, 'deleted', 12, transaction_timestamp(),
                      'control-v1', '{}'::jsonb, $2)`, [raceAccount, "4".repeat(64)]);
            await transaction.unsafe(`UPDATE omi_memory.account_control_heads
              SET control_revision = 2, updated_at = transaction_timestamp()
              WHERE account_id = $1`, [raceAccount]);
          });
        }
        return appRolePool.withTransaction(options, callback);
      },
    });
    await expect(createPostgresFirebaseAuthorizedGraphSnapshotRuntime({
      ...runtimeOptions(race), pool: racePool,
    }).load("header.payload.signature", now))
      .resolves.toEqual({ kind: "denied", outcome: "authorization" });
    expect(raceTransactions).toBe(3);
  }, 120_000);

  test("application-role product projection writer is atomic, replayable, graph-fenced, and authority-fenced", async () => {
    const suffix = randomUUID();
    const accountId = `account:product:${suffix}`;
    const principalId = `principal:product:${suffix}`;
    const applicationId = "app:qualification-product";
    const credentialId = `credential:product:${suffix}`;
    const writeGrantId = `grant:product-write:${suffix}`;
    const projectGrantId = `grant:product-project:${suffix}`;
    const controlHash = "1".repeat(64);
    const credentialHash = "2".repeat(64);
    const writeGrantHash = "3".repeat(64);
    const projectGrantHash = "4".repeat(64);
    const now = Math.floor(Date.now() / 1_000);

    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(
        "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)", [accountId],
      );
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
          (account_id, control_revision, account_generation, account_epoch,
           lifecycle_state, deletion_epoch, observed_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, 17, 'new', 12, 'active', NULL, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountId, controlHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
          (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 17, 12, 17)`, [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_revisions
          (account_id, principal_id, application_id, credential_id,
           credential_generation, credential_kind, lifecycle,
           authentication_strength, expires_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, $2, $3, $4, 4, 'firebase', 'active', 'service-workload',
                to_timestamp($5), 'credential-v1', '{}'::jsonb, $6)`,
      [accountId, principalId, applicationId, credentialId, now + 7_200, credentialHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_heads
          (account_id, application_id, credential_id, credential_generation)
        VALUES ($1, $2, $3, 4)`, [accountId, applicationId, credentialId]);
      for (const [capability, grantId, grantHash] of [
        ["memories.write", writeGrantId, writeGrantHash],
        ["memories.project", projectGrantId, projectGrantHash],
      ] as const) {
        await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
            (account_id, application_id, credential_id, credential_generation,
             capability, grant_id, grant_version, lifecycle, enabled, scopes,
             record_schema_version, record_json, content_hash)
          VALUES ($1, $2, $3, 4, $4, $5, 1, 'active', true,
                  '[]'::jsonb, 'grant-v1', '{}'::jsonb, $6)`,
        [accountId, applicationId, credentialId, capability, grantId, grantHash]);
        await transaction.unsafe(`INSERT INTO omi_memory.application_grant_heads
            (account_id, application_id, credential_id, credential_generation,
             capability, grant_id, grant_version)
          VALUES ($1, $2, $3, 4, $4, $5, 1)`,
        [accountId, applicationId, credentialId, capability, grantId]);
      }
    });

    const authority = (
      capability: "memories.write" | "memories.project",
      grantId: string,
      grantHash: string,
    ): AuthorityStateRow => ({
      account_id: accountId, principal_id: principalId, application_id: applicationId,
      credential_id: credentialId, credential_generation: 4, capability,
      grant_id: grantId, grant_version: 1, account_epoch: 12,
      control_conflict_reason: null, control_conflict_at_revision: null,
      destination_activation_epoch: 12, destination_activation_revision: 17,
      lifecycle_state: "active", deletion_epoch: null, account_generation: "new",
      credential_lifecycle: "active", grant_lifecycle: "active", grant_enabled: true,
      authentication_strength: "service-workload",
      credential_expires_at_epoch_seconds: now + 7_200, control_revision: 17,
      control_content_hash: controlHash, credential_content_hash: credentialHash,
      grant_content_hash: grantHash, db_now_epoch_seconds: now,
    });
    const authorized = (row: AuthorityStateRow) => createAuthorizedLedgerWriteContextIssuer().issue({
      context_version: "authorized-ledger-write-context-v1", principal_id: principalId,
      account_id: accountId, application_id: applicationId, credential_id: credentialId,
      credential_generation: 4, capability: row.capability, grant_id: row.grant_id,
      grant_version: row.grant_version, account_epoch: 12,
      destination_activation_revision: 17, lifecycle_state: "active", deletion_epoch: null,
      authentication_strength: "service-workload", issued_at_epoch_seconds: now - 60,
      expires_at_epoch_seconds: now + 3_600,
      authorization_state_digest: authorizationStateDigest(row),
    }, now);
    const writeContext = authorized(authority("memories.write", writeGrantId, writeGrantHash));
    const projectContext = authorized(authority("memories.project", projectGrantId, projectGrantHash));

    let productBackend: number | undefined;
    let productStatement = "none";
    let productProviderCode = "none";
    let productConstraint = "none";
    const appRolePool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(
        options: Parameters<PostgresTransactionPool["withTransaction"]>[0],
        callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
      ) => pool.withTransaction(options, async (connection) => {
        await connection.query({
          name: "qualification.product_set_role",
          text: "SET LOCAL ROLE omi_platform_application", values: [],
        });
        const role = await connection.query<{ current_user: string; backend_pid: number }>({
          name: "qualification.product_assert_role",
          text: "SELECT current_user, pg_backend_pid() AS backend_pid", values: [],
        });
        expect(role[0]?.current_user).toBe("omi_platform_application");
        if (productBackend === undefined) productBackend = role[0]?.backend_pid;
        expect(role[0]?.backend_pid).toBe(productBackend);
        return callback(Object.freeze({
          connectionIdentity: connection.connectionIdentity,
          query: async <Row extends Record<string, unknown>>(statement: SqlStatement) => {
            productStatement = statement.name;
            try {
              return await connection.query<Row>(statement);
            } catch (error) {
              const code = error && typeof error === "object" ? Reflect.get(error, "code") : null;
              const constraint = error && typeof error === "object"
                ? Reflect.get(error, "constraint_name") : null;
              productProviderCode = typeof code === "string" ? code : "unknown";
              productConstraint = typeof constraint === "string" ? constraint : "unknown";
              throw error;
            }
          },
          execute: async (statement: SqlStatement) => {
            productStatement = statement.name;
            try {
              return await connection.execute(statement);
            } catch (error) {
              const code = error && typeof error === "object" ? Reflect.get(error, "code") : null;
              const constraint = error && typeof error === "object"
                ? Reflect.get(error, "constraint_name") : null;
              productProviderCode = typeof code === "string" ? code : "unknown";
              productConstraint = typeof constraint === "string" ? constraint : "unknown";
              throw error;
            }
          },
        }));
      }),
    });

    const ledger = createPostgresAuthoritativeLedgerRepository({ pool: appRolePool });
    const graph = nonemptyAppend(accountId, `product-${suffix}`, null);
    await expect(ledger.append(writeContext, graph)).resolves.toMatchObject({
      kind: "committed", sequence: 1,
    });
    const claimRevision = graph.transition.revisions.find((revision) => revision.kind === "claim");
    const evidenceRevision = graph.transition.revisions.find((revision) => revision.kind === "evidence");
    if (!claimRevision || claimRevision.kind !== "claim"
      || !evidenceRevision || evidenceRevision.kind !== "evidence") {
      throw new Error("invalid product qualification graph");
    }
    const graphCoordinate = {
      owner_account_id: accountId, graph_frontier: `frontier:product:${suffix}`,
      graph_commit_id: graph.transition.derivation.commit.commit_id,
      graph_commit_sequence: 1,
    };
    const born = birthProductProposition({
      owner_account_id: accountId, proposition_id: `proposition:${suffix}:one`,
      birth_claim_lineage_id: claimRevision.claim.claim_lineage_id, origin: "native",
      graph_frontier: graphCoordinate.graph_frontier, input_digest: "5".repeat(64),
      result_digest: "6".repeat(64), created_at_event_time: 10,
    });
    const projector = createPostgresProductProjectionWriteRepository({ pool: appRolePool });
    const birth = productRequest({
      operation: "birth" as const, graph: graphCoordinate,
      identity: born.identity, membership: born.membership,
    });
    try {
      expect(await projector.append(projectContext, birth)).toEqual({ kind: "appended" });
    } catch (error) {
      throw new Error(
        `product qualification failed at ${productStatement} code ${productProviderCode} constraint ${productConstraint}`,
        { cause: error },
      );
    }
    await expect(projector.append(projectContext, birth)).resolves.toEqual({ kind: "replayed" });

    const changedBirth = birthProductProposition({
      owner_account_id: accountId, proposition_id: born.identity.proposition_id,
      birth_claim_lineage_id: claimRevision.claim.claim_lineage_id, origin: "native",
      graph_frontier: graphCoordinate.graph_frontier, input_digest: "5".repeat(64),
      result_digest: "7".repeat(64), created_at_event_time: 11,
    });
    await expect(projector.append(projectContext, productRequest({
      operation: "birth", graph: graphCoordinate,
      identity: changedBirth.identity, membership: changedBirth.membership,
    }))).resolves.toEqual({ kind: "idempotency_conflict" });

    const renderedContent = Object.freeze({ title: "A cited product memory", language: "en" });
    const renderedContentDigest = sha256CanonicalContent(renderedContent);
    const projection = buildProductProjectionRevision({
      identity: born.identity, membership: born.membership, projection_sequence: 1,
      graph_frontier: graphCoordinate.graph_frontier,
      renderer_contract_digest: "8".repeat(64), rendered_content_digest: renderedContentDigest,
      citations: [{
        claim_lineage_id: claimRevision.claim.claim_lineage_id,
        claim_revision_id: claimRevision.revision_id,
        evidence_refs: [evidenceRevision.evidence.evidence_id],
      }],
      created_at_event_time: 20,
    });
    const payload: ProductProjectionPayload = {
      owner_account_id: accountId, projection_revision_id: projection.projection_revision_id,
      rendered_content_digest: renderedContentDigest,
      payload_contract_version: "product-rendered-content-v1",
      rendered_content: renderedContent,
    };
    const projectionWrite = productRequest({
      operation: "projection" as const, graph: graphCoordinate,
      identity: born.identity, membership: born.membership, projection, payload,
    });
    try {
      expect(await projector.append(projectContext, projectionWrite)).toEqual({ kind: "appended" });
    } catch (error) {
      throw new Error(
        `product qualification failed at ${productStatement} code ${productProviderCode} constraint ${productConstraint}`,
        { cause: error },
      );
    }

    const persisted = await ownerSql.unsafe<{
      propositions: number; memberships: number; projections: number; payloads: number;
      citations: number; evidence_refs: number; receipts: number;
    }[]>(`SELECT
      (SELECT count(*)::int FROM omi_memory.memory_product_propositions WHERE account_id = $1) AS propositions,
      (SELECT count(*)::int FROM omi_memory.memory_product_membership_revisions WHERE account_id = $1) AS memberships,
      (SELECT count(*)::int FROM omi_memory.memory_product_projection_revisions WHERE account_id = $1) AS projections,
      (SELECT count(*)::int FROM omi_memory.memory_product_projection_payloads WHERE account_id = $1) AS payloads,
      (SELECT count(*)::int FROM omi_memory.memory_product_projection_citations WHERE account_id = $1) AS citations,
      (SELECT count(*)::int FROM omi_memory.memory_product_projection_citation_evidence_refs WHERE account_id = $1) AS evidence_refs,
      (SELECT count(*)::int FROM omi_memory.memory_product_operation_receipts WHERE account_id = $1) AS receipts`,
    [accountId]);
    expect([...persisted]).toEqual([{
      propositions: 1, memberships: 1, projections: 1, payloads: 1,
      citations: 1, evidence_refs: 1, receipts: 2,
    }]);

    const rollbackBorn = birthProductProposition({
      owner_account_id: accountId, proposition_id: `proposition:${suffix}:rollback`,
      birth_claim_lineage_id: claimRevision.claim.claim_lineage_id, origin: "native",
      graph_frontier: graphCoordinate.graph_frontier, input_digest: "9".repeat(64),
      result_digest: "a".repeat(64), created_at_event_time: 30,
    });
    try {
      await ownerSql.unsafe(`
        CREATE OR REPLACE FUNCTION omi_memory.qualification_reject_product_receipt()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'qualification injected product rollback'; END
        $$;
        DROP TRIGGER IF EXISTS reject_product_receipt ON omi_memory.memory_product_operation_receipts;
        CREATE TRIGGER reject_product_receipt
        AFTER INSERT ON omi_memory.memory_product_operation_receipts
        FOR EACH ROW EXECUTE FUNCTION omi_memory.qualification_reject_product_receipt()
      `, [], { prepare: false });
      await expect(projector.append(projectContext, productRequest({
        operation: "birth", graph: graphCoordinate,
        identity: rollbackBorn.identity, membership: rollbackBorn.membership,
      }))).rejects.toMatchObject({ code: "persistence_failed", message: "persistence_failed" });
      const rolledBack = await ownerSql.unsafe<{ propositions: number; receipts: number }[]>(`
        SELECT
          (SELECT count(*)::int FROM omi_memory.memory_product_propositions
            WHERE account_id = $1 AND proposition_id = $2) AS propositions,
          (SELECT count(*)::int FROM omi_memory.memory_product_operation_receipts
            WHERE account_id = $1 AND operation_identity = $2) AS receipts
      `, [accountId, rollbackBorn.identity.proposition_id]);
      expect([...rolledBack]).toEqual([{ propositions: 0, receipts: 0 }]);
    } finally {
      await ownerSql.unsafe(`
        DROP TRIGGER IF EXISTS reject_product_receipt ON omi_memory.memory_product_operation_receipts;
        DROP FUNCTION IF EXISTS omi_memory.qualification_reject_product_receipt()
      `, [], { prepare: false }).catch(() => undefined);
    }

    const laterGraph = nonemptyAppend(
      accountId, `product-later-${suffix}`, graph.transition.derivation.commit.commit_id,
    );
    await expect(ledger.append(writeContext, laterGraph)).resolves.toMatchObject({
      kind: "committed", sequence: 2,
    });
    const staleBorn = birthProductProposition({
      owner_account_id: accountId, proposition_id: `proposition:${suffix}:stale`,
      birth_claim_lineage_id: claimRevision.claim.claim_lineage_id, origin: "native",
      graph_frontier: graphCoordinate.graph_frontier, input_digest: "b".repeat(64),
      result_digest: "c".repeat(64), created_at_event_time: 40,
    });
    await expect(projector.append(projectContext, productRequest({
      operation: "birth", graph: graphCoordinate,
      identity: staleBorn.identity, membership: staleBorn.membership,
    }))).resolves.toEqual({ kind: "stale_graph" });

    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 4, 'memories.project', $4, 2, 'revoked', false,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
      [accountId, applicationId, credentialId, projectGrantId, "d".repeat(64)]);
      await transaction.unsafe(`UPDATE omi_memory.application_grant_heads
        SET grant_version = 2, updated_at = transaction_timestamp()
        WHERE account_id = $1 AND application_id = $2 AND credential_id = $3
          AND credential_generation = 4 AND capability = 'memories.project'`,
      [accountId, applicationId, credentialId]);
    });
    await expect(projector.append(projectContext, birth)).resolves.toEqual({
      kind: "authorization_denied", reason: "grant_inactive",
    });

    for (const forbiddenSql of [
      "UPDATE omi_memory.memory_product_propositions SET origin = 'native' WHERE account_id = $1",
      "DELETE FROM omi_memory.memory_product_projection_payloads WHERE account_id = $1",
    ]) {
      await expect(ownerSql.begin(async (transaction) => {
        await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
        await transaction.unsafe(forbiddenSql, [accountId]);
      })).rejects.toMatchObject({ code: "42501" });
    }
  }, 120_000);

  test("application-role experiment results, pairs, and grounding are isolated, replayable, and authority-fenced", async () => {
    const suffix = randomUUID();
    const accountId = `account:experiment:${suffix}`;
    const principalId = `principal:experiment:${suffix}`;
    const applicationId = "app:qualification-experiment";
    const credentialId = `credential:experiment:${suffix}`;
    const grantId = `grant:experiment:${suffix}`;
    const writeGrantId = `grant:experiment-write:${suffix}`;
    const controlHash = "1".repeat(64);
    const credentialHash = "2".repeat(64);
    const grantHash = "3".repeat(64);
    const writeGrantHash = "4".repeat(64);
    const now = Math.floor(Date.now() / 1_000);

    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe("INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)", [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
          (account_id, control_revision, account_generation, account_epoch,
           lifecycle_state, deletion_epoch, observed_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, 17, 'new', 12, 'active', NULL, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountId, controlHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
          (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 17, 12, 17)`, [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_revisions
          (account_id, principal_id, application_id, credential_id,
           credential_generation, credential_kind, lifecycle,
           authentication_strength, expires_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, $2, $3, $4, 4, 'firebase', 'active', 'service-workload',
                to_timestamp($5), 'credential-v1', '{}'::jsonb, $6)`,
      [accountId, principalId, applicationId, credentialId, now + 7_200, credentialHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_heads
          (account_id, application_id, credential_id, credential_generation)
        VALUES ($1, $2, $3, 4)`, [accountId, applicationId, credentialId]);
      for (const [capability, selectedGrantId, selectedGrantHash] of [
        ["memories.experiments.shadow", grantId, grantHash],
        ["memories.write", writeGrantId, writeGrantHash],
      ] as const) {
        await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
            (account_id, application_id, credential_id, credential_generation,
             capability, grant_id, grant_version, lifecycle, enabled, scopes,
             record_schema_version, record_json, content_hash)
          VALUES ($1, $2, $3, 4, $4, $5, 1, 'active', true,
                  '[]'::jsonb, 'grant-v1', '{}'::jsonb, $6)`,
        [accountId, applicationId, credentialId, capability, selectedGrantId, selectedGrantHash]);
        await transaction.unsafe(`INSERT INTO omi_memory.application_grant_heads
            (account_id, application_id, credential_id, credential_generation,
             capability, grant_id, grant_version)
          VALUES ($1, $2, $3, 4, $4, $5, 1)`,
        [accountId, applicationId, credentialId, capability, selectedGrantId]);
      }
    });

    const authority = (
      capability: "memories.experiments.shadow" | "memories.write",
      selectedGrantId: string,
      selectedGrantHash: string,
    ): AuthorityStateRow => ({
      account_id: accountId, principal_id: principalId, application_id: applicationId,
      credential_id: credentialId, credential_generation: 4,
      capability, grant_id: selectedGrantId, grant_version: 1,
      account_epoch: 12, control_conflict_reason: null, control_conflict_at_revision: null,
      destination_activation_epoch: 12, destination_activation_revision: 17,
      lifecycle_state: "active", deletion_epoch: null, account_generation: "new",
      credential_lifecycle: "active", grant_lifecycle: "active", grant_enabled: true,
      authentication_strength: "service-workload", credential_expires_at_epoch_seconds: now + 7_200,
      control_revision: 17, control_content_hash: controlHash,
      credential_content_hash: credentialHash, grant_content_hash: selectedGrantHash,
      db_now_epoch_seconds: now,
    });
    const shadowAuthority = authority("memories.experiments.shadow", grantId, grantHash);
    const writeAuthority = authority("memories.write", writeGrantId, writeGrantHash);
    const context = createAuthorizedLedgerWriteContextIssuer().issue({
      context_version: "authorized-ledger-write-context-v1", principal_id: principalId,
      account_id: accountId, application_id: applicationId, credential_id: credentialId,
      credential_generation: 4, capability: "memories.experiments.shadow",
      grant_id: grantId, grant_version: 1, account_epoch: 12,
      destination_activation_revision: 17, lifecycle_state: "active", deletion_epoch: null,
      authentication_strength: "service-workload", issued_at_epoch_seconds: now - 60,
      expires_at_epoch_seconds: now + 3_600,
      authorization_state_digest: authorizationStateDigest(shadowAuthority),
    }, now);
    const writeContext = createAuthorizedLedgerWriteContextIssuer().issue({
      context_version: "authorized-ledger-write-context-v1", principal_id: principalId,
      account_id: accountId, application_id: applicationId, credential_id: credentialId,
      credential_generation: 4, capability: "memories.write",
      grant_id: writeGrantId, grant_version: 1, account_epoch: 12,
      destination_activation_revision: 17, lifecycle_state: "active", deletion_epoch: null,
      authentication_strength: "service-workload", issued_at_epoch_seconds: now - 60,
      expires_at_epoch_seconds: now + 3_600,
      authorization_state_digest: authorizationStateDigest(writeAuthority),
    }, now);

    let backendPid: number | undefined;
    const appRolePool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(
        options: Parameters<PostgresTransactionPool["withTransaction"]>[0],
        callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
      ) => pool.withTransaction(options, async (connection) => {
        await connection.query({
          name: "qualification.experiment_set_role",
          text: "SET LOCAL ROLE omi_platform_application", values: [],
        });
        const role = await connection.query<{ current_user: string; backend_pid: number }>({
          name: "qualification.experiment_assert_role",
          text: "SELECT current_user, pg_backend_pid() AS backend_pid", values: [],
        });
        expect(role[0]?.current_user).toBe("omi_platform_application");
        if (backendPid === undefined) backendPid = role[0]?.backend_pid;
        expect(role[0]?.backend_pid).toBe(backendPid);
        return callback(connection);
      }),
    });

    const strategy = (id: string, version: string) => registerMemoryStrategy({
      version: MEMORY_STRATEGY_VERSION, strategy_id: id, work_kind: "retrieval",
      coordinates: {
        strategy_version: version, model_version: "deepseek:v4-flash",
        prompt_version: "prompt:qualification:v1", policy_version: "policy:v1",
        code_version: "code:v1", schema_version: "schema:v1", tokenizer_version: "tokenizer:v1",
        tool_version: "none", result_contract_version: "memory-read-evaluation-result-v1",
        speaker_strategy_version: "none", boundary_strategy_version: "none",
      },
    });
    const baselineStrategy = strategy(`strategy:baseline:${suffix}`, "retrieval:baseline:v1");
    const candidateStrategy = strategy(`strategy:candidate:${suffix}`, "retrieval:candidate:v1");
    const policy = defineMemoryStrategyAssignmentPolicy({
      policy_id: `policy:retrieval:${suffix}`, work_kind: "retrieval", unit_kind: "session",
      key_version: "assignment-key:v1", authority_strategy_id: baselineStrategy.strategy_id,
      shadow_candidates: [{ strategy_id: candidateStrategy.strategy_id, basis_points: 10_000 }],
    }, [baselineStrategy, candidateStrategy]);
    const assignment = createMemoryStrategyAssigner(new Uint8Array(32).fill(5)).assign({
      owner_account_id: accountId, unit_ref: `session:${suffix}`,
      policy, strategies: [baselineStrategy, candidateStrategy],
    });
    const source = defineMemoryEvaluationEvidenceSource(async (authorized, request) => ({
      kind: "found", owner_account_id: authorized.account_id, account_epoch: authorized.account_epoch,
      source_kind: request.source_kind, source_ref: request.source_ref,
      input_frontier: request.input_frontier, payload: { query: "Where do I work?" },
    }));
    const copied = await source.load(context, {
      source_kind: "authorized_graph_snapshot", source_ref: `source:${suffix}`,
      input_frontier: `frontier:${suffix}`,
    });
    if (copied.kind !== "found") throw new Error("qualification copied input unavailable");
    const evidenceRef = `tr1_${sha256CanonicalContent({ suffix, evidence: 1 })}` as const;

    const stageRequest = (role: MemoryEvaluationRole): MemoryEvaluationStageRequest => {
      const selected = role === "baseline" ? assignment.authority : assignment.shadows[0]!;
      const selectedStrategy = role === "baseline" ? baselineStrategy : candidateStrategy;
      const trace = buildContentSafeRecallTrace({
        version: "recall-trace-v1", traceRef: `tr1_${sha256CanonicalContent({ suffix, role })}`,
        strategyVersion: selectedStrategy.coordinates.strategy_version,
        projectionFreshness: "fresh", outcome: "grounded", latencyMs: 1,
        tokenCounts: { input: 1, output: 1 },
        stages: {
          eligible: [evidenceRef], selected: [evidenceRef], hydrated: [evidenceRef],
          policyEligible: [evidenceRef], cited: [evidenceRef], grounded: [evidenceRef],
        },
      });
      const normalized = buildMemoryReadEvaluationResult(context, {
        assignment_bundle: assignment, assignment_id: selected.assignment_id,
        copied_input: copied.copied_input, evaluation_role: role, repeat_ordinal: 0,
        query_text: "Where do I work?", answer_text: "You work at Omi.", absence: null,
        assertions: [{ ordinal: 0, text: "You work at Omi.", citations: [evidenceRef] }],
        recall_trace: trace,
      });
      const body = {
        assignment_bundle: assignment, assignment_id: selected.assignment_id,
        account_epoch: 12, evaluation_role: role, evaluation_mode: "offline_replay" as const,
        evaluation_run_id: `mer1_${sha256CanonicalContent({ suffix, run: 1 })}`,
        input_frontier: `frontier:${suffix}`, input_digest: copied.copied_input.input_digest,
        repeat_ordinal: 0, result_contract_version: normalized.version,
        response_digest: sha256CanonicalContent({ role, normalized }),
        normalized_result_digest: durableMemoryWorkNormalizedResultDigest(normalized.version, normalized),
        normalized_result: normalized,
      };
      return { ...body, request_digest: memoryEvaluationStageRequestDigest(context, body) };
    };

    const results = createPostgresMemoryShadowResultRepository({ pool: appRolePool });
    const groundings = createPostgresMemoryReadGroundingRepository({ pool: appRolePool });
    const ledger = createPostgresAuthoritativeLedgerRepository({ pool: appRolePool });
    const sourceGraph = nonemptyAppend(accountId, `${suffix}:query-source`, null);
    await expect(ledger.append(writeContext, sourceGraph)).resolves.toEqual({
      kind: "committed", commit_id: sourceGraph.transition.derivation.commit.commit_id, sequence: 1,
    });
    const canonicalGraph = identityAppend(
      accountId, `${suffix}:query-canonical`, sourceGraph.transition.derivation.commit.commit_id,
    );
    await expect(ledger.append(writeContext, canonicalGraph)).resolves.toEqual({
      kind: "committed", commit_id: canonicalGraph.transition.derivation.commit.commit_id, sequence: 2,
    });
    const graphRepository = createPostgresAuthoritativeGraphSnapshotRepository({ pool: appRolePool });
    const graphSnapshot = await graphRepository.load(context);
    let queryModelCalls = 0;
    const queryCandidateRefs: string[] = [];
    const queryRuntime = createPostgresMemoryQueryEvaluationOneShotRuntime({
      pool: appRolePool, codec_root_secret: new Uint8Array(32).fill(8),
      produce: async (request) => {
        queryModelCalls += 1;
        expect(request.candidates).toHaveLength(1);
        expect(request.candidates[0]?.text).toBe("Alice");
        const cited = request.candidates[0]!.trace_ref;
        queryCandidateRefs.push(cited);
        return {
          kind: "produced" as const,
          response_digest: sha256CanonicalContent({
            qualification: "postgres-nonempty-query-v1",
            strategy_id: request.strategy.strategy_id,
            repeat_ordinal: request.repeat_ordinal,
          }),
          answer_text: "Alice is remembered.", absence: null,
          assertions: [{ ordinal: 0, text: "Alice is remembered.", citations: [cited] }],
          recall_trace: buildContentSafeRecallTrace({
            version: "recall-trace-v1",
            traceRef: `tr1_${sha256CanonicalContent({
              qualification: "postgres-nonempty-query-trace-v1",
              strategy_id: request.strategy.strategy_id,
            })}`,
            strategyVersion: request.strategy.coordinates.strategy_version,
            projectionFreshness: "fresh", outcome: "grounded", latencyMs: 1,
            tokenCounts: { input: 1, output: 1 },
            stages: {
              eligible: [cited], selected: [cited], hydrated: [cited],
              policyEligible: [cited], cited: [cited], grounded: [cited],
            },
          }),
        };
      },
    });
    const stagedQueryInput = await queryRuntime.stageInput(context, {
      input_ref: `mqir1_${sha256CanonicalContent({ suffix, query: 1 })}`,
      query_text: "Where do I work?", account_timezone: "UTC",
    });
    if (stagedQueryInput.kind !== "staged") throw new Error("qualification query input not staged");
    const queryInput = stagedQueryInput.input;
    const queryInputs = createPostgresMemoryQueryEvaluationInputRepository({ pool: appRolePool });
    const queryGraphSource = createPostgresMemoryQueryEvaluationGraphSource({ pool: appRolePool });
    await expect(queryInputs.stage(context, queryInput)).resolves.toEqual({ kind: "replayed", input: queryInput });
    const restartedQueryInputs = createPostgresMemoryQueryEvaluationInputRepository({ pool: appRolePool });
    await expect(restartedQueryInputs.load(context, queryInput.source_ref)).resolves.toEqual({
      kind: "found", input: queryInput,
    });
    await expect(queryGraphSource.load(context, {
      source_kind: "authorized_graph_snapshot", source_ref: queryInput.source_ref,
      input_frontier: queryInput.input_frontier,
    })).resolves.toEqual({
      kind: "found", owner_account_id: accountId, account_epoch: 12,
      source_ref: queryInput.source_ref, input_frontier: queryInput.input_frontier,
      query_text: queryInput.query_text, account_timezone: queryInput.account_timezone,
      graph_snapshot: graphSnapshot,
    });
    const queryRunRequest = Object.freeze({
      assignment_bundle: assignment,
      evaluation_run_id: `mer1_${sha256CanonicalContent({ suffix, run: "postgres-query" })}`,
      source_request: Object.freeze({
        source_kind: "authorized_graph_snapshot" as const,
        source_ref: queryInput.source_ref,
        input_frontier: queryInput.input_frontier,
      }),
      repeats: 1,
    });
    const firstQueryRun = await queryRuntime.run(context, queryRunRequest);
    expect(firstQueryRun).toMatchObject({
      kind: "completed", observed_model_calls: 2, staged_results: 2,
      replayed_results: 0, recorded_pairs: 1, replayed_pairs: 0,
    });
    expect(firstQueryRun.pair_receipts).toHaveLength(1);
    expect(queryModelCalls).toBe(2);
    expect(new Set(queryCandidateRefs).size).toBe(1);
    const [queryCandidateRef] = queryCandidateRefs;
    const persistedGroundings = await ownerSql.unsafe<{
      grounded_reference_count: number; rows_json: unknown;
    }[]>(`SELECT grounded_reference_count, rows_json
      FROM omi_memory.memory_strategy_baseline_read_groundings WHERE account_id = $1
      UNION ALL
      SELECT grounded_reference_count, rows_json
      FROM omi_memory.memory_strategy_candidate_read_groundings WHERE account_id = $1`, [accountId]);
    expect([...persistedGroundings]).toHaveLength(2);
    for (const persisted of persistedGroundings) {
      expect(persisted.grounded_reference_count).toBe(1);
      expect(persisted.rows_json).toEqual([{
        trace_ref: queryCandidateRef,
        contributing_subject_classes: ["generic"],
      }]);
    }
    const restartedQueryRuntime = createPostgresMemoryQueryEvaluationOneShotRuntime({
      pool: appRolePool, codec_root_secret: new Uint8Array(32).fill(8),
      produce: async () => { throw new Error("replay_must_not_call_model"); },
    });
    const replayedQueryRun = await restartedQueryRuntime.run(context, queryRunRequest);
    expect(replayedQueryRun).toMatchObject({
      kind: "completed", observed_model_calls: 0, staged_results: 0,
      replayed_results: 2, recorded_pairs: 0, replayed_pairs: 1,
    });
    expect(queryModelCalls).toBe(2);
    expect(replayedQueryRun.pair_receipts).toEqual(firstQueryRun.pair_receipts);
    const baselineRequest = stageRequest("baseline");
    const candidateRequest = stageRequest("candidate");
    const baselineResult = materializeMemoryEvaluationResult(context, baselineRequest);
    const candidateResult = materializeMemoryEvaluationResult(context, candidateRequest);
    for (const [selected, selectedRequest] of [
      [baselineResult, baselineRequest],
      [candidateResult, candidateRequest],
    ] as const) {
      const artifact = materializeFinalizedMemoryReadGrounding({
        evaluation_result: selected, projection_authorization_digest: "4".repeat(64),
        reader_projection_digest: "5".repeat(64), projected_content_digest: "6".repeat(64),
        rows: [{ trace_ref: evidenceRef, contributing_subject_classes: ["owner"] }],
      });
      await expect(groundings.stage(context, selected, artifact, selectedRequest)).resolves.toEqual({ kind: "staged", artifact });
      await expect(groundings.load(context, selected)).resolves.toEqual({ kind: "found", artifact });
    }
    await expect(results.stage(context, baselineRequest)).resolves.toEqual({
      kind: "replayed", result: baselineResult,
    });
    await expect(results.load(context, {
      assignment_bundle: assignment, assignment_id: assignment.authority.assignment_id,
      account_epoch: 12, evaluation_role: "baseline", evaluation_mode: "offline_replay",
      evaluation_run_id: baselineRequest.evaluation_run_id,
      input_frontier: baselineRequest.input_frontier, input_digest: baselineRequest.input_digest,
      repeat_ordinal: 0,
    })).resolves.toEqual({ kind: "found", result: baselineResult });
    const pair = pairMemoryEvaluationResults(baselineResult, candidateResult);
    await expect(results.recordPair(context, pair)).resolves.toEqual({ kind: "recorded", pair });
    await expect(results.recordPair(context, pair)).resolves.toEqual({ kind: "replayed", pair });

    const persisted = await ownerSql.unsafe<{
      baselines: number; candidates: number; pairs: number; baseline_groundings: number;
      candidate_groundings: number; query_inputs: number; pair_json_columns: number;
    }[]>(`SELECT
      (SELECT count(*)::int FROM omi_memory.memory_strategy_evaluation_baselines WHERE account_id = $1) AS baselines,
      (SELECT count(*)::int FROM omi_memory.memory_strategy_shadow_results WHERE account_id = $1) AS candidates,
      (SELECT count(*)::int FROM omi_memory.memory_strategy_evaluation_pairs WHERE account_id = $1) AS pairs,
      (SELECT count(*)::int FROM omi_memory.memory_strategy_baseline_read_groundings WHERE account_id = $1) AS baseline_groundings,
      (SELECT count(*)::int FROM omi_memory.memory_strategy_candidate_read_groundings WHERE account_id = $1) AS candidate_groundings,
      (SELECT count(*)::int FROM omi_memory.memory_query_evaluation_inputs WHERE account_id = $1) AS query_inputs,
      (SELECT count(*)::int FROM information_schema.columns
       WHERE table_schema = 'omi_memory' AND table_name = 'memory_strategy_evaluation_pairs'
         AND data_type IN ('json', 'jsonb')) AS pair_json_columns`, [accountId]);
    expect([...persisted]).toEqual([{
      baselines: 2, candidates: 2, pairs: 2,
      baseline_groundings: 2, candidate_groundings: 2, query_inputs: 1, pair_json_columns: 0,
    }]);

    const rollbackPolicy = defineMemoryStrategyAssignmentPolicy({
      policy_id: `policy:rollback:${suffix}`, work_kind: "retrieval", unit_kind: "session",
      key_version: "assignment-key:v1", authority_strategy_id: baselineStrategy.strategy_id,
      shadow_candidates: [{ strategy_id: candidateStrategy.strategy_id, basis_points: 10_000 }],
    }, [baselineStrategy, candidateStrategy]);
    const rollbackAssignment = createMemoryStrategyAssigner(new Uint8Array(32).fill(7)).assign({
      owner_account_id: accountId, unit_ref: `session:rollback:${suffix}`,
      policy: rollbackPolicy, strategies: [baselineStrategy, candidateStrategy],
    });
    const rollbackBody = {
      ...baselineRequest, assignment_bundle: rollbackAssignment,
      assignment_id: rollbackAssignment.authority.assignment_id,
      evaluation_run_id: `mer1_${sha256CanonicalContent({ suffix, run: "rollback" })}`,
    };
    const { request_digest: _oldRollbackDigest, ...rollbackRequestBody } = rollbackBody;
    const rollbackRequest: MemoryEvaluationStageRequest = {
      ...rollbackRequestBody,
      request_digest: memoryEvaluationStageRequestDigest(context, rollbackRequestBody),
    };
    const rollbackResult = materializeMemoryEvaluationResult(context, rollbackRequest);
    const rollbackArtifact = materializeFinalizedMemoryReadGrounding({
      evaluation_result: rollbackResult, projection_authorization_digest: "4".repeat(64),
      reader_projection_digest: "5".repeat(64), projected_content_digest: "6".repeat(64),
      rows: [{ trace_ref: evidenceRef, contributing_subject_classes: ["owner"] }],
    });
    try {
      await ownerSql.unsafe(`
        CREATE OR REPLACE FUNCTION omi_memory.qualification_reject_experiment_grounding()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'qualification injected experiment rollback'; END
        $$;
        DROP TRIGGER IF EXISTS reject_experiment_grounding ON omi_memory.memory_strategy_baseline_read_groundings;
        CREATE TRIGGER reject_experiment_grounding
        AFTER INSERT ON omi_memory.memory_strategy_baseline_read_groundings
        FOR EACH ROW EXECUTE FUNCTION omi_memory.qualification_reject_experiment_grounding()
      `, [], { prepare: false });
      await expect(groundings.stage(
        context, rollbackResult, rollbackArtifact, rollbackRequest,
      )).resolves.toEqual({ kind: "source_unavailable" });
      const rolledBack = await ownerSql.unsafe<{ bundles: number; results: number; groundings: number }[]>(`SELECT
        (SELECT count(*)::int FROM omi_memory.memory_strategy_assignment_bundles
          WHERE account_id = $1 AND assignment_bundle_id = $2) AS bundles,
        (SELECT count(*)::int FROM omi_memory.memory_strategy_evaluation_baselines
          WHERE account_id = $1 AND evaluation_run_id = $3) AS results,
        (SELECT count(*)::int FROM omi_memory.memory_strategy_baseline_read_groundings
          WHERE account_id = $1 AND evaluation_result_id = $4) AS groundings`,
      [accountId, rollbackAssignment.assignment_bundle_id, rollbackRequest.evaluation_run_id,
        rollbackResult.evaluation_result_id]);
      expect([...rolledBack]).toEqual([{ bundles: 0, results: 0, groundings: 0 }]);
    } finally {
      await ownerSql.unsafe(`
        DROP TRIGGER IF EXISTS reject_experiment_grounding ON omi_memory.memory_strategy_baseline_read_groundings;
        DROP FUNCTION IF EXISTS omi_memory.qualification_reject_experiment_grounding()
      `, [], { prepare: false }).catch(() => undefined);
    }

    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 4, 'memories.experiments.shadow', $4, 2, 'revoked', false,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
      [accountId, applicationId, credentialId, grantId, "7".repeat(64)]);
      await transaction.unsafe(`UPDATE omi_memory.application_grant_heads
        SET grant_version = 2, updated_at = transaction_timestamp()
        WHERE account_id = $1 AND application_id = $2 AND credential_id = $3
          AND credential_generation = 4 AND capability = 'memories.experiments.shadow'`,
      [accountId, applicationId, credentialId]);
    });
    await expect(results.stage(context, baselineRequest)).resolves.toEqual({
      kind: "authorization_denied", reason: "grant_inactive",
    });
    await expect(restartedQueryInputs.load(context, queryInput.source_ref)).resolves.toEqual({
      kind: "authorization_denied", reason: "grant_inactive",
    });

    for (const forbiddenSql of [
      "UPDATE omi_memory.memory_strategy_evaluation_baselines SET result_version = result_version WHERE account_id = $1",
      "DELETE FROM omi_memory.memory_strategy_evaluation_pairs WHERE account_id = $1",
      "UPDATE omi_memory.memory_query_evaluation_inputs SET query_text = query_text WHERE account_id = $1",
      "DELETE FROM omi_memory.memory_query_evaluation_inputs WHERE account_id = $1",
    ]) {
      await expect(ownerSql.begin(async (transaction) => {
        await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
        await transaction.unsafe(forbiddenSql, [accountId]);
      })).rejects.toMatchObject({ code: "42501" });
    }
  }, 120_000);
});
