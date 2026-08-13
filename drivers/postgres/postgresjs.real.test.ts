import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { createHash, randomUUID } from "node:crypto";
import postgres, { type Sql } from "postgres";

import {
  createAuthorizedLedgerWriteContextIssuer,
  type AuthorizedLedgerWriteContextInput,
} from "../../apps/service/auth/authorized-context-internal";
import { createServedCounter } from "../../apps/service/observability/served-count";
import {
  InvalidMcpCursorError,
  asOpaqueVisibleKeyset,
  issueMcpCursor,
} from "../../apps/mcp/cursor";
import {
  emitDurableMemoryWorkBacklogTelemetry,
} from "../../apps/service/observability/durable-memory-work-backlog";
import { authoritativeAppendRequestDigest, type AuthoritativeLedgerAppend } from "../../apps/service/stores/authoritative-ledger-repository";
import {
  productProjectionWriteRequestDigest,
  type ProductProjectionPayload,
  type ProductProjectionWriteBody,
} from "../../apps/service/stores/product-projection-repository";
import {
  legacyMigrationTombstoneRequestDigest,
  legacyPropositionMappingResumeRequestDigest,
} from "../../apps/service/stores/legacy-proposition-migration-repository";
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
import type { AttributionCalibrationRequest } from
  "../../core/consolidate/attribution-calibration";
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
import {
  isTrustedRecallCompletenessHonest,
  parseSynthesizedPageJson,
} from "@omi-core/ratified-contracts/projections/synthesized";
import { produceQaRenders } from "../../apps/qa/renders";
import type { IdentityAuthorization, IdentityConstraint, Predicate, ProvisionalClaim } from "../../core/schema";
import {
  createPostgresAuthoritativeLedgerRepository,
  createPostgresSuccessfulEmptyLedgerRepository,
} from "./authoritative-ledger-repository";
import { createPostgresAuthoritativeGraphSnapshotRepository } from "./authoritative-graph-snapshot";
import { createPostgresDeletionCleanupParticipant } from
  "./account-deletion-cleanup-participant";
import { createPostgresTypesenseDeletionReceiptRepository } from
  "./typesense-deletion-receipt-repository";
import { createPostgresPineconeDeletionReceiptRepository } from
  "./pinecone-deletion-receipt-repository";
import { createPostgresGcsDeletionReceiptRepository } from
  "./gcs-deletion-receipt-repository";
import { createPostgresFirestoreLegacyGenerationReceiptRepository } from
  "./firestore-legacy-generation-receipt-repository";
import { createPostgresStrandedRollbackRecoveryManifestRepository } from
  "./stranded-rollback-recovery-manifest-repository";
import {
  STRANDED_ROLLBACK_RECOVERY_CONTRACT_VERSION,
  STRANDED_ROLLBACK_RECOVERY_SURFACES,
  STRANDED_ROLLBACK_RECOVERY_WINDOW_SECONDS,
  STRANDED_ROLLBACK_SOURCE_RECEIPT_VERSION,
  verifyStrandedRollbackRecovery,
} from "../../core/control/stranded-rollback-recovery";
import type { CheckedOutPostgresConnection, PostgresTransactionPool, SqlStatement } from "./connection";
import { createPostgresDurableMemoryWorkAcceptanceRepository } from "./durable-memory-work-acceptance";
import { createPostgresDurableMemoryWorkBacklogSource } from "./durable-memory-work-backlog";
import { createPostgresDurableMemoryWorkExecutionRepository } from "./durable-memory-work-execution";
import { createPostgresDurableMemoryWorkResultRepository } from "./durable-memory-work-result";
import { createPostgresDurableMemoryWorkSuccessRepository } from "./durable-memory-work-success";
import { createPostgresFormationWorkInputRepository } from "./formation-work-input";
import { createPostgresFormationOneShotRuntime } from "./formation-one-shot-runtime";
import { createPostgresProductionModelPipelineExclusivity } from "./model-pipeline-exclusivity";
import { MODEL_PIPELINE_RESOURCE_VERSION } from "../../apps/service/workers/model-pipeline-exclusivity";
import {
  currentProductionMigrationManifestDigest,
  parseProductionQualificationManifest,
  PRODUCTION_QUALIFICATION_BUN_IMAGE,
  PRODUCTION_QUALIFICATION_DEPENDENCY_ARTIFACT_VERSION,
  PRODUCTION_QUALIFICATION_MANIFEST_VERSION,
  PRODUCTION_QUALIFICATION_NODE_CONTROL_IMAGE,
  PRODUCTION_QUALIFICATION_PLATFORM,
  PRODUCTION_QUALIFICATION_POSTGRES_CLIENT,
  PRODUCTION_QUALIFICATION_POSTGRES_SERVER_VERSION,
} from "../../scripts/production-qualification-manifest";
import {
  createPostgresFirebaseAuthorizedGraphSnapshotRuntime,
  projectFirebaseAuthorizedGraphSnapshotLoad,
} from "./firebase-authorized-graph-snapshot-runtime";
import { createPostgresFirebaseAuthorizedMemoryReadRuntime } from
  "./firebase-authorized-memory-read-runtime";
import { createPostgresFirebaseChatGenerationContextSource } from
  "./firebase-chat-generation-context-source";
import { createPostgresFirebaseAuthorizedMemoryServiceApp } from
  "./firebase-authorized-memory-service-app";
import { createPostgresFirebaseAuthorizedMemoryExportRuntime } from
  "./firebase-authorized-memory-export-runtime";
import { createPostgresFirebaseAuthorizedLedgerRuntime } from "./firebase-authorized-ledger-runtime";
import { createPostgresPredicateBatchWorkInputRepository } from "./predicate-batch-work-input";
import { createPostgresPredicateBatchOneShotRuntime } from "./predicate-batch-one-shot-runtime";
import { createPostgresProductProjectionWriteRepository } from "./product-projection-repository";
import { createPostgresLegacyPropositionMigrationRepository } from
  "./legacy-proposition-migration-repository";
import { createPostgresTombstoneRestoreTarget } from "./tombstone-restore-target";
import { createPostgresRestoreReplayCheckpointRepository } from
  "./restore-replay-checkpoint-repository";
import {
  createPostgresMemoryReadGroundingRepository,
  createPostgresMemoryShadowResultRepository,
} from "./memory-experiment-repository";
import { createPostgresListenFinalizationRepository } from "./listen-finalization-repository";
import { createPostgresListenFormationOutboxRepository } from "./listen-formation-outbox";
import {
  LISTEN_CAPTURE_APPEND_VERSION,
  LISTEN_CAPTURE_FINALIZE_VERSION,
  LISTEN_CAPTURE_INTERRUPT_VERSION,
  LISTEN_CAPTURE_OPEN_VERSION,
  LISTEN_CAPTURE_RESUME_VERSION,
} from "../../apps/service/stores/listen-finalization-repository";
import { materializeListenFormationSnapshot } from
  "../../apps/service/listen/formation-ingestion";
import { defineListenAttributionBeliefInputStager } from
  "../../apps/service/listen/attribution-belief-input-source";
import { ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION } from
  "../../apps/service/workers/attribution-belief-shadow-producer";
import {
  createPostgresAcceptedFormationBeliefSource,
  createPostgresListenAttributionBeliefInputRepository,
} from "./listen-attribution-belief-input";
import { createPostgresListenAttributionBeliefOneShotRuntime } from
  "./listen-attribution-belief-one-shot-runtime";
import {
  createPostgresMemoryQueryEvaluationGraphSource,
  createPostgresMemoryQueryEvaluationInputRepository,
} from "./memory-query-evaluation-source";
import { createPostgresMemoryQueryEvaluationOneShotRuntime } from
  "./memory-query-evaluation-one-shot-runtime";
import { POSTGRES_MIGRATIONS } from "./migrations/manifest";
import { runPostgresMigrations } from "./migrations/runner";
import { createPostgresJsTransactionPool, type CloseablePostgresTransactionPool } from "./postgresjs";
import { createPostgresProductionRuntimeReadiness } from "./production-runtime-readiness";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";
import { SqliteLedger } from "../sqlite";
import { DeterministicFakeModel, type ModelInvokeRequest } from "../model/port";

const explicitTestUrl = process.env["OMI_TEST_POSTGRES_URL"];
const realTest = explicitTestUrl ? describe : describe.skip;
const QUALIFICATION_MANIFEST_RECEIPT = parseProductionQualificationManifest({
  version: PRODUCTION_QUALIFICATION_MANIFEST_VERSION,
  source: {
    source_commit: "a".repeat(40),
    dependency_artifact_version: PRODUCTION_QUALIFICATION_DEPENDENCY_ARTIFACT_VERSION,
    dependency_artifact_receipt_digest: "0".repeat(64),
    platform: PRODUCTION_QUALIFICATION_PLATFORM,
    bun_image: PRODUCTION_QUALIFICATION_BUN_IMAGE,
    node_control_image: PRODUCTION_QUALIFICATION_NODE_CONTROL_IMAGE,
    postgres_server_version_num: PRODUCTION_QUALIFICATION_POSTGRES_SERVER_VERSION,
    postgres_client: PRODUCTION_QUALIFICATION_POSTGRES_CLIENT,
    migration_manifest_digest: currentProductionMigrationManifestDigest(),
  },
  workload: {
    account_count: 2, duration_seconds: 60,
    memory_read_steady_rps: 1, memory_read_burst_rps: 1,
    memory_read_steady_concurrency: 1, memory_read_burst_concurrency: 1,
    mcp_steady_rps: 0, mcp_burst_rps: 0,
    mcp_steady_concurrency: 0, mcp_burst_concurrency: 0,
    shadow_jobs_per_minute: 1,
  },
  objectives: {
    p95_memory_read_ms: 1, p95_mcp_ms: 1, p95_pool_acquire_ms: 1,
    cold_start_ms: 1, cpu_millicores: 1, rss_mib: 1, graceful_shutdown_ms: 1,
  },
  connections: {
    cloud_sql_total: 7, serving: 1, candidate: 1, rollback: 1,
    jobs: 1, migration: 1, operator: 1, emergency: 1,
  },
  recovery: {
    authoritative_rpo_seconds: 0, authoritative_rto_seconds: 1,
    rebuildable_rpo_seconds: 0, rebuildable_rto_seconds: 1,
  },
  model_resources: "0123456789abcdef".split("").map((character) => ({
    resource_digest: character.repeat(64), max_concurrency: 1,
  })),
});
const QUALIFICATION_DATABASE_GENERATION_DIGEST = "d".repeat(64);
const QUALIFICATION_RESTORE_RELEASE = Object.freeze({
  database_generation_digest: QUALIFICATION_DATABASE_GENERATION_DIGEST,
  restore_release_revision: 1,
  restore_release_content_hash: "9".repeat(64),
});

const issueQualificationContext = (
  input: Omit<AuthorizedLedgerWriteContextInput, "authorization_state_digest">,
  authority: AuthorityStateRow,
  nowEpochSeconds: number,
) => createAuthorizedLedgerWriteContextIssuer().issueRestored({
  ...input,
  authorization_state_digest: authorizationStateDigest(
    authority,
    QUALIFICATION_RESTORE_RELEASE,
  ),
}, QUALIFICATION_RESTORE_RELEASE, nowEpochSeconds);

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
  snapshotValue?: Readonly<FormationInputSnapshot>,
): DurableMemoryWorkAcceptanceRequest => {
  const snapshot = snapshotValue ?? durableWorkFormationSnapshot(accountId, suffix);
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
    owner_account_id: accountId, unit_ref: snapshot.session_id, policy, strategies: [strategy],
  });
  const inputs: readonly DurableMemoryWorkInputManifestEntry[] = formationWorkInputManifest(
    snapshot,
  );
  const accepted: AcceptedDurableMemoryWork = {
    version: DURABLE_MEMORY_WORK_VERSION, job_id: snapshot.work_id,
    owner_account_id: accountId, account_epoch: 12,
    lifecycle_state: "active", deletion_epoch: null, work_kind: "formation",
    input_frontier: snapshot.input_frontier,
    input_digest: durableMemoryWorkInputManifestDigest(inputs),
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
  let modelLockPool: CloseablePostgresTransactionPool;

  beforeAll(() => {
    if (!explicitTestUrl) throw new Error("OMI_TEST_POSTGRES_URL is required");
    const parsed = new URL(explicitTestUrl);
    if (parsed.hostname !== "127.0.0.1" || parsed.protocol !== "postgres:") {
      throw new Error("postgres_test_not_loopback_only");
    }
    ownerSql = postgres(explicitTestUrl, { max: 2, prepare: true });
    pool = createPostgresJsTransactionPool({ connectionString: explicitTestUrl, maxConnections: 1 });
    modelLockPool = createPostgresJsTransactionPool({ connectionString: explicitTestUrl, maxConnections: 1 });
  });

  afterAll(async () => {
    await pool?.close();
    await modelLockPool?.close();
    await ownerSql?.end({ timeout: 5 });
  });

  test("runs the pinned server, creates only the test roles, and reapplies all migrations as no-ops", async () => {
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
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omi_platform_cleanup') THEN
          CREATE ROLE omi_platform_cleanup NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omi_platform_restore') THEN
          CREATE ROLE omi_platform_restore NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omi_platform_restore_operator') THEN
          CREATE ROLE omi_platform_restore_operator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
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
    await ownerSql.unsafe("DELETE FROM omi_memory.postgres_restore_admission_heads");
    await ownerSql.unsafe("DELETE FROM omi_memory.postgres_restore_admission_revisions");
    const legacySuffix = randomUUID();
    const legacyAccountId = `account:restore-gate-probe:${legacySuffix}`;
    const legacyPrincipalId = `principal:restore-gate-probe:${legacySuffix}`;
    const legacyApplicationId = "app:restore-gate-probe";
    const legacyCredentialId = `credential:restore-gate-probe:${legacySuffix}`;
    const legacyGrantId = `grant:restore-gate-probe:${legacySuffix}`;
    const legacyNow = Math.floor(Date.now() / 1_000);
    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(
        "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)", [legacyAccountId],
      );
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
          (account_id, control_revision, account_generation, account_epoch,
           lifecycle_state, deletion_epoch, observed_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, 1, 'new', 1, 'active', NULL, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [legacyAccountId, "a".repeat(64)]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
          (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 1, 1, 1)`, [legacyAccountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_revisions
          (account_id, principal_id, application_id, credential_id,
           credential_generation, credential_kind, lifecycle,
           authentication_strength, expires_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, $2, $3, $4, 1, 'service', 'active', 'service-workload',
                to_timestamp($5), 'credential-v1', '{}'::jsonb, $6)`, [
        legacyAccountId, legacyPrincipalId, legacyApplicationId, legacyCredentialId,
        legacyNow + 7_200, "b".repeat(64),
      ]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_heads
          (account_id, application_id, credential_id, credential_generation)
        VALUES ($1, $2, $3, 1)`, [legacyAccountId, legacyApplicationId, legacyCredentialId]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 1, 'memories.write', $4, 1, 'active', true,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`, [
        legacyAccountId, legacyApplicationId, legacyCredentialId, legacyGrantId,
        "c".repeat(64),
      ]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_heads
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version)
        VALUES ($1, $2, $3, 1, 'memories.write', $4, 1)`, [
        legacyAccountId, legacyApplicationId, legacyCredentialId, legacyGrantId,
      ]);
    });
    await ownerSql.unsafe(`INSERT INTO omi_memory.postgres_restore_admission_revisions
        (database_generation_digest, release_revision, state, restore_id,
         restored_snapshot_digest, checkpoint_candidate_digest,
         checkpoint_evidence_digest, first_approval_subject_digest,
         first_approval_receipt_digest, second_approval_subject_digest,
         second_approval_receipt_digest, manual_release_receipt_digest,
         previous_release_revision, content_hash)
      VALUES ($1, 1, 'released', 'restore:qualification-generation', $2, $3, $4,
              $5, $6, $7, $8, $9, NULL, $10)
      ON CONFLICT (database_generation_digest, release_revision) DO NOTHING
    `, [
      QUALIFICATION_DATABASE_GENERATION_DIGEST,
      "1".repeat(64), "2".repeat(64), "3".repeat(64), "4".repeat(64),
      "5".repeat(64), "6".repeat(64), "7".repeat(64), "8".repeat(64),
      "9".repeat(64),
    ]);
    let enteredLegacyAuthority!: () => void;
    const legacyAuthorityEntered = new Promise<void>((resolve) => {
      enteredLegacyAuthority = resolve;
    });
    let releaseLegacyAuthority!: () => void;
    const legacyAuthorityRelease = new Promise<void>((resolve) => {
      releaseLegacyAuthority = resolve;
    });
    const legacyAuthority = pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async (connection) => {
        await connection.query({
          name: "qualification.restore_gate_set_role",
          text: "SET LOCAL ROLE omi_platform_application",
          values: [],
        });
        const legacyRows = await connection.query<{ account_id: string }>({
          name: "qualification.restore_gate_hold_unbound",
          text: `SELECT * FROM omi_memory.lock_unfenced_authority_state(
            $1, $2, $3, $4, 1, 'memories.write', $5
          )`,
          values: [legacyAccountId, legacyPrincipalId, legacyApplicationId,
            legacyCredentialId, legacyGrantId],
        });
        expect(legacyRows).toHaveLength(1);
        expect(legacyRows[0]?.account_id).toBe(legacyAccountId);
        enteredLegacyAuthority();
        await legacyAuthorityRelease;
      },
    );
    await legacyAuthorityEntered;
    let headInsertFinished = false;
    const headInsert = ownerSql.unsafe(`INSERT INTO omi_memory.postgres_restore_admission_heads
        (database_generation_digest, release_revision)
      VALUES ($1, 1)
      ON CONFLICT (database_generation_digest) DO UPDATE
        SET release_revision = EXCLUDED.release_revision,
            updated_at = transaction_timestamp()`, [QUALIFICATION_DATABASE_GENERATION_DIGEST])
      .then(() => { headInsertFinished = true; });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(headInsertFinished).toBe(false);
    releaseLegacyAuthority();
    await legacyAuthority;
    await headInsert;
    expect(headInsertFinished).toBe(true);
  }, 120_000);

  test("admits startup only for the exact applied manifest and released database generation", async () => {
    const appRolePool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(
        options: Parameters<PostgresTransactionPool["withTransaction"]>[0],
        callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
      ) => pool.withTransaction(options, async (connection) => {
        await connection.query({
          name: "qualification.production_readiness.set_application_role",
          text: "SET LOCAL ROLE omi_platform_application",
          values: [],
        });
        return callback(connection);
      }),
    });

    const readiness = createPostgresProductionRuntimeReadiness(
      appRolePool,
      QUALIFICATION_DATABASE_GENERATION_DIGEST,
    );
    await expect(readiness.check()).resolves.toBe(true);
    await expect(createPostgresProductionRuntimeReadiness(
      appRolePool,
      "0".repeat(64),
    ).check()).resolves.toBe(false);

    await expect(appRolePool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read only" },
      async (connection) => connection.query({
        name: "qualification.production_readiness.direct_history_denied",
        text: "SELECT version FROM omi_memory.platform_schema_migrations",
        values: [],
      }),
    )).rejects.toMatchObject({ code: "42501" });
    await expect(appRolePool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read only" },
      async (connection) => connection.query({
        name: "qualification.production_readiness.direct_release_denied",
        text: "SELECT database_generation_digest FROM omi_memory.postgres_restore_admission_heads",
        values: [],
      }),
    )).rejects.toMatchObject({ code: "42501" });
  });

  test("releases one exact restored generation through the single GCP-operator role", async () => {
    const generationDigest = createHash("sha256").update(randomUUID()).digest("hex");
    const checkpointContentHash = "a".repeat(64);
    const candidateDigest = "b".repeat(64);
    const evidenceDigest = "c".repeat(64);
    const releaseContentHash = "d".repeat(64);
    await ownerSql.unsafe(`INSERT INTO omi_memory.postgres_restore_admission_revisions
        (database_generation_digest, release_revision, state, restore_id,
         restored_snapshot_digest, checkpoint_candidate_digest,
         checkpoint_evidence_digest, previous_release_revision, content_hash,
         release_authority)
      VALUES ($1, 1, 'checkpointed', $2, $3, $4, $5, NULL, $6, NULL)`, [
      generationDigest, `restore:gcp-operator:${randomUUID()}`, "e".repeat(64),
      candidateDigest, evidenceDigest, checkpointContentHash,
    ]);
    await ownerSql.unsafe(`INSERT INTO omi_memory.postgres_restore_admission_heads
        (database_generation_digest, release_revision)
      VALUES ($1, 1)`, [generationDigest]);

    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      return transaction.unsafe(`SELECT * FROM omi_memory.release_postgres_restore_generation_v2(
        $1, 1, $2, $3, $4, 2, $5
      )`, [generationDigest, checkpointContentHash, candidateDigest, evidenceDigest, releaseContentHash]);
    })).rejects.toMatchObject({ code: "42501" });

    const release = await ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_restore_operator");
      return transaction.unsafe<{ result: string; release_revision: string; release_content_hash: string }[]>(
        `SELECT * FROM omi_memory.release_postgres_restore_generation_v2(
          $1, 1, $2, $3, $4, 2, $5
        )`, [generationDigest, checkpointContentHash, candidateDigest, evidenceDigest, releaseContentHash],
      );
    });
    expect(release).toEqual([{
      result: "released", release_revision: "2", release_content_hash: releaseContentHash,
    }]);
    const replay = await ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_restore_operator");
      return transaction.unsafe<{ result: string }[]>(
        `SELECT * FROM omi_memory.release_postgres_restore_generation_v2(
          $1, 1, $2, $3, $4, 2, $5
        )`, [generationDigest, checkpointContentHash, candidateDigest, evidenceDigest, releaseContentHash],
      );
    });
    expect(replay[0]?.result).toBe("replayed");
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_restore_operator");
      return transaction.unsafe(`SELECT * FROM omi_memory.release_postgres_restore_generation_v2(
        $1, 1, $2, $3, $4, 2, $5
      )`, [generationDigest, checkpointContentHash, candidateDigest, evidenceDigest, "f".repeat(64)]);
    })).rejects.toMatchObject({ code: "P3603" });

    const persisted = await ownerSql.unsafe<{
      release_authority: string;
      first_approval_subject_digest: string | null;
      second_approval_subject_digest: string | null;
      manual_release_receipt_digest: string | null;
    }[]>(`SELECT release_authority, first_approval_subject_digest,
          second_approval_subject_digest, manual_release_receipt_digest
        FROM omi_memory.postgres_restore_admission_revisions
        WHERE database_generation_digest = $1 AND release_revision = 2`, [generationDigest]);
    expect(persisted).toEqual([{
      release_authority: "gcp_iam",
      first_approval_subject_digest: null,
      second_approval_subject_digest: null,
      manual_release_receipt_digest: null,
    }]);
  });

  test("Listen capture persists an atomic finalization boundary with exact replay and rollback", async () => {
    const suffix = randomUUID();
    const accountId = `account:listen-qualification:${suffix}`;
    const principalId = `principal:listen-qualification:${suffix}`;
    const applicationId = `app:listen-qualification:${suffix}`;
    const credentialId = `credential:listen-qualification:${suffix}`;
    const grantId = `grant:listen-qualification:${suffix}`;
    const controlHash = "a".repeat(64);
    const credentialHash = "b".repeat(64);
    const grantHash = "c".repeat(64);
    const now = Math.floor(Date.now() / 1_000);
    const startedAt = "2026-08-13T00:00:00.000Z";
    const appendedAt = "2026-08-13T00:00:30.000Z";
    const interruptedAt = "2026-08-13T00:00:40.000Z";
    const resumedAt = "2026-08-13T00:00:50.000Z";
    const endedAt = "2026-08-13T00:01:00.000Z";
    const sessionId = `listen-session:${suffix}`;
    const conversationId = `listen-conversation:${suffix}`;
    const finalizationId = `listen-finalization:${sha256CanonicalContent({
      owner_account_id: accountId, session_id: sessionId,
    })}`;
    const openRequest = {
      version: LISTEN_CAPTURE_OPEN_VERSION,
      session_id: sessionId,
      conversation_id: conversationId,
      client_conversation_id: `client-conversation:${suffix}`,
      started_at: startedAt,
      source: "omi-listen",
      codec: "pcm_s16le",
      sample_rate: 16_000,
      channels: 1,
    } as const;
    const firstSegment = {
      version: LISTEN_CAPTURE_APPEND_VERSION,
      session_id: sessionId,
      segment: { id: `segment:${suffix}:1`, text: "I prefer a quiet workspace.", is_user: true, start: 0, end: 2 },
      appended_at: appendedAt,
    } as const;
    const secondSegment = {
      version: LISTEN_CAPTURE_APPEND_VERSION,
      session_id: sessionId,
      segment: { id: `segment:${suffix}:2`, text: "The other speaker is not the owner.", is_user: false, start: 2, end: 4 },
      appended_at: appendedAt,
    } as const;

    const authorityRow: AuthorityStateRow = {
      account_id: accountId,
      principal_id: principalId,
      application_id: applicationId,
      credential_id: credentialId,
      credential_generation: 4,
      capability: "listen.capture.write",
      grant_id: grantId,
      grant_version: 1,
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

    try {
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
          VALUES ($1, $2, $3, 4, 'listen.capture.write', $4, 1, 'active', true,
                  '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
        [accountId, applicationId, credentialId, grantId, grantHash]);
        await transaction.unsafe(`INSERT INTO omi_memory.application_grant_heads
            (account_id, application_id, credential_id, credential_generation,
             capability, grant_id, grant_version)
          VALUES ($1, $2, $3, 4, 'listen.capture.write', $4, 1)`,
        [accountId, applicationId, credentialId, grantId]);
      });

      const context = issueQualificationContext({
        context_version: "authorized-ledger-write-context-v1",
        principal_id: principalId,
        account_id: accountId,
        application_id: applicationId,
        credential_id: credentialId,
        credential_generation: 4,
        capability: "listen.capture.write",
        grant_id: grantId,
        grant_version: 1,
        account_epoch: 12,
        destination_activation_revision: 17,
        lifecycle_state: "active",
        deletion_epoch: null,
        authentication_strength: "firebase-id-token",
        issued_at_epoch_seconds: now - 60,
        expires_at_epoch_seconds: now + 3_600,
      }, authorityRow, now);
      const appRolePool: PostgresTransactionPool = Object.freeze({
        withTransaction: async <Result>(
          options: Parameters<PostgresTransactionPool["withTransaction"]>[0],
          callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
        ) => pool.withTransaction(options, async (connection) => {
          await connection.query({
            name: "qualification.listen.set_application_role",
            text: "SET LOCAL ROLE omi_platform_application",
            values: [],
          });
          return callback(connection);
        }),
      });
      const repository = createPostgresListenFinalizationRepository({ pool: appRolePool });

      await expect(repository.open(context, openRequest)).resolves.toEqual({
        kind: "opened", session_id: sessionId, conversation_id: conversationId,
      });
      await expect(repository.open(context, openRequest)).resolves.toEqual({
        kind: "replayed", session_id: sessionId, conversation_id: conversationId,
      });
      await expect(repository.append(context, firstSegment)).resolves.toMatchObject({
        kind: "appended", session_id: sessionId, segment_id: firstSegment.segment.id, ordinal: 0,
      });
      await expect(repository.append(context, secondSegment)).resolves.toMatchObject({
        kind: "appended", session_id: sessionId, segment_id: secondSegment.segment.id, ordinal: 1,
      });
      await expect(repository.append(context, firstSegment)).resolves.toMatchObject({
        kind: "replayed", session_id: sessionId, segment_id: firstSegment.segment.id, ordinal: 0,
      });
      await expect(repository.append(context, {
        ...firstSegment, segment: { ...firstSegment.segment, text: "changed bytes" },
      })).rejects.toMatchObject({ code: "idempotency_conflict" });
      await expect(repository.interrupt(context, {
        version: LISTEN_CAPTURE_INTERRUPT_VERSION, session_id: sessionId, interrupted_at: interruptedAt,
      })).resolves.toMatchObject({ kind: "interrupted", session_id: sessionId, state_sequence: 1 });
      await expect(repository.resume(context, {
        version: LISTEN_CAPTURE_RESUME_VERSION, session_id: sessionId, resumed_at: resumedAt,
      })).resolves.toMatchObject({ kind: "resumed", session_id: sessionId, state_sequence: 2 });

      const finalizeRequest = {
        version: LISTEN_CAPTURE_FINALIZE_VERSION,
        session_id: sessionId, terminal_status: "completed" as const, ended_at: endedAt,
      };
      const sealed = await repository.finalize(context, finalizeRequest);
      expect(sealed).toMatchObject({ kind: "sealed", finalization_id: finalizationId, segment_count: 2 });
      await expect(repository.finalize(context, finalizeRequest)).resolves.toEqual({
        ...sealed, kind: "replayed",
      });
      await expect(repository.finalize(context, {
        ...finalizeRequest, ended_at: "2026-08-13T00:01:01.000Z",
      })).rejects.toMatchObject({ code: "idempotency_conflict" });
      await expect(repository.append(context, {
        ...secondSegment, segment: { ...secondSegment.segment, id: `segment:post-seal:${suffix}` },
      })).rejects.toMatchObject({ code: "transition_invalid" });

      const persisted = await ownerSql.unsafe<{
        sessions: number; states: number; segments: number; finalizations: number;
        intents: number; outbox: number;
      }[]>(`SELECT
        (SELECT count(*)::int FROM omi_memory.listen_capture_sessions
          WHERE account_id = $1 AND session_id = $2) AS sessions,
        (SELECT count(*)::int FROM omi_memory.listen_capture_session_state_revisions
          WHERE account_id = $1 AND session_id = $2) AS states,
        (SELECT count(*)::int FROM omi_memory.listen_capture_segments
          WHERE account_id = $1 AND session_id = $2) AS segments,
        (SELECT count(*)::int FROM omi_memory.listen_formation_finalizations
          WHERE account_id = $1 AND session_id = $2) AS finalizations,
        (SELECT count(*)::int FROM omi_memory.listen_conversation_finalization_intents
          WHERE account_id = $1 AND conversation_id = $3) AS intents,
        (SELECT count(*)::int FROM omi_memory.listen_formation_outbox
          WHERE account_id = $1 AND finalization_id = $4) AS outbox`,
      [accountId, sessionId, conversationId, finalizationId]);
      expect([...persisted]).toEqual([{
        sessions: 1, states: 4, segments: 2, finalizations: 1, intents: 1, outbox: 1,
      }]);

      const acceptGrantId = `grant:listen-formation:${suffix}`;
      const acceptGrantHash = "d".repeat(64);
      await ownerSql.begin(async (transaction) => {
        await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
            (account_id, application_id, credential_id, credential_generation,
             capability, grant_id, grant_version, lifecycle, enabled, scopes,
             record_schema_version, record_json, content_hash)
          VALUES ($1, $2, $3, 4, 'memories.work.accept', $4, 1, 'active', true,
                  '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
        [accountId, applicationId, credentialId, acceptGrantId, acceptGrantHash]);
        await transaction.unsafe(`INSERT INTO omi_memory.application_grant_heads
            (account_id, application_id, credential_id, credential_generation,
             capability, grant_id, grant_version)
          VALUES ($1, $2, $3, 4, 'memories.work.accept', $4, 1)`,
        [accountId, applicationId, credentialId, acceptGrantId]);
      });
      const acceptAuthorityRow: AuthorityStateRow = {
        ...authorityRow, capability: "memories.work.accept", grant_id: acceptGrantId,
        grant_content_hash: acceptGrantHash,
      };
      const acceptContext = issueQualificationContext({
        context_version: "authorized-ledger-write-context-v1", principal_id: principalId,
        account_id: accountId, application_id: applicationId, credential_id: credentialId,
        credential_generation: 4, capability: "memories.work.accept",
        grant_id: acceptGrantId, grant_version: 1, account_epoch: 12,
        destination_activation_revision: 17, lifecycle_state: "active", deletion_epoch: null,
        authentication_strength: "firebase-id-token", issued_at_epoch_seconds: now - 60,
        expires_at_epoch_seconds: now + 3_600,
      }, acceptAuthorityRow, now);
      const delivery = createPostgresListenFormationOutboxRepository({
        pool: appRolePool, lease_duration_seconds: 1,
        retry_delay_seconds: 10, max_attempts: 3,
      });
      const claimed = await delivery.claimNext(acceptContext);
      expect(claimed.kind).toBe("claimed");
      if (claimed.kind !== "claimed") throw new Error("listen_delivery_not_claimed");
      const loaded = await delivery.load(acceptContext, claimed.lease);
      expect(loaded).toMatchObject({
        kind: "found",
        payload: {
          owner_account_id: accountId, finalization_id: finalizationId,
          formation_work_id: sealed.formation_work_id,
          finalization: { transcript_digest: sealed.transcript_digest },
        },
      });
      if (loaded.kind !== "found") throw new Error("listen_delivery_not_loaded");
      expect(loaded.payload.finalization.segments).toHaveLength(2);
      expect(loaded.payload.finalization.segments.map((segment) => segment.is_user))
        .toEqual([true, false]);

      const beliefSnapshot = materializeListenFormationSnapshot({
        finalization: loaded.payload.finalization,
        graph_snapshot: {
          owner_account_id: accountId, graph_generation: 0,
          claims: [], entities: [], predicates: [], identity_authorizations: [], adjacency: [],
        },
        source_language: "en", account_timezone: "UTC",
        reference_clock_query_at: "2026-08-13T00:01:01.000Z",
        policy_version: "policy:listen:qualification:v1",
        predicate_alias_generation: "predicate:0",
        authorization_generation: "authorization:0", stm_generation: "stm:0",
      });
      const beliefAcceptance = durableWorkAcceptanceRequest(
        accountId, `${suffix}:listen-belief`, now, 30, 10, beliefSnapshot,
      );
      const beliefPending = acceptDurableMemoryWork(beliefAcceptance.accepted_work);
      const beliefStageBody = { pending_job: beliefPending, snapshot: beliefSnapshot };
      const formationInputRepository = createPostgresFormationWorkInputRepository({ pool: appRolePool });
      await expect(formationInputRepository.stage(acceptContext, {
        ...beliefStageBody,
        request_digest: formationWorkInputStageRequestDigest(beliefStageBody),
      })).resolves.toMatchObject({ kind: "staged", input: { job_id: beliefSnapshot.work_id } });
      await expect(createPostgresDurableMemoryWorkAcceptanceRepository({ pool: appRolePool })
        .accept(acceptContext, beliefAcceptance)).resolves.toMatchObject({
        kind: "accepted", job: { job_id: beliefSnapshot.work_id },
      });

      const shadowGrantId = `grant:listen-belief:${suffix}`;
      const shadowGrantHash = "f".repeat(64);
      await ownerSql.begin(async (transaction) => {
        await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
            (account_id, application_id, credential_id, credential_generation,
             capability, grant_id, grant_version, lifecycle, enabled, scopes,
             record_schema_version, record_json, content_hash)
          VALUES ($1, $2, $3, 4, 'memories.experiments.shadow', $4, 1, 'active', true,
                  '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
        [accountId, applicationId, credentialId, shadowGrantId, shadowGrantHash]);
        await transaction.unsafe(`INSERT INTO omi_memory.application_grant_heads
            (account_id, application_id, credential_id, credential_generation,
             capability, grant_id, grant_version)
          VALUES ($1, $2, $3, 4, 'memories.experiments.shadow', $4, 1)`,
        [accountId, applicationId, credentialId, shadowGrantId]);
      });
      const shadowAuthorityRow: AuthorityStateRow = {
        ...authorityRow, capability: "memories.experiments.shadow",
        grant_id: shadowGrantId, grant_content_hash: shadowGrantHash,
      };
      const shadowContext = issueQualificationContext({
        context_version: "authorized-ledger-write-context-v1", principal_id: principalId,
        account_id: accountId, application_id: applicationId, credential_id: credentialId,
        credential_generation: 4, capability: "memories.experiments.shadow",
        grant_id: shadowGrantId, grant_version: 1, account_epoch: 12,
        destination_activation_revision: 17, lifecycle_state: "active", deletion_epoch: null,
        authentication_strength: "firebase-id-token", issued_at_epoch_seconds: now - 60,
        expires_at_epoch_seconds: now + 3_600,
      }, shadowAuthorityRow, now);
      const beliefSource = createPostgresAcceptedFormationBeliefSource({ pool: appRolePool });
      const beliefRepository = createPostgresListenAttributionBeliefInputRepository({
        pool: appRolePool,
      });
      const beliefStager = defineListenAttributionBeliefInputStager({
        source: beliefSource, repository: beliefRepository,
      });
      const beliefStage = await beliefStager.stageAcceptedFormation(
        shadowContext, beliefSnapshot.work_id,
      );
      expect(beliefStage).toMatchObject({ kind: "staged", set: { inputs: [{}, {}] } });
      if (beliefStage.kind !== "staged") throw new Error("listen_belief_not_staged");
      await expect(beliefStager.stageAcceptedFormation(shadowContext, beliefSnapshot.work_id))
        .resolves.toMatchObject({ kind: "replayed", set: { set_digest: beliefStage.set.set_digest } });
      const beliefRows = await ownerSql.unsafe<{ count: number; contains_text: boolean }[]>(`SELECT
        count(*)::int AS count,
        bool_or(input_json::text LIKE '%quiet workspace%') AS contains_text
        FROM omi_memory.memory_listen_attribution_belief_inputs
        WHERE account_id = $1 AND formation_work_id = $2`,
      [accountId, beliefSnapshot.work_id]);
      expect([...beliefRows]).toEqual([{ count: 2, contains_text: false }]);

      const beliefStrategy = (role: "baseline" | "candidate") => registerMemoryStrategy({
        version: MEMORY_STRATEGY_VERSION,
        strategy_id: `strategy:listen-belief:${role}:${suffix}`,
        work_kind: "identity_cluster",
        coordinates: {
          strategy_version: `listen-belief:${role}:v1`,
          model_version: "injected-calibrator:qualification:v1",
          prompt_version: `listen-belief:${role}:prompt:v1`,
          policy_version: "listen-belief:shadow-policy:v1",
          code_version: "listen-belief:shadow-code:v1",
          schema_version: "listen-belief:shadow-schema:v1",
          tokenizer_version: "none", tool_version: "none",
          result_contract_version: ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION,
          speaker_strategy_version: "none", boundary_strategy_version: "none",
        },
      });
      const beliefStrategies = [beliefStrategy("baseline"), beliefStrategy("candidate")];
      const beliefPolicy = defineMemoryStrategyAssignmentPolicy({
        policy_id: `policy:listen-belief:${suffix}`,
        work_kind: "identity_cluster", unit_kind: "session",
        key_version: "listen-belief-assignment-key:v1",
        authority_strategy_id: beliefStrategies[0]!.strategy_id,
        shadow_candidates: [{
          strategy_id: beliefStrategies[1]!.strategy_id, basis_points: 10_000,
        }],
      }, beliefStrategies);
      const beliefInput = beliefStage.set.inputs[0]!;
      const beliefAssignment = createMemoryStrategyAssigner(new Uint8Array(32).fill(37)).assign({
        owner_account_id: accountId, unit_ref: beliefInput.input_ref,
        policy: beliefPolicy, strategies: beliefStrategies,
      });
      let calibratorCalls = 0;
      const beliefLossSignals: AbortSignal[] = [];
      const beliefRuntime = createPostgresListenAttributionBeliefOneShotRuntime({
        pool: appRolePool,
        model_pipeline_exclusivity: createPostgresProductionModelPipelineExclusivity(modelLockPool, QUALIFICATION_MANIFEST_RECEIPT),
        resolve_model_pipeline_resource: async () => Object.freeze({
          version: MODEL_PIPELINE_RESOURCE_VERSION,
          resource_digest: "d".repeat(64),
        }),
        resolve_calibrator: async (_strategy, evaluationRole) => ({
          calibrate: async (
            calibrationRequest: AttributionCalibrationRequest,
            lossSignal?: AbortSignal,
          ) => {
            calibratorCalls += 1;
            if (!(lossSignal instanceof AbortSignal)) throw new Error("missing belief loss signal");
            beliefLossSignals.push(lossSignal);
            const preferred = calibrationRequest.hypotheses.length === 1 ? 1_000_000
              : evaluationRole === "baseline" ? 600_000 : 750_000;
            const remaining = 1_000_000 - preferred;
            const otherCount = calibrationRequest.hypotheses.length - 1;
            let allocated = 0;
            return {
              probabilities: calibrationRequest.hypotheses.map((hypothesis, index) => {
                const probability = index === 0 ? preferred
                  : index === calibrationRequest.hypotheses.length - 1
                    ? remaining - allocated
                    : Math.floor(remaining / otherCount);
                if (index > 0) allocated += probability;
                return { hypothesis_id: hypothesis.hypothesis_id, probability_micros: probability };
              }),
            };
          },
        }),
      });
      const beliefReplayRequest = {
        input_ref: beliefInput.input_ref,
        input_frontier: beliefInput.input.graph_frontier,
        assignment_bundle: beliefAssignment,
        evaluation_run_id: `mer1_${sha256CanonicalContent({
          qualification: "listen-belief-one-shot", suffix,
        })}`,
        repeats: 2,
      };
      const beliefEvaluation = await beliefRuntime.run(shadowContext, beliefReplayRequest);
      expect(beliefEvaluation).toMatchObject({
        kind: "completed", model_calls: 4, reused_results: 0,
      });
      if (beliefEvaluation.kind !== "completed") throw new Error("listen_belief_evaluation_stopped");
      expect(beliefEvaluation.pairs).toHaveLength(2);
      expect(calibratorCalls).toBe(4);
      expect(beliefLossSignals).toHaveLength(4);
      const beliefEvaluationReplay = await beliefRuntime.run(shadowContext, beliefReplayRequest);
      expect(beliefEvaluationReplay).toMatchObject({
        kind: "completed", model_calls: 0, reused_results: 4,
      });
      expect(calibratorCalls).toBe(4);
      expect(JSON.stringify(beliefEvaluationReplay)).not.toContain("quiet workspace");
      const beliefEvaluationRows = await ownerSql.unsafe<{
        baselines: number; candidates: number; pairs: number;
      }[]>(`SELECT
        (SELECT count(*)::int FROM omi_memory.memory_strategy_evaluation_baselines
          WHERE account_id = $1 AND evaluation_run_id = $2) AS baselines,
        (SELECT count(*)::int FROM omi_memory.memory_strategy_shadow_results
          WHERE account_id = $1 AND evaluation_run_id = $2) AS candidates,
        (SELECT count(*)::int FROM omi_memory.memory_strategy_evaluation_pairs
          WHERE account_id = $1 AND evaluation_run_id = $2) AS pairs`,
      [accountId, beliefReplayRequest.evaluation_run_id]);
      expect([...beliefEvaluationRows]).toEqual([{ baselines: 2, candidates: 2, pairs: 2 }]);

      await ownerSql.begin(async (transaction) => {
        await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
            (account_id, application_id, credential_id, credential_generation,
             capability, grant_id, grant_version, lifecycle, enabled, scopes,
             record_schema_version, record_json, content_hash)
          VALUES ($1, $2, $3, 4, 'memories.experiments.shadow', $4, 2, 'revoked', false,
                  '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
        [accountId, applicationId, credentialId, shadowGrantId, "0".repeat(64)]);
        await transaction.unsafe(`UPDATE omi_memory.application_grant_heads
          SET grant_version = 2
          WHERE account_id = $1 AND application_id = $2 AND credential_id = $3
            AND credential_generation = 4 AND capability = 'memories.experiments.shadow'`,
        [accountId, applicationId, credentialId]);
      });
      await expect(beliefSource.load(shadowContext, beliefSnapshot.work_id)).resolves.toEqual({
        kind: "authorization_denied", reason: "grant_inactive",
      });
      await expect(beliefRuntime.run(shadowContext, beliefReplayRequest)).resolves.toEqual({
        kind: "source_stopped", stop_code: "authorization_or_context",
      });

      await expect(delivery.claimNext(acceptContext)).resolves.toEqual({ kind: "none_available" });
      const reclaimDeadline = Date.now() + 5_000;
      let reclaimed = await delivery.claimNext(acceptContext);
      while (reclaimed.kind === "none_available" && Date.now() < reclaimDeadline) {
        await new Promise((resolve) => setTimeout(resolve, 100));
        reclaimed = await delivery.claimNext(acceptContext);
      }
      expect(reclaimed.kind).toBe("claimed");
      if (reclaimed.kind !== "claimed") throw new Error("listen_delivery_not_reclaimed");
      expect(reclaimed.lease.lease_fence).toBe(claimed.lease.lease_fence + 1);
      await expect(delivery.recordFailure(acceptContext, claimed.lease, {
        code: "dependency_unavailable",
      })).resolves.toEqual({ kind: "stale_lease" });
      const failureResult = await delivery.recordFailure(acceptContext, reclaimed.lease, {
        code: "dependency_unavailable",
      });
      expect(failureResult).toEqual({ kind: "recorded" });
      await expect(delivery.claimNext(acceptContext)).resolves.toEqual({ kind: "none_available" });
      const deliveryRows = await ownerSql.unsafe<{ revisions: number; heads: number }[]>(`SELECT
        (SELECT count(*)::int FROM omi_memory.listen_formation_delivery_revisions
          WHERE account_id = $1 AND outbox_id = $2) AS revisions,
        (SELECT count(*)::int FROM omi_memory.listen_formation_delivery_heads
          WHERE account_id = $1 AND outbox_id = $2) AS heads`,
      [accountId, reclaimed.lease.outbox_id]);
      expect([...deliveryRows]).toEqual([{ revisions: 3, heads: 1 }]);

      const emptySessionId = `listen-empty:${suffix}`;
      await expect(repository.open(context, {
        ...openRequest, session_id: emptySessionId,
        conversation_id: `listen-empty-conversation:${suffix}`,
        client_conversation_id: `listen-empty-client:${suffix}`,
      })).resolves.toMatchObject({ kind: "opened", session_id: emptySessionId });
      await expect(repository.finalize(context, {
        version: LISTEN_CAPTURE_FINALIZE_VERSION, session_id: emptySessionId,
        terminal_status: "completed", ended_at: endedAt,
      })).rejects.toMatchObject({ code: "transition_invalid" });

      for (const table of [
        "listen_capture_sessions", "listen_capture_session_state_revisions",
        "listen_capture_segments", "listen_formation_finalizations",
        "listen_conversation_finalization_intents", "listen_formation_outbox",
        "listen_formation_delivery_revisions", "listen_formation_delivery_heads",
        "memory_listen_attribution_belief_inputs",
      ]) {
        await expect(ownerSql.begin(async (transaction) => {
          await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
          await transaction.unsafe(`SELECT 1 FROM omi_memory.${table} LIMIT 1`);
        })).rejects.toMatchObject({ code: "42501" });
      }
      await expect(ownerSql.begin(async (transaction) => {
        await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
        await transaction.unsafe("SELECT set_config('omi.account_id', $1, true)", [accountId]);
        await transaction.unsafe("SELECT set_config('omi.principal_id', $1, true)", [principalId]);
        await transaction.unsafe(`SELECT * FROM omi_memory.open_listen_capture_session(
          'missing-capability', 'missing-capability-conversation', NULL,
          transaction_timestamp(), NULL, 'pcm', 16000, 1, $1, $2
        )`, ["e".repeat(64), "f".repeat(64)]);
      })).rejects.toMatchObject({ code: "P1005" });

      const rollbackSessionId = `listen-rollback:${suffix}`;
      const rollbackConversationId = `listen-rollback-conversation:${suffix}`;
      const rollbackFinalizationId = `listen-finalization:${sha256CanonicalContent({
        owner_account_id: accountId, session_id: rollbackSessionId,
      })}`;
      await repository.open(context, {
        ...openRequest, session_id: rollbackSessionId, conversation_id: rollbackConversationId,
        client_conversation_id: `listen-rollback-client:${suffix}`,
      });
      await repository.append(context, {
        ...firstSegment, session_id: rollbackSessionId,
        segment: { ...firstSegment.segment, id: `segment:rollback:${suffix}` },
      });
      await ownerSql.unsafe(`
        CREATE OR REPLACE FUNCTION omi_memory.listen_qualification_fail_outbox()
        RETURNS trigger LANGUAGE plpgsql AS $fn$
        BEGIN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'qualification_listen_outbox_failure'; END
        $fn$;
        DROP TRIGGER IF EXISTS listen_qualification_fail_outbox
          ON omi_memory.listen_formation_outbox;
        CREATE TRIGGER listen_qualification_fail_outbox BEFORE INSERT
          ON omi_memory.listen_formation_outbox
          FOR EACH ROW EXECUTE FUNCTION omi_memory.listen_qualification_fail_outbox();
      `, [], { prepare: false });
      try {
        await expect(repository.finalize(context, {
          version: LISTEN_CAPTURE_FINALIZE_VERSION, session_id: rollbackSessionId,
          terminal_status: "completed", ended_at: endedAt,
        })).rejects.toMatchObject({ code: "persistence_failed" });
        const rollbackRows = await ownerSql.unsafe<{
          states: number; finalizations: number; intents: number; outbox: number;
        }[]>(`SELECT
          (SELECT count(*)::int FROM omi_memory.listen_capture_session_state_revisions
            WHERE account_id = $1 AND session_id = $2) AS states,
          (SELECT count(*)::int FROM omi_memory.listen_formation_finalizations
            WHERE account_id = $1 AND session_id = $2) AS finalizations,
          (SELECT count(*)::int FROM omi_memory.listen_conversation_finalization_intents
            WHERE account_id = $1 AND conversation_id = $3) AS intents,
          (SELECT count(*)::int FROM omi_memory.listen_formation_outbox
            WHERE account_id = $1 AND finalization_id = $4) AS outbox`,
        [accountId, rollbackSessionId, rollbackConversationId, rollbackFinalizationId]);
        expect([...rollbackRows]).toEqual([{ states: 1, finalizations: 0, intents: 0, outbox: 0 }]);
      } finally {
        await ownerSql.unsafe(`
          DROP TRIGGER IF EXISTS listen_qualification_fail_outbox
            ON omi_memory.listen_formation_outbox;
          DROP FUNCTION IF EXISTS omi_memory.listen_qualification_fail_outbox();
        `, [], { prepare: false });
      }

      await ownerSql.begin(async (transaction) => {
        await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
            (account_id, application_id, credential_id, credential_generation,
             capability, grant_id, grant_version, lifecycle, enabled, scopes,
             record_schema_version, record_json, content_hash)
          VALUES ($1, $2, $3, 4, 'listen.capture.write', $4, 2, 'revoked', false,
                  '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
        [accountId, applicationId, credentialId, grantId, "d".repeat(64)]);
        await transaction.unsafe(`UPDATE omi_memory.application_grant_heads
          SET grant_version = 2
          WHERE account_id = $1 AND application_id = $2 AND credential_id = $3
            AND credential_generation = 4 AND capability = 'listen.capture.write'`,
        [accountId, applicationId, credentialId]);
      });
      await expect(repository.open(context, {
        ...openRequest, session_id: `listen-revoked:${suffix}`,
        conversation_id: `listen-revoked-conversation:${suffix}`,
      })).rejects.toMatchObject({ code: "grant_inactive" });
    } finally {
      await ownerSql.begin(async (transaction) => {
        for (const table of [
          "listen_formation_delivery_heads", "listen_formation_delivery_revisions",
          "memory_listen_attribution_belief_inputs", "memory_formation_work_inputs",
          "memory_strategy_evaluation_pairs", "memory_strategy_evaluation_baselines",
          "memory_strategy_shadow_results",
          "memory_work_heads", "memory_work_state_revisions", "memory_work_input_manifest",
          "memory_work_acceptances", "memory_work_execution_policies",
          "memory_strategy_shadow_assignments", "memory_strategy_assignment_bundles",
          "memory_strategy_policy_shadows", "memory_strategy_assignment_policies",
          "memory_strategy_definitions",
          "listen_formation_outbox", "listen_conversation_finalization_intents",
          "listen_formation_finalizations", "listen_capture_segments",
          "listen_capture_session_state_revisions", "listen_capture_sessions",
        ]) {
          await transaction.unsafe(`DELETE FROM omi_memory.${table} WHERE account_id = $1`, [accountId]);
        }
        await transaction.unsafe(`DELETE FROM omi_memory.application_grant_heads WHERE account_id = $1`, [accountId]);
        await transaction.unsafe(`DELETE FROM omi_memory.application_grant_revisions WHERE account_id = $1`, [accountId]);
        await transaction.unsafe(`DELETE FROM omi_memory.application_credential_heads WHERE account_id = $1`, [accountId]);
        await transaction.unsafe(`DELETE FROM omi_memory.application_credential_revisions WHERE account_id = $1`, [accountId]);
        await transaction.unsafe(`DELETE FROM omi_memory.memory_graph_heads WHERE account_id = $1`, [accountId]);
        await transaction.unsafe(`DELETE FROM omi_memory.account_control_heads WHERE account_id = $1`, [accountId]);
        await transaction.unsafe(`DELETE FROM omi_memory.account_control_revisions WHERE account_id = $1`, [accountId]);
        await transaction.unsafe(`DELETE FROM omi_memory.platform_accounts WHERE account_id = $1`, [accountId]);
      });
    }
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

  test("model pipeline advisory locks exclude the same resource across independent pools", async () => {
    const contenderPool = createPostgresJsTransactionPool({
      connectionString: explicitTestUrl!, maxConnections: 1,
    });
    try {
      const holder = createPostgresProductionModelPipelineExclusivity(modelLockPool, QUALIFICATION_MANIFEST_RECEIPT);
      const contender = createPostgresProductionModelPipelineExclusivity(contenderPool, QUALIFICATION_MANIFEST_RECEIPT);
      const same = Object.freeze({
        version: MODEL_PIPELINE_RESOURCE_VERSION,
        resource_digest: "9".repeat(64),
      });
      const different = Object.freeze({
        version: MODEL_PIPELINE_RESOURCE_VERSION,
        resource_digest: "8".repeat(64),
      });
      let entered!: () => void;
      const enteredPromise = new Promise<void>((resolve) => { entered = resolve; });
      let release!: () => void;
      const releasePromise = new Promise<void>((resolve) => { release = resolve; });
      const held = holder.runExclusive(same, async () => {
        entered();
        await releasePromise;
        return "holder";
      });
      await enteredPromise;
      let sameCalls = 0;
      await expect(contender.runExclusive(same, async () => {
        sameCalls += 1;
        return "overlap";
      })).resolves.toEqual({ kind: "busy" });
      expect(sameCalls).toBe(0);
      await expect(contender.runExclusive(different, async () => "different"))
        .resolves.toEqual({ kind: "completed", value: "different" });
      release();
      await expect(held).resolves.toEqual({ kind: "completed", value: "holder" });
      await expect(contender.runExclusive(same, async () => "next"))
        .resolves.toEqual({ kind: "completed", value: "next" });
    } finally {
      await contenderPool.close();
    }
  });

  test("model pipeline loss aborts a pending provider before same-resource reacquisition", async () => {
    const contenderPool = createPostgresJsTransactionPool({
      connectionString: explicitTestUrl!, maxConnections: 1,
    });
    try {
      const holder = createPostgresProductionModelPipelineExclusivity(modelLockPool, QUALIFICATION_MANIFEST_RECEIPT);
      const contender = createPostgresProductionModelPipelineExclusivity(contenderPool, QUALIFICATION_MANIFEST_RECEIPT);
      const resource = Object.freeze({
        version: MODEL_PIPELINE_RESOURCE_VERSION,
        resource_digest: "7".repeat(64),
      });
      let providerStarted!: () => void;
      const providerStartedPromise = new Promise<void>((resolve) => { providerStarted = resolve; });
      let providerAborted!: () => void;
      const providerAbortedPromise = new Promise<void>((resolve) => { providerAborted = resolve; });
      const held = holder.runExclusive(resource, async (lossSignal) => {
        providerStarted();
        return await new Promise<string>((_resolve, reject) => {
          lossSignal.addEventListener("abort", () => {
            providerAborted();
            reject(lossSignal.reason);
          }, { once: true });
        });
      });
      await providerStartedPromise;
      const locks = await ownerSql.unsafe<{ pid: number }[]>(`
        SELECT pid
        FROM pg_catalog.pg_locks
        WHERE locktype = 'advisory'
          AND granted
          AND classid::bigint = $1
          AND objid::bigint = $2
      `, [0x77777777, 0x77777777]);
      expect(locks).toHaveLength(1);
      const holderPid = locks[0]?.pid;
      if (holderPid === undefined) throw new Error("missing model pipeline holder pid");
      await expect(contender.runExclusive(resource, async () => "overlap"))
        .resolves.toEqual({ kind: "busy" });
      const terminated = await ownerSql.unsafe<{ terminated: boolean }[]>(
        "SELECT pg_terminate_backend($1) AS terminated", [holderPid],
      );
      expect(terminated[0]?.terminated).toBe(true);
      await expect(Promise.race([
        providerAbortedPromise.then(() => "aborted"),
        Bun.sleep(5_000).then(() => "timeout"),
      ])).resolves.toBe("aborted");
      await expect(held).resolves.toEqual({ kind: "unavailable" });
      await expect(contender.runExclusive(resource, async () => "reacquired"))
        .resolves.toEqual({ kind: "completed", value: "reacquired" });
    } finally {
      await contenderPool.close();
    }
  }, 30_000);

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
    const context = issueQualificationContext({
      context_version: "authorized-ledger-write-context-v1", principal_id: principalId,
      account_id: accountId, application_id: applicationId, credential_id: credentialId,
      credential_generation: 4, capability: "memories.work.accept", grant_id: grantId,
      grant_version: 9, account_epoch: 12, destination_activation_revision: 17,
      lifecycle_state: "active", deletion_epoch: null, authentication_strength: "service-workload",
      issued_at_epoch_seconds: now - 60, expires_at_epoch_seconds: now + 3_600,
    }, authorityRow, now);
    const executionAuthorityRow: AuthorityStateRow = {
      ...authorityRow,
      capability: "memories.work.execute",
      grant_id: executeGrantId,
      grant_version: 1,
      grant_content_hash: "e".repeat(64),
    };
    const executionContext = issueQualificationContext({
      context_version: "authorized-ledger-write-context-v1", principal_id: principalId,
      account_id: accountId, application_id: applicationId, credential_id: credentialId,
      credential_generation: 4, capability: "memories.work.execute", grant_id: executeGrantId,
      grant_version: 1, account_epoch: 12, destination_activation_revision: 17,
      lifecycle_state: "active", deletion_epoch: null, authentication_strength: "service-workload",
      issued_at_epoch_seconds: now - 60, expires_at_epoch_seconds: now + 3_600,
    }, executionAuthorityRow, now);
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
      model_pipeline_exclusivity: createPostgresProductionModelPipelineExclusivity(modelLockPool, QUALIFICATION_MANIFEST_RECEIPT),
      resolve_model_pipeline_resource: async () => Object.freeze({
        version: MODEL_PIPELINE_RESOURCE_VERSION,
        resource_digest: "a".repeat(64),
      }),
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
      model_pipeline_exclusivity: createPostgresProductionModelPipelineExclusivity(modelLockPool, QUALIFICATION_MANIFEST_RECEIPT),
      resolve_model_pipeline_resource: async () => Object.freeze({
        version: MODEL_PIPELINE_RESOURCE_VERSION,
        resource_digest: "b".repeat(64),
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
      model_pipeline_exclusivity: createPostgresProductionModelPipelineExclusivity(modelLockPool, QUALIFICATION_MANIFEST_RECEIPT),
      resolve_model_pipeline_resource: async () => Object.freeze({
        version: MODEL_PIPELINE_RESOURCE_VERSION,
        resource_digest: "c".repeat(64),
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
    const exportGrantId = `grant:${suffix}:export`;
    const firebaseProjectId = `firebase-project-${suffix}`;
    const firebaseUid = `firebase-user-${suffix}`;
    const controlHash = "1".repeat(64);
    const credentialHash = "2".repeat(64);
    const grantHash = "3".repeat(64);
    const readGrantHash = "5".repeat(64);
    const exportGrantHash = "6".repeat(64);
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
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 4, 'memories.export', $4, 1, 'active', true,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
      [accountId, applicationId, credentialId, exportGrantId, exportGrantHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_heads
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version)
        VALUES ($1, $2, $3, 4, 'memories.export', $4, 1)`,
      [accountId, applicationId, credentialId, exportGrantId]);
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
    const context = issueQualificationContext({
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
    }, authorityRow, now);

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
    const contextB = issueQualificationContext({
      context_version: "authorized-ledger-write-context-v1",
      principal_id: principalB, account_id: accountB, application_id: applicationId,
      credential_id: credentialB, credential_generation: 4, capability: "memories.write",
      grant_id: grantB, grant_version: 9, account_epoch: 12,
      destination_activation_revision: 17, lifecycle_state: "active", deletion_epoch: null,
      authentication_strength: "firebase-id-token", issued_at_epoch_seconds: now - 60,
      expires_at_epoch_seconds: now + 3_600,
    }, authorityRowB, now);

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
    const unboundContext = createAuthorizedLedgerWriteContextIssuer().issue({
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
    await expect(repository.append(unboundContext, first)).resolves.toEqual({
      kind: "authorization_denied",
      reason: "authorization_state_denied",
    });
    expect(lastRepositoryStatement).toBe("authority.lock_and_revalidate");
    const beforeBoundAppend = await ownerSql.unsafe<{ count: number }[]>(`
      SELECT count(*)::int AS count
      FROM omi_memory.memory_idempotency_receipts
      WHERE account_id = $1
    `, [accountId]);
    expect([...beforeBoundAppend]).toEqual([{ count: 0 }]);
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
      database_generation_digest: QUALIFICATION_DATABASE_GENERATION_DIGEST,
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
    const wrongGenerationRuntime = createPostgresFirebaseAuthorizedLedgerRuntime({
      pool: appRolePool,
      project_id: firebaseProjectId,
      runtime_mode: "deployed",
      id_token_adapter: {
        verification_source: "firebase_production",
        verifyIdToken: async () => firebaseClaims,
      },
      application_id: applicationId,
      context_ttl_seconds: 60,
      database_generation_digest: "e".repeat(64),
    });
    await expect(wrongGenerationRuntime.append("header.payload.signature", now, firebaseAppend))
      .resolves.toEqual({ kind: "denied", outcome: "authorization" });

    await ownerSql.unsafe(`INSERT INTO omi_memory.postgres_restore_admission_revisions
        (database_generation_digest, release_revision, state, restore_id,
         restored_snapshot_digest, checkpoint_candidate_digest,
         checkpoint_evidence_digest, first_approval_subject_digest,
         first_approval_receipt_digest, second_approval_subject_digest,
         second_approval_receipt_digest, manual_release_receipt_digest,
         previous_release_revision, content_hash)
      VALUES ($1, 2, 'released', 'restore:qualification-generation-2', $2, $3, $4,
              $5, $6, $7, $8, $9, 1, $10)
      ON CONFLICT (database_generation_digest, release_revision) DO NOTHING`, [
      QUALIFICATION_DATABASE_GENERATION_DIGEST,
      "a".repeat(64), "b".repeat(64), "c".repeat(64), "1".repeat(64),
      "2".repeat(64), "3".repeat(64), "4".repeat(64), "5".repeat(64),
      "6".repeat(64),
    ]);
    let releaseRaceTransactions = 0;
    const releaseRacePool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(options, callback) => {
        releaseRaceTransactions += 1;
        if (releaseRaceTransactions === 3) {
          await ownerSql.unsafe(`UPDATE omi_memory.postgres_restore_admission_heads
            SET release_revision = 2, updated_at = transaction_timestamp()
            WHERE database_generation_digest = $1`, [QUALIFICATION_DATABASE_GENERATION_DIGEST]);
        }
        return appRolePool.withTransaction(options, callback);
      },
    });
    const releaseRaceRuntime = createPostgresFirebaseAuthorizedLedgerRuntime({
      pool: releaseRacePool,
      project_id: firebaseProjectId,
      runtime_mode: "deployed",
      id_token_adapter: {
        verification_source: "firebase_production",
        verifyIdToken: async () => firebaseClaims,
      },
      application_id: applicationId,
      context_ttl_seconds: 60,
      database_generation_digest: QUALIFICATION_DATABASE_GENERATION_DIGEST,
    });
    const releaseRaceAppend = append(
      `commit:${suffix}:release-race`,
      `append:${suffix}:release-race`,
      firebaseAppend.transition.derivation.commit.commit_id,
    );
    await expect(releaseRaceRuntime.append(
      "header.payload.signature", now, releaseRaceAppend,
    )).resolves.toEqual({
      kind: "completed",
      outcome: { kind: "authorization_denied", reason: "authorization_state_denied" },
    });
    expect(releaseRaceTransactions).toBe(3);
    await ownerSql.unsafe(`UPDATE omi_memory.postgres_restore_admission_heads
      SET release_revision = 1, updated_at = transaction_timestamp()
      WHERE database_generation_digest = $1`, [QUALIFICATION_DATABASE_GENERATION_DIGEST]);
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
      database_generation_digest: QUALIFICATION_DATABASE_GENERATION_DIGEST,
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
        database_generation_digest: QUALIFICATION_DATABASE_GENERATION_DIGEST,
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
    expect(productPage!.items.every((item) => item.citations.length > 0)).toBe(true);
    expect(isTrustedRecallCompletenessHonest(productPage!)).toBe(true);
    expect(productReadTraces).toBe(1);
    const chatMemoryContext = createPostgresFirebaseChatGenerationContextSource({
      memory: firebaseProductRead,
      now_epoch_seconds: () => now,
    });
    const chatContext = await chatMemoryContext.load({
      accountId,
      bearerToken: "header.payload.signature",
      admitted: { message: {}, generationId: "generation:qualification" } as never,
    });
    expect(chatContext.state).toBe("loaded");
    if (chatContext.state !== "loaded") throw new Error("expected Chat memory context");
    const chatContextPage = parseSynthesizedPageJson(chatContext.canonical_page_json);
    expect(chatContextPage).not.toBeNull();
    expect(chatContextPage!.items.length).toBeGreaterThan(0);
    expect(chatContextPage!.items.every((item) => item.citations.length > 0)).toBe(true);
    expect(isTrustedRecallCompletenessHonest(chatContextPage!)).toBe(true);
    expect(JSON.stringify(chatContext)).not.toContain("header.payload.signature");
    await expect(chatMemoryContext.load({
      accountId: `wrong-${accountId}`,
      bearerToken: "header.payload.signature",
      admitted: { message: {}, generationId: "generation:qualification" } as never,
    })).resolves.toEqual({
      version: "chat-generation-memory-context-v1",
      state: "unavailable",
    });
    expect(productReadTraces).toBe(2);
    const routeCounter = createServedCounter();
    const memoryServiceApp = createPostgresFirebaseAuthorizedMemoryServiceApp({
      mcp_handler: () => new Response("mcp-delegated", { status: 202 }),
      memory_read: {
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
          database_generation_digest: QUALIFICATION_DATABASE_GENERATION_DIGEST,
        },
        product: {
          account_timezone: "UTC",
          codec_root_secret: new Uint8Array(32).fill(0x55),
          produce_renders: produceQaRenders,
          verify_cursor: () => { throw new InvalidMcpCursorError(); },
          issue_cursor: () => { throw new Error("bounded qualification page must not issue a cursor"); },
          trace_sink: () => undefined,
          accepted_coverage_state: "bypassed",
          stm_coverage_state: "bypassed",
        },
      },
      now_epoch_seconds: () => now,
      counter: routeCounter,
    });
    const routeResponse = await memoryServiceApp.request("/v1/memories?limit=100", {
      headers: { authorization: "Bearer header.payload.signature" },
    });
    expect(routeResponse.status).toBe(200);
    const routePage = parseSynthesizedPageJson(await routeResponse.text());
    expect(routePage).not.toBeNull();
    expect(routePage!.items.length).toBeGreaterThan(0);
    expect(routePage!.items.every((item) => item.citations.length > 0)).toBe(true);
    expect(isTrustedRecallCompletenessHonest(routePage!)).toBe(true);
    expect(routeCounter.snapshot()).toMatchObject({
      domainReadsServed: 1,
      domainReadsDenied: 0,
      domainReadsFailed: 0,
    });
    const mcpResponse = await memoryServiceApp.request("/mcp", { method: "POST" });
    expect(mcpResponse.status).toBe(202);
    expect(await mcpResponse.text()).toBe("mcp-delegated");

    const digest = "7".repeat(64);
    const invalidCursor = issueMcpCursor({
      last_visible_key: asOpaqueVisibleKeyset(`vk1_${"8".repeat(64)}`),
      bindings: {
        owner_digest: digest,
        app_digest: digest,
        credential_key_digest: digest,
        authorization_generation_digest: digest,
        grant_generation_digest: digest,
        account_generation_digest: digest,
        graph_generation_digest: digest,
        projection_generation_digest: digest,
        projection_commit_digest: digest,
        visibility_digest: digest,
        filter_digest: digest,
        query_digest: digest,
        cursor_policy_digest: digest,
        source_digest: digest,
        read_mode_digest: digest,
      },
      issued_at_epoch_seconds: now,
      ttl_seconds: 60,
    }, {
      active_key_id: "qualification",
      keys: [{ key_id: "qualification", secret: new Uint8Array(32).fill(0x66) }],
    });
    const invalidCursorResponse = await memoryServiceApp.request(
      `/v1/memories?cursor=${encodeURIComponent(invalidCursor)}`,
      { headers: { authorization: "Bearer header.payload.signature" } },
    );
    expect(invalidCursorResponse.status).toBe(400);
    expect(await invalidCursorResponse.text()).toBe('{"error":"bad_request"}');
    expect(routeCounter.snapshot().domainReadsServed).toBe(1);
    const firebaseMemoryExport = createPostgresFirebaseAuthorizedMemoryExportRuntime({
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
        database_generation_digest: QUALIFICATION_DATABASE_GENERATION_DIGEST,
      },
      product: {
        account_timezone: "UTC",
        codec_root_secret: new Uint8Array(32).fill(0x56),
        produce_renders: produceQaRenders,
        chunk_max_bytes: 64 * 1024,
      },
    });
    const memoryExport = await firebaseMemoryExport.export(
      "header.payload.signature",
      now,
    );
    expect(memoryExport.kind).toBe("loaded");
    if (memoryExport.kind !== "loaded") throw new Error("expected owner memory export");
    const exportManifest = JSON.parse(memoryExport.manifest_json) as {
      contractVersion: string;
      counts: { memories: number; lineages: number; sources: number; chunks: number };
    };
    expect(exportManifest.contractVersion).toBe("owner-memory-export-v1");
    expect(exportManifest.counts.memories).toBeGreaterThan(0);
    expect(exportManifest.counts.lineages).toBeGreaterThan(0);
    expect(exportManifest.counts.sources).toBeGreaterThan(0);
    expect(exportManifest.counts.chunks).toBe(memoryExport.chunk_json.length);
    expect(memoryExport.chunk_json.join("\n")).not.toContain(`lineage:${suffix}:visible-product`);
    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 4, 'memories.export', $4, 2, 'revoked', false,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
      [accountId, applicationId, credentialId, exportGrantId, "7".repeat(64)]);
      await transaction.unsafe(`UPDATE omi_memory.application_grant_heads
          SET grant_version = 2
        WHERE account_id = $1 AND application_id = $2 AND credential_id = $3
          AND credential_generation = 4 AND capability = 'memories.export'`,
      [accountId, applicationId, credentialId]);
    });
    await expect(firebaseMemoryExport.export("header.payload.signature", now)).resolves.toEqual({
      kind: "denied", outcome: "authorization",
    });
    const readAfterExportRevocation = await firebaseProductRead.read(
      "header.payload.signature",
      now,
      { limit: 100, cursor: null },
    );
    expect(readAfterExportRevocation.kind).toBe("loaded");
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
      database_generation_digest: QUALIFICATION_DATABASE_GENERATION_DIGEST,
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
      database_generation_digest: QUALIFICATION_DATABASE_GENERATION_DIGEST,
    });
    await expect(revokedReadRuntime.load(
      "header.payload.signature",
      now,
    )).resolves.toEqual({ kind: "denied", outcome: "authorization" });
    expect(readTransactions).toBe(3);

    await expect(repository.append(context, first)).resolves.toEqual({
      kind: "authorization_denied", reason: "grant_inactive",
    });

    // A retained restore tombstone is checked twice: the Firebase lookup omits
    // the account, and a context minted before replay is denied again before
    // even an idempotent receipt can be returned.
    const restoredFenceTarget = createPostgresTombstoneRestoreTarget(pool);
    const restoredFenceRestore = Object.freeze({
      restore_id: `restore:application-gate:${suffix}`,
      restore_scope: "postgresql" as const,
      restored_snapshot_digest: sha256CanonicalContent({ suffix, restoredFence: true }),
      restore_completed_at_epoch_seconds: 1_800_000_000,
    });
    await expect(restoredFenceTarget.applyTerminalRecord({
      restore: restoredFenceRestore,
      terminal_record: {
        account_id: accountB, control_revision: 17, deletion_epoch: 90,
        terminal_record_digest: sha256CanonicalContent({ suffix, restoredFence: "account-b" }),
      },
    })).resolves.toMatchObject({ result: "applied", account_id: accountB });
    await expect(repository.append(contextB, sameKeyOtherAccount)).resolves.toEqual({
      kind: "authorization_denied", reason: "authorization_state_denied",
    });

    await expect(restoredFenceTarget.applyTerminalRecord({
      restore: restoredFenceRestore,
      terminal_record: {
        account_id: accountId, control_revision: 17, deletion_epoch: 91,
        terminal_record_digest: sha256CanonicalContent({ suffix, restoredFence: "account-a" }),
      },
    })).resolves.toMatchObject({ result: "applied", account_id: accountId });
    const postRestoreLookup = await ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      return transaction.unsafe<{ count: number }[]>(`SELECT count(*)::int AS count
        FROM omi_memory.lookup_released_unfenced_firebase_application_authorization(
          $1, $2, $3, $4, $5
        )`, [
        firebaseProjectId, firebaseUid, applicationId, "memories.write",
        QUALIFICATION_DATABASE_GENERATION_DIGEST,
      ]);
    });
    expect([...postRestoreLookup]).toEqual([{ count: 0 }]);
    const restoredRouteResponse = await memoryServiceApp.request("/v1/memories?limit=100", {
      headers: { authorization: "Bearer header.payload.signature" },
    });
    expect(restoredRouteResponse.status).toBe(403);
    expect(await restoredRouteResponse.text()).toBe('{"error":"forbidden"}');
    expect(routeCounter.snapshot()).toMatchObject({
      domainReadsServed: 1,
      domainReadsDenied: 2,
      domainReadsFailed: 0,
    });
    for (const bypass of [
      ["SELECT * FROM omi_memory.lookup_firebase_application_authorization($1, $2, $3, $4)",
        [firebaseProjectId, firebaseUid, applicationId, "memories.write"]],
      ["SELECT * FROM omi_memory.lock_authority_state($1, $2, $3, $4, $5, $6, $7)",
        [accountB, principalB, applicationId, credentialB, 4, "memories.write", grantB]],
    ] as const) {
      await expect(ownerSql.begin(async (transaction) => {
        await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
        await transaction.unsafe(bypass[0], [...bypass[1]]);
      })).rejects.toMatchObject({ code: "42501" });
    }
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
      database_generation_digest: QUALIFICATION_DATABASE_GENERATION_DIGEST,
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
    const authorized = (row: AuthorityStateRow) => issueQualificationContext({
      context_version: "authorized-ledger-write-context-v1", principal_id: principalId,
      account_id: accountId, application_id: applicationId, credential_id: credentialId,
      credential_generation: 4, capability: row.capability, grant_id: row.grant_id,
      grant_version: row.grant_version, account_epoch: 12,
      destination_activation_revision: 17, lifecycle_state: "active", deletion_epoch: null,
      authentication_strength: "service-workload", issued_at_epoch_seconds: now - 60,
      expires_at_epoch_seconds: now + 3_600,
    }, row, now);
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

    const migration = createPostgresLegacyPropositionMigrationRepository({ pool: appRolePool });
    const resumeRequest = (legacySourceId: string, proposedId: string | null) => {
      const body = {
        legacy_source_id: legacySourceId,
        proposed_random_opaque_proposition_id: proposedId,
      };
      return Object.freeze({
        ...body,
        request_digest: legacyPropositionMappingResumeRequestDigest(accountId, body),
      });
    };
    const tombstoneRequest = (
      legacySourceId: string,
      sequence: number,
      operationId: string,
      eventTime: number,
    ) => {
      const body = {
        legacy_source_id: legacySourceId,
        tombstone_sequence: sequence,
        tombstone_operation_id: operationId,
        tombstoned_at_event_time: eventTime,
      };
      return Object.freeze({
        ...body,
        request_digest: legacyMigrationTombstoneRequestDigest(accountId, body),
      });
    };
    const allocationSource = `legacy:qualification:allocation:${suffix}`;
    try {
      expect(await migration.resumeMapping(
        projectContext, resumeRequest(allocationSource, null),
      )).toEqual({ kind: "allocation_required" });
    } catch (error) {
      throw new Error(
        `legacy migration qualification failed at ${productStatement} code ${productProviderCode} constraint ${productConstraint}`,
        { cause: error },
      );
    }

    const mappedSource = `legacy:qualification:mapped:${suffix}`;
    const durableWinner = `proposition:${suffix}:opaque-winner`;
    const inserted = await migration.resumeMapping(
      projectContext, resumeRequest(mappedSource, durableWinner),
    );
    expect(inserted).toMatchObject({
      kind: "inserted",
      mapping: {
        owner_account_id: accountId,
        legacy_source_id: mappedSource,
        proposition_id: durableWinner,
      },
    });
    await expect(migration.resumeMapping(
      projectContext, resumeRequest(mappedSource, `proposition:${suffix}:losing-proposal`),
    )).resolves.toMatchObject({
      kind: "reused",
      mapping: { proposition_id: durableWinner },
    });

    const mappedTombstone = tombstoneRequest(
      mappedSource, 7, `migration-tombstone:${suffix}:mapped`, 70,
    );
    await expect(migration.recordTombstone(projectContext, mappedTombstone))
      .resolves.toEqual({ kind: "recorded" });
    await expect(migration.recordTombstone(projectContext, mappedTombstone))
      .resolves.toEqual({ kind: "replayed" });
    const changedMappedTombstone = tombstoneRequest(
      mappedSource, 8, `migration-tombstone:${suffix}:mapped`, 71,
    );
    await expect(migration.recordTombstone(projectContext, changedMappedTombstone))
      .resolves.toEqual({ kind: "idempotency_conflict" });
    await expect(migration.resumeMapping(
      projectContext, resumeRequest(mappedSource, durableWinner),
    )).resolves.toEqual({ kind: "tombstoned" });

    const deletedBeforeResume = `legacy:qualification:deleted-first:${suffix}`;
    const deletedFirstTombstone = tombstoneRequest(
      deletedBeforeResume, 2, `migration-tombstone:${suffix}:deleted-first`, 80,
    );
    await expect(migration.recordTombstone(projectContext, deletedFirstTombstone))
      .resolves.toEqual({ kind: "recorded" });
    await expect(migration.resumeMapping(projectContext, resumeRequest(
      deletedBeforeResume, `proposition:${suffix}:must-never-exist`,
    ))).resolves.toEqual({ kind: "tombstoned" });

    const racingSource = `legacy:qualification:race:${suffix}`;
    const racingTombstone = tombstoneRequest(
      racingSource, 3, `migration-tombstone:${suffix}:race`, 90,
    );
    const racingResults = await Promise.all([
      migration.resumeMapping(
        projectContext, resumeRequest(racingSource, `proposition:${suffix}:race`),
      ),
      migration.recordTombstone(projectContext, racingTombstone),
    ]);
    expect(["inserted", "tombstoned", "serialization_retryable"])
      .toContain(racingResults[0].kind);
    expect(["recorded", "serialization_retryable"])
      .toContain(racingResults[1].kind);
    if (racingResults[1].kind === "serialization_retryable") {
      await expect(migration.recordTombstone(projectContext, racingTombstone))
        .resolves.toEqual({ kind: "recorded" });
    }
    await expect(migration.resumeMapping(
      projectContext, resumeRequest(racingSource, `proposition:${suffix}:race-late`),
    )).resolves.toEqual({ kind: "tombstoned" });

    const legacyRows = await ownerSql.unsafe<{
      mappings: number; tombstones: number; deleted_first_mapping: number; race_tombstones: number;
    }[]>(`SELECT
      (SELECT count(*)::int FROM omi_memory.memory_legacy_proposition_mappings
        WHERE account_id = $1) AS mappings,
      (SELECT count(*)::int FROM omi_memory.memory_migration_item_tombstones
        WHERE account_id = $1) AS tombstones,
      (SELECT count(*)::int FROM omi_memory.memory_legacy_proposition_mappings
        WHERE account_id = $1 AND legacy_source_id = $2) AS deleted_first_mapping,
      (SELECT count(*)::int FROM omi_memory.memory_migration_item_tombstones
        WHERE account_id = $1 AND legacy_source_id = $3) AS race_tombstones`,
    [accountId, deletedBeforeResume, racingSource]);
    expect([...legacyRows]).toEqual([{
      mappings: racingResults[0].kind === "inserted" ? 2 : 1,
      tombstones: 3, deleted_first_mapping: 0, race_tombstones: 1,
    }]);

    const rollbackSource = `legacy:qualification:rollback:${suffix}`;
    try {
      await ownerSql.unsafe(`
        CREATE OR REPLACE FUNCTION omi_memory.qualification_reject_legacy_mapping()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'qualification injected legacy mapping rollback'; END
        $$;
        DROP TRIGGER IF EXISTS reject_legacy_mapping
          ON omi_memory.memory_legacy_proposition_mappings;
        CREATE TRIGGER reject_legacy_mapping
        AFTER INSERT ON omi_memory.memory_legacy_proposition_mappings
        FOR EACH ROW EXECUTE FUNCTION omi_memory.qualification_reject_legacy_mapping()
      `, [], { prepare: false });
      await expect(migration.resumeMapping(projectContext, resumeRequest(
        rollbackSource, `proposition:${suffix}:rollback-legacy`,
      ))).rejects.toMatchObject({ code: "persistence_failed", message: "persistence_failed" });
      const rolledBackLegacy = await ownerSql.unsafe<{ mappings: number }[]>(`
        SELECT count(*)::int AS mappings
        FROM omi_memory.memory_legacy_proposition_mappings
        WHERE account_id = $1 AND legacy_source_id = $2
      `, [accountId, rollbackSource]);
      expect([...rolledBackLegacy]).toEqual([{ mappings: 0 }]);
    } finally {
      await ownerSql.unsafe(`
        DROP TRIGGER IF EXISTS reject_legacy_mapping
          ON omi_memory.memory_legacy_proposition_mappings;
        DROP FUNCTION IF EXISTS omi_memory.qualification_reject_legacy_mapping()
      `, [], { prepare: false }).catch(() => undefined);
    }

    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe("SELECT set_config('omi.account_id', $1, true)", [accountId]);
      await transaction.unsafe("SELECT set_config('omi.principal_id', $1, true)", [principalId]);
      await transaction.unsafe("SELECT set_config('omi.capability', 'memories.project', true)");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.resume_legacy_proposition_mapping($1, $2, NULL, NULL)",
        [`account:foreign:${suffix}`, `legacy:foreign:${suffix}`],
      );
    })).rejects.toMatchObject({ code: "P1005" });

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
    await expect(migration.resumeMapping(
      projectContext, resumeRequest(mappedSource, durableWinner),
    )).resolves.toEqual({ kind: "authorization_denied", reason: "grant_inactive" });

    for (const forbiddenSql of [
      "UPDATE omi_memory.memory_product_propositions SET origin = 'native' WHERE account_id = $1",
      "DELETE FROM omi_memory.memory_product_projection_payloads WHERE account_id = $1",
      "SELECT * FROM omi_memory.memory_legacy_proposition_mappings WHERE account_id = $1",
      "SELECT * FROM omi_memory.memory_migration_item_tombstones WHERE account_id = $1",
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
    const context = issueQualificationContext({
      context_version: "authorized-ledger-write-context-v1", principal_id: principalId,
      account_id: accountId, application_id: applicationId, credential_id: credentialId,
      credential_generation: 4, capability: "memories.experiments.shadow",
      grant_id: grantId, grant_version: 1, account_epoch: 12,
      destination_activation_revision: 17, lifecycle_state: "active", deletion_epoch: null,
      authentication_strength: "service-workload", issued_at_epoch_seconds: now - 60,
      expires_at_epoch_seconds: now + 3_600,
    }, shadowAuthority, now);
    const writeContext = issueQualificationContext({
      context_version: "authorized-ledger-write-context-v1", principal_id: principalId,
      account_id: accountId, application_id: applicationId, credential_id: credentialId,
      credential_generation: 4, capability: "memories.write",
      grant_id: writeGrantId, grant_version: 1, account_epoch: 12,
      destination_activation_revision: 17, lifecycle_state: "active", deletion_epoch: null,
      authentication_strength: "service-workload", issued_at_epoch_seconds: now - 60,
      expires_at_epoch_seconds: now + 3_600,
    }, writeAuthority, now);

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
    const queryLossSignals: AbortSignal[] = [];
    const queryCandidateRefs: string[] = [];
    const queryRuntime = createPostgresMemoryQueryEvaluationOneShotRuntime({
      pool: appRolePool, codec_root_secret: new Uint8Array(32).fill(8),
      model_pipeline_exclusivity: createPostgresProductionModelPipelineExclusivity(modelLockPool, QUALIFICATION_MANIFEST_RECEIPT),
      resolve_model_pipeline_resource: async () => Object.freeze({
        version: MODEL_PIPELINE_RESOURCE_VERSION,
        resource_digest: "e".repeat(64),
      }),
      produce: async (request, lossSignal) => {
        queryModelCalls += 1;
        if (!(lossSignal instanceof AbortSignal)) throw new Error("missing query loss signal");
        queryLossSignals.push(lossSignal);
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
    expect(queryLossSignals).toHaveLength(2);
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
      model_pipeline_exclusivity: createPostgresProductionModelPipelineExclusivity(modelLockPool, QUALIFICATION_MANIFEST_RECEIPT),
      resolve_model_pipeline_resource: async () => Object.freeze({
        version: MODEL_PIPELINE_RESOURCE_VERSION,
        resource_digest: "e".repeat(64),
      }),
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

  test("cleanup role scans, atomically disposes, receipts, rolls back, and retains tombstones", async () => {
    const suffix = randomUUID();
    const accountId = `account:cleanup:${suffix}`;
    const inputId = `fwi1_${sha256CanonicalContent({ suffix, input: true })}`;
    const jobId = `cleanup-job:${suffix}`;
    const operationRef = `opref1_${sha256CanonicalContent({ suffix, operation: true })}`;
    const eligibility = sha256CanonicalContent({ suffix, eligibility: true });
    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe("INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)", [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
        (account_id, control_revision, account_generation, account_epoch, lifecycle_state,
         deletion_epoch, observed_at, record_schema_version, record_json, content_hash)
        VALUES ($1, 7, 'new', 3, 'deleted', 11, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountId, "a".repeat(64)]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
        (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 7, NULL, NULL)`, [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_terminal_deletion_exports
        (account_id, deletion_epoch, export_contract_version, transitioned_at,
         account_generation, terminal_lifecycle_state, stranded_data_present,
         control_revision, content_hash)
        VALUES ($1, 11, 'terminal-v1', transaction_timestamp(), 'new', 'deleted', false, 7, $2)`,
      [accountId, "b".repeat(64)]);
      await transaction.unsafe(`INSERT INTO omi_memory.memory_formation_work_inputs
        (account_id, staged_input_id, job_id, input_version, account_epoch,
         accepted_work_digest, input_frontier, input_digest, execution_contract_digest,
         snapshot_digest, snapshot_version, snapshot_json, stage_request_digest, content_hash)
        VALUES ($1, $2, $3, 'formation-work-staged-input-v1', 3, $4, '0', $5, $6,
                $7, 'formation-input-snapshot-v1', '{}'::jsonb, $8, $9)`, [
        accountId, inputId, jobId, "c".repeat(64), "d".repeat(64), "e".repeat(64),
        "f".repeat(64), "1".repeat(64), "2".repeat(64),
      ]);
    });

    const cleanup = createPostgresDeletionCleanupParticipant(pool);
    await expect(cleanup.withHeldDatabaseFence(
      { account_id: accountId, control_revision: 7, deletion_epoch: 11 },
      operationRef,
      eligibility,
      async (session) => {
        const before = await session.scanOwned();
        expect(before.find((row) => row.surface === "staged_results")?.remaining_count).toBe(1);
        const disposed = await session.dispose(["durable_work", "staged_results"]);
        expect(disposed.map((row) => [row.surface, row.result])).toEqual([
          ["durable_work", "already_absent"], ["staged_results", "disposed"],
        ]);
        const replay = await session.dispose(["durable_work", "staged_results"]);
        expect(replay).toEqual(disposed);
        const after = await session.scanOwned();
        expect(after.find((row) => row.surface === "staged_results")?.remaining_count).toBe(0);
        throw new Error("qualification rollback after cleanup");
      },
    )).rejects.toMatchObject({ code: "persistence_failed" });

    let counts = await ownerSql.unsafe<{ inputs: number; receipts: number }[]>(`SELECT
      (SELECT count(*)::int FROM omi_memory.memory_formation_work_inputs WHERE account_id = $1) inputs,
      (SELECT count(*)::int FROM omi_memory.account_deletion_surface_receipts WHERE account_id = $1) receipts`,
    [accountId]);
    expect([...counts]).toEqual([{ inputs: 1, receipts: 0 }]);

    await cleanup.withHeldDatabaseFence(
      { account_id: accountId, control_revision: 7, deletion_epoch: 11 },
      operationRef,
      eligibility,
      async (session) => {
        await session.dispose(["durable_work", "staged_results"]);
      },
    );
    counts = await ownerSql.unsafe<{ inputs: number; receipts: number }[]>(`SELECT
      (SELECT count(*)::int FROM omi_memory.memory_formation_work_inputs WHERE account_id = $1) inputs,
      (SELECT count(*)::int FROM omi_memory.account_deletion_surface_receipts WHERE account_id = $1) receipts`,
    [accountId]);
    expect([...counts]).toEqual([{ inputs: 0, receipts: 2 }]);
    const safety = await ownerSql.unsafe<{ controls: number; exports: number }[]>(`SELECT
      (SELECT count(*)::int FROM omi_memory.account_control_revisions WHERE account_id = $1) controls,
      (SELECT count(*)::int FROM omi_memory.account_terminal_deletion_exports WHERE account_id = $1) exports`,
    [accountId]);
    expect([...safety]).toEqual([{ controls: 1, exports: 1 }]);

    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe("SELECT * FROM omi_memory.scan_deleted_account_surface('staged_results')");
    })).rejects.toMatchObject({ code: "42501" });
    await expect(cleanup.withHeldDatabaseFence(
      { account_id: accountId, control_revision: 6, deletion_epoch: 11 },
      `opref1_${"9".repeat(64)}`,
      eligibility,
      async () => undefined,
    )).rejects.toMatchObject({ code: "terminal_coordinate_denied" });
  }, 120_000);

  test("Typesense cleanup receipts are retained, exact, replayable, and cleanup-role only", async () => {
    const suffix = randomUUID();
    const accountId = `account:typesense-receipt:${suffix}`;
    const operationRef = `opref1_${sha256CanonicalContent({ suffix, operation: true })}`;
    const eligibilityDigest = sha256CanonicalContent({ suffix, eligibility: true });
    const registryDigest = sha256CanonicalContent({ suffix, registry: true });
    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(
        "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)", [accountId],
      );
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
        (account_id, control_revision, account_generation, account_epoch, lifecycle_state,
         deletion_epoch, observed_at, record_schema_version, record_json, content_hash)
        VALUES ($1, 7, 'new', 3, 'deleted', 11, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountId, "a".repeat(64)]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
        (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 7, NULL, NULL)`, [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_terminal_deletion_exports
        (account_id, deletion_epoch, export_contract_version, transitioned_at,
         account_generation, terminal_lifecycle_state, stranded_data_present,
         control_revision, content_hash)
        VALUES ($1, 11, 'terminal-v1', transaction_timestamp(), 'new', 'deleted', false, 7, $2)`,
      [accountId, "b".repeat(64)]);
    });

    const receiptCore = Object.freeze({
      version: "typesense-deletion-receipt-key-v1" as const,
      account_id: accountId,
      control_revision: 7,
      deletion_epoch: 11,
      operation_ref: operationRef,
      eligibility_digest: eligibilityDigest,
      registry_digest: registryDigest,
      role: "legacy_conversations" as const,
      collection_name: "conversations",
      result: "disposed" as const,
      affected_count: 2,
      provider_receipt_digest: "c".repeat(64),
    });
    const storedReceipt = Object.freeze({
      ...receiptCore,
      receipt_digest: createHash("sha256").update(JSON.stringify({
        contract_version: "typesense-deletion-stored-receipt-v1",
        receipt: receiptCore,
      })).digest("hex"),
    });
    const repository = createPostgresTypesenseDeletionReceiptRepository(pool);
    const key = Object.freeze({
      version: storedReceipt.version,
      account_id: storedReceipt.account_id,
      control_revision: storedReceipt.control_revision,
      deletion_epoch: storedReceipt.deletion_epoch,
      operation_ref: storedReceipt.operation_ref,
      eligibility_digest: storedReceipt.eligibility_digest,
      registry_digest: storedReceipt.registry_digest,
      role: storedReceipt.role,
      collection_name: storedReceipt.collection_name,
    });
    await expect(repository.load(key)).resolves.toEqual({ kind: "missing" });
    await expect(repository.record(storedReceipt)).resolves.toEqual(storedReceipt);
    await expect(repository.record(storedReceipt)).resolves.toEqual(storedReceipt);
    await expect(repository.load(key)).resolves.toEqual({ kind: "found", receipt: storedReceipt });

    const changedCore = Object.freeze({
      ...receiptCore,
      provider_receipt_digest: "d".repeat(64),
    });
    const changed = Object.freeze({
      ...changedCore,
      receipt_digest: createHash("sha256").update(JSON.stringify({
        contract_version: "typesense-deletion-stored-receipt-v1",
        receipt: changedCore,
      })).digest("hex"),
    });
    await expect(repository.record(changed)).rejects.toMatchObject({ code: "receipt_conflict" });

    const counts = await ownerSql.unsafe<{ count: number }[]>(`
      SELECT count(*)::int AS count
      FROM omi_memory.account_typesense_deletion_receipts
      WHERE account_id = $1`, [accountId]);
    expect([...counts]).toEqual([{ count: 1 }]);
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.account_typesense_deletion_receipts WHERE account_id = $1",
        [accountId],
      );
    })).rejects.toMatchObject({ code: "42501" });
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.load_typesense_deletion_receipt($1,$2,$3,$4,$5,$6,$7,$8)",
        [
          accountId, 7, 11, operationRef, eligibilityDigest, registryDigest,
          "legacy_conversations", "conversations",
        ],
      );
    })).rejects.toMatchObject({ code: "42501" });
  }, 120_000);

  test("Pinecone cleanup receipts bind all vector coordinates and remain cleanup-role only", async () => {
    const suffix = randomUUID();
    const accountId = `account:pinecone-receipt:${suffix}`;
    const operationRef = `opref1_${sha256CanonicalContent({ suffix, operation: "pinecone" })}`;
    const eligibilityDigest = sha256CanonicalContent({ suffix, eligibility: "pinecone" });
    const registryDigest = sha256CanonicalContent({ suffix, registry: "pinecone" });
    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(
        "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)", [accountId],
      );
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
        (account_id, control_revision, account_generation, account_epoch, lifecycle_state,
         deletion_epoch, observed_at, record_schema_version, record_json, content_hash)
        VALUES ($1, 8, 'new', 4, 'deleted', 12, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountId, "1".repeat(64)]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
        (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 8, NULL, NULL)`, [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_terminal_deletion_exports
        (account_id, deletion_epoch, export_contract_version, transitioned_at,
         account_generation, terminal_lifecycle_state, stranded_data_present,
         control_revision, content_hash)
        VALUES ($1, 12, 'terminal-v1', transaction_timestamp(), 'new', 'deleted', false, 8, $2)`,
      [accountId, "2".repeat(64)]);
    });

    const receiptCore = Object.freeze({
      version: "pinecone-deletion-receipt-key-v1" as const,
      account_id: accountId,
      control_revision: 8,
      deletion_epoch: 12,
      operation_ref: operationRef,
      eligibility_digest: eligibilityDigest,
      registry_digest: registryDigest,
      role: "memory_vectors" as const,
      index_name: "memories-backend" as const,
      namespace_name: "ns2" as const,
      result: "disposed" as const,
      pre_delete_count: 3,
      pre_delete_content_hash: "3".repeat(64),
      provider_receipt_digest: "4".repeat(64),
    });
    const storedReceipt = Object.freeze({
      ...receiptCore,
      receipt_digest: createHash("sha256").update(JSON.stringify({
        contract_version: "pinecone-deletion-stored-receipt-v1",
        receipt: receiptCore,
      })).digest("hex"),
    });
    const repository = createPostgresPineconeDeletionReceiptRepository(pool);
    const key = Object.freeze({
      version: storedReceipt.version,
      account_id: storedReceipt.account_id,
      control_revision: storedReceipt.control_revision,
      deletion_epoch: storedReceipt.deletion_epoch,
      operation_ref: storedReceipt.operation_ref,
      eligibility_digest: storedReceipt.eligibility_digest,
      registry_digest: storedReceipt.registry_digest,
      role: storedReceipt.role,
      index_name: storedReceipt.index_name,
      namespace_name: storedReceipt.namespace_name,
    });
    await expect(repository.load(key)).resolves.toEqual({ kind: "missing" });
    await expect(repository.record(storedReceipt)).resolves.toEqual(storedReceipt);
    await expect(repository.record(storedReceipt)).resolves.toEqual(storedReceipt);
    await expect(repository.load(key)).resolves.toEqual({ kind: "found", receipt: storedReceipt });

    const changedCore = Object.freeze({ ...receiptCore, provider_receipt_digest: "5".repeat(64) });
    const changed = Object.freeze({
      ...changedCore,
      receipt_digest: createHash("sha256").update(JSON.stringify({
        contract_version: "pinecone-deletion-stored-receipt-v1", receipt: changedCore,
      })).digest("hex"),
    });
    await expect(repository.record(changed)).rejects.toMatchObject({ code: "receipt_conflict" });

    const counts = await ownerSql.unsafe<{ count: number }[]>(`
      SELECT count(*)::int AS count FROM omi_memory.account_pinecone_deletion_receipts
      WHERE account_id = $1`, [accountId]);
    expect([...counts]).toEqual([{ count: 1 }]);
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.account_pinecone_deletion_receipts WHERE account_id = $1",
        [accountId],
      );
    })).rejects.toMatchObject({ code: "42501" });
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.load_pinecone_deletion_receipt($1,$2,$3,$4,$5,$6,$7,$8,$9)",
        [
          accountId, 8, 12, operationRef, eligibilityDigest, registryDigest,
          "memory_vectors", "memories-backend", "ns2",
        ],
      );
    })).rejects.toMatchObject({ code: "42501" });
  }, 120_000);

  test("GCS cleanup receipts bind policy and prefix coordinates and remain cleanup-role only", async () => {
    const suffix = randomUUID();
    const accountId = `account:gcs-receipt:${suffix}`;
    const operationRef = `opref1_${sha256CanonicalContent({ suffix, operation: "gcs" })}`;
    const eligibilityDigest = sha256CanonicalContent({ suffix, eligibility: "gcs" });
    const registryDigest = sha256CanonicalContent({ suffix, registry: "gcs" });
    const policyDigest = sha256CanonicalContent({ suffix, policy: "gcs" });
    const prefixDigest = sha256CanonicalContent({ suffix, prefix: "gcs" });
    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(
        "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)", [accountId],
      );
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
        (account_id, control_revision, account_generation, account_epoch, lifecycle_state,
         deletion_epoch, observed_at, record_schema_version, record_json, content_hash)
        VALUES ($1, 9, 'new', 5, 'deleted', 13, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountId, "1".repeat(64)]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
        (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 9, NULL, NULL)`, [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_terminal_deletion_exports
        (account_id, deletion_epoch, export_contract_version, transitioned_at,
         account_generation, terminal_lifecycle_state, stranded_data_present,
         control_revision, content_hash)
        VALUES ($1, 13, 'terminal-v1', transaction_timestamp(), 'new', 'deleted', false, 9, $2)`,
      [accountId, "2".repeat(64)]);
    });

    const receiptCore = Object.freeze({
      version: "gcs-deletion-receipt-key-v1" as const,
      account_id: accountId,
      control_revision: 9,
      deletion_epoch: 13,
      operation_ref: operationRef,
      eligibility_digest: eligibilityDigest,
      registry_digest: registryDigest,
      policy_digest: policyDigest,
      owner_mapping_digest: sha256CanonicalContent({ suffix, owner_mapping: "gcs" }),
      role: "private_sync_chunks" as const,
      bucket_name: "omi-private-cloud-sync",
      prefix_digest: prefixDigest,
      result: "disposed" as const,
      pre_delete_count: 3,
      pre_delete_set_digest: "3".repeat(64),
      provider_receipt_digest: "4".repeat(64),
    });
    const storedReceipt = Object.freeze({
      ...receiptCore,
      receipt_digest: createHash("sha256").update(JSON.stringify({
        contract_version: "gcs-deletion-stored-receipt-v1",
        receipt: receiptCore,
      })).digest("hex"),
    });
    const repository = createPostgresGcsDeletionReceiptRepository(pool);
    const key = Object.freeze({
      version: storedReceipt.version,
      account_id: storedReceipt.account_id,
      control_revision: storedReceipt.control_revision,
      deletion_epoch: storedReceipt.deletion_epoch,
      operation_ref: storedReceipt.operation_ref,
      eligibility_digest: storedReceipt.eligibility_digest,
      registry_digest: storedReceipt.registry_digest,
      policy_digest: storedReceipt.policy_digest,
      owner_mapping_digest: storedReceipt.owner_mapping_digest,
      role: storedReceipt.role,
      bucket_name: storedReceipt.bucket_name,
      prefix_digest: storedReceipt.prefix_digest,
    });
    await expect(repository.load(key)).resolves.toEqual({ kind: "missing" });
    await expect(repository.record(storedReceipt)).resolves.toEqual(storedReceipt);
    await expect(repository.record(storedReceipt)).resolves.toEqual(storedReceipt);
    await expect(repository.load(key)).resolves.toEqual({ kind: "found", receipt: storedReceipt });

    const changedCore = Object.freeze({ ...receiptCore, provider_receipt_digest: "5".repeat(64) });
    const changed = Object.freeze({
      ...changedCore,
      receipt_digest: createHash("sha256").update(JSON.stringify({
        contract_version: "gcs-deletion-stored-receipt-v1", receipt: changedCore,
      })).digest("hex"),
    });
    await expect(repository.record(changed)).rejects.toMatchObject({ code: "receipt_conflict" });

    const counts = await ownerSql.unsafe<{ count: number }[]>(`
      SELECT count(*)::int AS count FROM omi_memory.account_gcs_deletion_receipts
      WHERE account_id = $1`, [accountId]);
    expect([...counts]).toEqual([{ count: 1 }]);
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.account_gcs_deletion_receipts WHERE account_id = $1",
        [accountId],
      );
    })).rejects.toMatchObject({ code: "42501" });
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.load_gcs_deletion_receipt($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
        [
          accountId, 9, 13, operationRef, eligibilityDigest, registryDigest,
          policyDigest, storedReceipt.owner_mapping_digest, "private_sync_chunks",
          "omi-private-cloud-sync", prefixDigest,
        ],
      );
    })).rejects.toMatchObject({ code: "42501" });
  }, 120_000);

  test("Firestore legacy-generation receipts bind source registry and remain cleanup-role only", async () => {
    const suffix = randomUUID();
    const accountId = `account:firestore-legacy-generation-receipt:${suffix}`;
    const operationRef = `opref1_${sha256CanonicalContent({ suffix, operation: "firestore" })}`;
    const eligibilityDigest = sha256CanonicalContent({ suffix, eligibility: "firestore" });
    const registryDigest = sha256CanonicalContent({ suffix, registry: "firestore" });
    const policyDigest = sha256CanonicalContent({ suffix, policy: "firestore" });
    const ownerMappingDigest = sha256CanonicalContent({ suffix, owner_mapping: "firestore" });
    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(
        "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)", [accountId],
      );
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
        (account_id, control_revision, account_generation, account_epoch, lifecycle_state,
         deletion_epoch, observed_at, record_schema_version, record_json, content_hash)
        VALUES ($1, 10, 'new', 6, 'deleted', 14, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountId, "1".repeat(64)]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
        (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 10, NULL, NULL)`, [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_terminal_deletion_exports
        (account_id, deletion_epoch, export_contract_version, transitioned_at,
         account_generation, terminal_lifecycle_state, stranded_data_present,
         control_revision, content_hash)
        VALUES ($1, 14, 'terminal-v1', transaction_timestamp(), 'new', 'deleted', false, 10, $2)`,
      [accountId, "2".repeat(64)]);
    });

    const receiptCore = Object.freeze({
      version: "firestore-legacy-generation-receipt-key-v1" as const,
      account_id: accountId,
      control_revision: 10,
      deletion_epoch: 14,
      operation_ref: operationRef,
      eligibility_digest: eligibilityDigest,
      registry_digest: registryDigest,
      policy_digest: policyDigest,
      owner_mapping_digest: ownerMappingDigest,
      project_id: "based-hardware",
      database_id: "(default)",
      role: "legacy_user_tree" as const,
      collection_id: "users",
      result: "disposed" as const,
      pre_delete_count: 3,
      pre_delete_set_digest: "3".repeat(64),
      provider_receipt_digest: "4".repeat(64),
    });
    const storedReceipt = Object.freeze({
      ...receiptCore,
      receipt_digest: createHash("sha256").update(JSON.stringify({
        contract_version: "firestore-legacy-generation-stored-receipt-v1",
        receipt: receiptCore,
      })).digest("hex"),
    });
    const repository = createPostgresFirestoreLegacyGenerationReceiptRepository(pool);
    const key = Object.freeze({
      version: storedReceipt.version,
      account_id: storedReceipt.account_id,
      control_revision: storedReceipt.control_revision,
      deletion_epoch: storedReceipt.deletion_epoch,
      operation_ref: storedReceipt.operation_ref,
      eligibility_digest: storedReceipt.eligibility_digest,
      registry_digest: storedReceipt.registry_digest,
      policy_digest: storedReceipt.policy_digest,
      owner_mapping_digest: storedReceipt.owner_mapping_digest,
      project_id: storedReceipt.project_id,
      database_id: storedReceipt.database_id,
      role: storedReceipt.role,
      collection_id: storedReceipt.collection_id,
    });
    await expect(repository.load(key)).resolves.toEqual({ kind: "missing" });
    await expect(repository.record(storedReceipt)).resolves.toEqual(storedReceipt);
    await expect(repository.record(storedReceipt)).resolves.toEqual(storedReceipt);
    await expect(repository.load(key)).resolves.toEqual({ kind: "found", receipt: storedReceipt });

    const changedCore = Object.freeze({ ...receiptCore, provider_receipt_digest: "5".repeat(64) });
    const changed = Object.freeze({
      ...changedCore,
      receipt_digest: createHash("sha256").update(JSON.stringify({
        contract_version: "firestore-legacy-generation-stored-receipt-v1",
        receipt: changedCore,
      })).digest("hex"),
    });
    await expect(repository.record(changed)).rejects.toMatchObject({ code: "receipt_conflict" });

    const counts = await ownerSql.unsafe<{ count: number }[]>(`
      SELECT count(*)::int AS count
      FROM omi_memory.account_firestore_legacy_generation_deletion_receipts
      WHERE account_id = $1`, [accountId]);
    expect([...counts]).toEqual([{ count: 1 }]);
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.account_firestore_legacy_generation_deletion_receipts WHERE account_id = $1",
        [accountId],
      );
    })).rejects.toMatchObject({ code: "42501" });
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.load_firestore_legacy_generation_deletion_receipt($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)",
        [
          accountId, 10, 14, operationRef, eligibilityDigest, registryDigest,
          policyDigest, ownerMappingDigest, "based-hardware", "(default)",
          "legacy_user_tree", "users",
        ],
      );
    })).rejects.toMatchObject({ code: "42501" });
  }, 120_000);

  test("stranded rollback manifests bind every destination surface to one exact 30-day window", async () => {
    const suffix = randomUUID();
    const accountId = `account:stranded-recovery:${suffix}`;
    const rolledBackAt = 1_800_000_000;
    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(
        "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)", [accountId],
      );
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
        (account_id, control_revision, account_generation, account_epoch, lifecycle_state,
         deletion_epoch, observed_at, record_schema_version, record_json, content_hash)
        VALUES ($1, 11, 'rolled_back_stranded', 7, 'active', NULL, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountId, "1".repeat(64)]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
        (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 11, NULL, NULL)`, [accountId]);
    });

    const manifestFor = (rollbackFrontier: string) => verifyStrandedRollbackRecovery({
      control_projection: {
        account_id: accountId,
        control_revision: 11,
        account_generation: "rolled_back_stranded",
        account_epoch: 7,
        lifecycle_state: "active",
        deletion_epoch: null,
        activation: null,
        conflict: null,
      },
      rollback_coordinate: {
        version: "stranded-rollback-coordinate-v1",
        account_id: accountId,
        control_revision: 11,
        account_epoch: 7,
        database_generation_digest: sha256CanonicalContent({ suffix, generation: true }),
        cutover_frontier_digest: sha256CanonicalContent({ suffix, cutover: true }),
        rollback_frontier_digest: rollbackFrontier,
        cutover_at_epoch_seconds: rolledBackAt - 3_600,
        rolled_back_at_epoch_seconds: rolledBackAt,
        recovery_deadline_epoch_seconds:
          rolledBackAt + STRANDED_ROLLBACK_RECOVERY_WINDOW_SECONDS,
      },
      source_receipts: STRANDED_ROLLBACK_RECOVERY_SURFACES.map((surface, index) => ({
        version: STRANDED_ROLLBACK_SOURCE_RECEIPT_VERSION,
        manifest_contract_version: STRANDED_ROLLBACK_RECOVERY_CONTRACT_VERSION,
        scanner_contract_version: `scanner-${surface}-v1`,
        account_id: accountId,
        control_revision: 11,
        account_epoch: 7,
        database_generation_digest: sha256CanonicalContent({ suffix, generation: true }),
        surface,
        source_frontier_digest: sha256CanonicalContent({ suffix, surface, frontier: true }),
        source_fence_state: "held" as const,
        source_fence_receipt_digest: sha256CanonicalContent({ suffix, surface, fence: true }),
        record_count: index,
        record_set_digest: sha256CanonicalContent({ suffix, surface, set: true }),
      })),
      observed_at_epoch_seconds: rolledBackAt + 1,
    }).verified_manifest!;

    const repository = createPostgresStrandedRollbackRecoveryManifestRepository(pool);
    const manifest = manifestFor(sha256CanonicalContent({ suffix, rollback: true }));
    const stored = await repository.record(manifest);
    expect(stored.kind).toBe("stored");
    expect((await repository.record(manifest)).kind).toBe("replayed");
    const key = Object.freeze({
      version: "stranded-rollback-recovery-manifest-key-v1" as const,
      account_id: accountId,
      control_revision: 11,
      account_epoch: 7,
      database_generation_digest: manifest.database_generation_digest,
      manifest_digest: manifest.manifest_digest,
    });
    await expect(repository.load(key)).resolves.toEqual({
      kind: "found", manifest: stored.manifest,
    });
    await expect(repository.record(manifestFor(sha256CanonicalContent({
      suffix, rollback: "changed",
    })))).rejects.toMatchObject({ code: "manifest_conflict" });

    const counts = await ownerSql.unsafe<{ manifests: number; receipts: number }[]>(`SELECT
      (SELECT count(*)::int FROM omi_memory.account_stranded_rollback_recovery_manifests
        WHERE account_id = $1) manifests,
      (SELECT count(*)::int FROM omi_memory.account_stranded_rollback_recovery_surface_receipts
        WHERE account_id = $1) receipts`, [accountId]);
    expect([...counts]).toEqual([{ manifests: 1, receipts: 11 }]);
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.account_stranded_rollback_recovery_manifests WHERE account_id = $1",
        [accountId],
      );
    })).rejects.toMatchObject({ code: "42501" });

    await ownerSql.unsafe(`UPDATE omi_memory.account_control_heads
      SET conflict_reason = 'qualification_drift', conflict_at_control_revision = 11
      WHERE account_id = $1`, [accountId]);
    await expect(repository.load(key)).rejects.toMatchObject({ code: "control_denied" });
  }, 120_000);

  test("restore role installs retained terminal fences with exact replay and rollback", async () => {
    const suffix = randomUUID();
    const accountId = `account:restore:${suffix}`;
    const rollbackAccountId = `account:restore-rollback:${suffix}`;
    const dominatedAccountId = `account:restore-dominated:${suffix}`;
    const restore = Object.freeze({
      restore_id: `restore:${suffix}`,
      restore_scope: "postgresql" as const,
      restored_snapshot_digest: sha256CanonicalContent({ suffix, snapshot: true }),
      restore_completed_at_epoch_seconds: 1_800_000_000,
    });
    const terminal = Object.freeze({
      account_id: accountId,
      control_revision: 9,
      deletion_epoch: 12,
      terminal_record_digest: sha256CanonicalContent({ suffix, terminal: true }),
    });
    await ownerSql.begin(async (transaction) => {
      for (const account of [accountId, rollbackAccountId, dominatedAccountId]) {
        await transaction.unsafe(
          "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)",
          [account],
        );
        await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
          (account_id, control_revision, account_generation, account_epoch, lifecycle_state,
           deletion_epoch, observed_at, record_schema_version, record_json, content_hash)
          VALUES ($1, 9, 'rolled_back_stranded', 4, 'active', NULL, transaction_timestamp(),
                  'control-v1', '{}'::jsonb, $2)`, [account, "a".repeat(64)]);
        await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
          (account_id, control_revision, activated_epoch, activation_control_revision)
          VALUES ($1, 9, 4, 9)`, [account]);
      }
    });

    const target = createPostgresTombstoneRestoreTarget(pool);
    const first = await target.applyTerminalRecord({ restore, terminal_record: terminal });
    expect(first).toMatchObject({
      restore_id: restore.restore_id,
      restored_snapshot_digest: restore.restored_snapshot_digest,
      account_id: accountId,
      control_revision: 9,
      deletion_epoch: 12,
      result: "applied",
      error_code: null,
    });
    expect(await target.applyTerminalRecord({ restore, terminal_record: terminal })).toEqual(first);

    const stored = await ownerSql.unsafe<{
      fences: number; receipts: number; fence_epoch: string; receipt_result: string;
    }[]>(`SELECT
      (SELECT count(*)::int FROM omi_memory.account_restored_terminal_fences
        WHERE account_id = $1) fences,
      (SELECT count(*)::int FROM omi_memory.account_restore_terminal_application_receipts
        WHERE account_id = $1 AND restore_id = $2) receipts,
      (SELECT deletion_epoch::text FROM omi_memory.account_restored_terminal_fences
        WHERE account_id = $1 ORDER BY deletion_epoch DESC LIMIT 1) fence_epoch,
      (SELECT result FROM omi_memory.account_restore_terminal_application_receipts
        WHERE account_id = $1 AND restore_id = $2) receipt_result`, [accountId, restore.restore_id]);
    expect([...stored]).toEqual([{
      fences: 1, receipts: 1, fence_epoch: "12", receipt_result: "applied",
    }]);

    await expect(target.applyTerminalRecord({
      restore,
      terminal_record: { ...terminal, terminal_record_digest: "f".repeat(64) },
    })).rejects.toMatchObject({ code: "target_conflict" });

    await expect(target.withHeldTarget(restore, async (session) => {
      await session.apply({ ...terminal, account_id: rollbackAccountId });
      throw new Error("qualification rollback after restore target");
    })).rejects.toMatchObject({ code: "persistence_failed" });
    const rollbackCounts = await ownerSql.unsafe<{ fences: number; receipts: number }[]>(`SELECT
      (SELECT count(*)::int FROM omi_memory.account_restored_terminal_fences
        WHERE account_id = $1) fences,
      (SELECT count(*)::int FROM omi_memory.account_restore_terminal_application_receipts
        WHERE account_id = $1) receipts`, [rollbackAccountId]);
    expect([...rollbackCounts]).toEqual([{ fences: 0, receipts: 0 }]);

    const higherRestore = Object.freeze({ ...restore, restore_id: `restore:higher:${suffix}` });
    const olderRestore = Object.freeze({ ...restore, restore_id: `restore:older:${suffix}` });
    await expect(target.applyTerminalRecord({
      restore: higherRestore,
      terminal_record: {
        ...terminal,
        account_id: dominatedAccountId,
        deletion_epoch: 20,
        terminal_record_digest: sha256CanonicalContent({ suffix, terminal: "higher" }),
      },
    })).resolves.toMatchObject({ result: "applied", deletion_epoch: 20 });
    await expect(target.applyTerminalRecord({
      restore: olderRestore,
      terminal_record: { ...terminal, account_id: dominatedAccountId },
    })).resolves.toMatchObject({ result: "already_absent", deletion_epoch: 12 });
    const dominated = await ownerSql.unsafe<{ fences: number; max_epoch: string }[]>(`SELECT
      count(*)::int AS fences, max(deletion_epoch)::text AS max_epoch
      FROM omi_memory.account_restored_terminal_fences WHERE account_id = $1`,
    [dominatedAccountId]);
    expect([...dominated]).toEqual([{ fences: 1, max_epoch: "20" }]);

    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.hold_postgres_restore_target($1, 'postgresql', $2, $3)",
        [restore.restore_id, restore.restored_snapshot_digest, restore.restore_completed_at_epoch_seconds],
      );
    })).rejects.toMatchObject({ code: "42501" });
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_restore");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.account_restore_terminal_application_receipts WHERE account_id = $1",
        [accountId],
      );
    })).rejects.toMatchObject({ code: "42501" });
  }, 120_000);

  test("restore role records untrusted checkpoint candidates with exact replay and rollback", async () => {
    const suffix = randomUUID();
    const hashJson = (value: unknown) => createHash("sha256")
      .update(JSON.stringify(value), "utf8").digest("hex");
    const makeCandidate = (highWatermark: number, label = "candidate") => {
      const checkpoint = {
        version: "tombstone-replay-checkpoint-v1",
        restore_id: `restore:${label}:${suffix}`,
        restore_scope: "postgresql" as const,
        restored_snapshot_digest: sha256CanonicalContent({ suffix, snapshot: "candidate" }),
        restore_completed_at_epoch_seconds: 1_800_000_000,
        source_snapshot_digest: sha256CanonicalContent({ suffix, source: "candidate" }),
        source_high_watermark: highWatermark,
        manifest_digest: sha256CanonicalContent({ suffix, manifest: highWatermark }),
        terminal_source_receipt_binding_digest: sha256CanonicalContent({ suffix, sourceReceipt: highWatermark }),
        application_set_digest: sha256CanonicalContent({ suffix, applications: highWatermark }),
        traffic_fence_receipt_digest: sha256CanonicalContent({ suffix, fence: highWatermark }),
      };
      return Object.freeze({
        version: "postgres-restore-replay-checkpoint-candidate-v1" as const,
        restored_generation_digest: sha256CanonicalContent({ suffix, generation: true }),
        restore_id: checkpoint.restore_id,
        restore_scope: checkpoint.restore_scope,
        restored_snapshot_digest: checkpoint.restored_snapshot_digest,
        restore_completed_at_epoch_seconds: checkpoint.restore_completed_at_epoch_seconds,
        source_snapshot_digest: checkpoint.source_snapshot_digest,
        source_feed_generation_digest: sha256CanonicalContent({ suffix, feed: true }),
        partition_topology_digest: sha256CanonicalContent({ suffix, topology: true }),
        source_high_watermark: checkpoint.source_high_watermark,
        manifest_digest: checkpoint.manifest_digest,
        record_count: 1,
        terminal_source_receipt_binding_digest: checkpoint.terminal_source_receipt_binding_digest,
        application_set_digest: checkpoint.application_set_digest,
        terminal_feed_fence_receipt_digest: checkpoint.traffic_fence_receipt_digest,
        checkpoint_digest: hashJson(checkpoint),
      });
    };
    const repository = createPostgresRestoreReplayCheckpointRepository(pool);
    const candidate = makeCandidate(14);
    const recorded = await repository.record(candidate);
    expect(recorded).toMatchObject({
      result: "recorded",
      restored_generation_digest: candidate.restored_generation_digest,
      restore_id: candidate.restore_id,
    });
    const replayed = await repository.record(candidate);
    expect(replayed).toMatchObject({
      result: "replayed",
      candidate_digest: recorded.candidate_digest,
      persistence_receipt_digest: recorded.persistence_receipt_digest,
      recorded_at_epoch_micros: recorded.recorded_at_epoch_micros,
    });
    const loaded = await repository.load(candidate.restored_generation_digest, candidate.restore_id);
    expect(loaded).toMatchObject({
      kind: "loaded",
      candidate: {
        candidate_digest: recorded.candidate_digest,
        persistence_receipt_digest: recorded.persistence_receipt_digest,
        recorded_at_epoch_micros: recorded.recorded_at_epoch_micros,
        source_feed_generation_digest: candidate.source_feed_generation_digest,
        partition_topology_digest: candidate.partition_topology_digest,
      },
    });
    await expect(repository.record(makeCandidate(15))).rejects
      .toMatchObject({ code: "candidate_conflict" });

    const stored = await ownerSql.unsafe<{ rows: number; watermark: string }[]>(`SELECT
      count(*)::int AS rows, max(source_high_watermark)::text AS watermark
      FROM omi_memory.postgres_restore_replay_checkpoint_candidates WHERE restore_id = $1`,
    [candidate.restore_id]);
    expect([...stored]).toEqual([{ rows: 1, watermark: "14" }]);

    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.postgres_restore_replay_checkpoint_candidates WHERE restore_id = $1",
        [candidate.restore_id],
      );
    })).rejects.toMatchObject({ code: "42501" });
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.record_postgres_restore_replay_checkpoint_candidate($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)",
        [candidate.restored_generation_digest, candidate.restore_id,
          candidate.restored_snapshot_digest, candidate.restore_completed_at_epoch_seconds,
          candidate.source_snapshot_digest, candidate.source_feed_generation_digest,
          candidate.partition_topology_digest, candidate.source_high_watermark,
          candidate.manifest_digest, candidate.record_count,
          candidate.terminal_source_receipt_binding_digest, candidate.application_set_digest,
          candidate.terminal_feed_fence_receipt_digest, candidate.checkpoint_digest,
          recorded.candidate_digest],
      );
    })).rejects.toMatchObject({ code: "42501" });

    const rollbackCandidate = makeCandidate(16, "candidate-rollback");
    await ownerSql.unsafe(`
      CREATE OR REPLACE FUNCTION omi_memory.reject_restore_checkpoint_candidate()
      RETURNS trigger LANGUAGE plpgsql AS $fn$
      BEGIN RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'injected_restore_candidate_failure'; END
      $fn$;
      DROP TRIGGER IF EXISTS reject_restore_checkpoint_candidate
        ON omi_memory.postgres_restore_replay_checkpoint_candidates;
      CREATE TRIGGER reject_restore_checkpoint_candidate BEFORE INSERT
        ON omi_memory.postgres_restore_replay_checkpoint_candidates
        FOR EACH ROW EXECUTE FUNCTION omi_memory.reject_restore_checkpoint_candidate();
    `, [], { prepare: false });
    try {
      await expect(repository.record(rollbackCandidate)).rejects
        .toMatchObject({ code: "persistence_failed" });
      const rollbackRows = await ownerSql.unsafe<{ rows: number }[]>(`SELECT count(*)::int AS rows
        FROM omi_memory.postgres_restore_replay_checkpoint_candidates WHERE restore_id = $1`,
      [rollbackCandidate.restore_id]);
      expect([...rollbackRows]).toEqual([{ rows: 0 }]);
    } finally {
      await ownerSql.unsafe(`
        DROP TRIGGER IF EXISTS reject_restore_checkpoint_candidate
          ON omi_memory.postgres_restore_replay_checkpoint_candidates;
        DROP FUNCTION IF EXISTS omi_memory.reject_restore_checkpoint_candidate();
      `, [], { prepare: false });
    }
  }, 120_000);
});
