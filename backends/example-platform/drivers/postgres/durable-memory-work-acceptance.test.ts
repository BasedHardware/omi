import { describe, expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import {
  durableMemoryWorkAcceptanceRequestDigest,
  durableMemoryWorkInputManifestDigest,
  type DurableMemoryWorkAcceptanceRequest,
  type DurableMemoryWorkInputManifestEntry,
} from "../../apps/service/stores/durable-memory-work-repository";
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
  DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
  registerDurableMemoryWorkExecutionPolicy,
} from "../../core/consolidate/execution-policy";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlStatement,
} from "./connection";
import { createPostgresDurableMemoryWorkAcceptanceRepository } from "./durable-memory-work-acceptance";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const digest = (character: string): string => character.repeat(64);

const authorityRow = (): AuthorityStateRow => ({
  account_id: "account:alice", principal_id: "principal:acceptor", application_id: "app:ingestion",
  credential_id: "credential:one", credential_generation: 4, capability: "memories.work.accept",
  grant_id: "grant:accept", grant_version: 9, account_epoch: 7,
  control_conflict_reason: null, control_conflict_at_revision: null,
  destination_activation_epoch: 7, destination_activation_revision: 17,
  lifecycle_state: "active", deletion_epoch: null, account_generation: "new",
  credential_lifecycle: "active", grant_lifecycle: "active", grant_enabled: true,
  authentication_strength: "service-workload", credential_expires_at_epoch_seconds: 300,
  control_revision: 17, control_content_hash: digest("1"),
  credential_content_hash: digest("2"), grant_content_hash: digest("3"),
  db_now_epoch_seconds: 150,
});

const context = () => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "principal:acceptor", account_id: "account:alice", application_id: "app:ingestion",
  credential_id: "credential:one", credential_generation: 4, capability: "memories.work.accept",
  grant_id: "grant:accept", grant_version: 9, account_epoch: 7,
  destination_activation_revision: 17, lifecycle_state: "active", deletion_epoch: null,
  authentication_strength: "service-workload", issued_at_epoch_seconds: 100,
  expires_at_epoch_seconds: 200, authorization_state_digest: authorizationStateDigest(authorityRow()),
}, 150);

const assignment = () => {
  const strategy = registerMemoryStrategy({
    version: MEMORY_STRATEGY_VERSION, strategy_id: "strategy:formation:authority",
    work_kind: "formation",
    coordinates: {
      strategy_version: "formation:v1", model_version: "deepseek-flash:v1",
      prompt_version: "prompt:v1", policy_version: "policy:v1", code_version: "code:v1",
      schema_version: "schema:v1", tokenizer_version: "tokenizer:v1", tool_version: "none",
      result_contract_version: "formation-result:v2", speaker_strategy_version: "speaker:v1",
      boundary_strategy_version: "boundary:deepseek:v1",
    },
  });
  const policy = defineMemoryStrategyAssignmentPolicy({
    policy_id: "policy:formation:v1", work_kind: "formation", unit_kind: "session",
    key_version: "assignment-key:v1", authority_strategy_id: strategy.strategy_id,
    shadow_candidates: [],
  }, [strategy]);
  return createMemoryStrategyAssigner(new Uint8Array(32).fill(7)).assign({
    owner_account_id: "account:alice", unit_ref: "session:one", policy, strategies: [strategy],
  });
};

const manifest = (): readonly DurableMemoryWorkInputManifestEntry[] => Object.freeze([
  Object.freeze({ input_kind: "evidence_revision", input_ref: "evidence:one", input_digest: digest("b") }),
  Object.freeze({
    input_kind: "graph_frontier", input_ref: "frontier:one",
    input_digest: sha256CanonicalContent({ graph_frontier: "frontier:one" }),
  }),
]);

const request = (acceptedAtEventTime = 100): DurableMemoryWorkAcceptanceRequest => {
  const inputs = manifest();
  const strategyAssignment = assignment();
  const accepted: AcceptedDurableMemoryWork = {
    version: DURABLE_MEMORY_WORK_VERSION, job_id: "job:formation:one",
    owner_account_id: "account:alice", account_epoch: 7,
    lifecycle_state: "active", deletion_epoch: null, work_kind: "formation",
    input_frontier: "frontier:one", input_digest: durableMemoryWorkInputManifestDigest(inputs),
    execution_contract_digest: strategyAssignment.authority.execution_contract_digest,
    accepted_at_event_time: acceptedAtEventTime, max_attempts: 2,
  };
  const pending = acceptDurableMemoryWork(accepted);
  const executionPolicy = registerDurableMemoryWorkExecutionPolicy({
    version: DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
    policy_id: "execution-policy:formation:qualification:v1",
    work_kind: "formation",
    execution_contract_digest: strategyAssignment.authority.execution_contract_digest,
    max_attempts: 2,
    lease_duration_seconds: 30,
    retry_delays_seconds: [10],
  });
  return Object.freeze({
    accepted_work: accepted, input_manifest: inputs, strategy_assignment: strategyAssignment,
    execution_policy: executionPolicy,
    request_digest: durableMemoryWorkAcceptanceRequestDigest(
      pending, inputs, strategyAssignment, executionPolicy,
    ),
  });
};

interface FakeSnapshot {
  acceptanceHash: string | null;
  stateDigest: string | null;
  manifest: { input_kind: string; input_ref: string; input_digest: string }[];
  immutableHashes: Map<string, string>;
}

class FakeConnection implements CheckedOutPostgresConnection {
  readonly connectionIdentity = Object.freeze({ client: "only-client" });
  readonly statements: SqlStatement[] = [];
  acceptanceHash: string | null = null;
  stateDigest: string | null = null;
  manifest: { input_kind: string; input_ref: string; input_digest: string }[] = [];
  immutableHashes = new Map<string, string>();
  failAt: string | null = null;

  snapshot(): FakeSnapshot {
    return {
      acceptanceHash: this.acceptanceHash, stateDigest: this.stateDigest,
      manifest: structuredClone(this.manifest), immutableHashes: new Map(this.immutableHashes),
    };
  }

  restore(snapshot: FakeSnapshot): void {
    this.acceptanceHash = snapshot.acceptanceHash;
    this.stateDigest = snapshot.stateDigest;
    this.manifest = snapshot.manifest;
    this.immutableHashes = snapshot.immutableHashes;
  }

  async query<Row extends Record<string, unknown>>(statement: SqlStatement): Promise<readonly Row[]> {
    this.statements.push(statement);
    if (statement.name === "authority.set_local" || statement.name === "work.acceptance.lock_key") return [];
    if (statement.name === "authority.lock_and_revalidate") return [authorityRow() as unknown as Row];
    if (statement.name === "work.acceptance.lookup") {
      return this.acceptanceHash === null ? [] : [{ content_hash: this.acceptanceHash } as unknown as Row];
    }
    if (statement.name === "work.acceptance.control_revision") {
      return [{ control_revision: "17" } as unknown as Row];
    }
    if (statement.name === "work.acceptance.pending_verify") {
      return this.stateDigest === null ? [] : [{
        state_revision: "0", state_digest: this.stateDigest, state: "pending",
      } as unknown as Row];
    }
    if (statement.name === "work.acceptance.manifest_verify") return this.manifest as unknown as readonly Row[];
    if (statement.name.endsWith(".verify")) {
      const contentHash = this.immutableHashes.get(statement.name.slice(0, -".verify".length));
      return contentHash ? [{ content_hash: contentHash } as unknown as Row] : [];
    }
    return [];
  }

  async execute(statement: SqlStatement): Promise<{ rowCount: number }> {
    this.statements.push(statement);
    if (this.failAt === statement.name) throw { code: "XX000", message: "private transcript" };
    if (statement.name.endsWith(".insert")
      && (statement.name.startsWith("work.strategy_")
        || statement.name === "work.execution_policy.insert")) {
      this.immutableHashes.set(statement.name.slice(0, -".insert".length), String(statement.values.at(-1)));
    } else if (statement.name === "work.acceptance.insert") {
      this.acceptanceHash = String(statement.values[12]);
    } else if (statement.name === "work.acceptance.manifest_insert") {
      this.manifest.push({
        input_kind: String(statement.values[3]), input_ref: String(statement.values[4]),
        input_digest: String(statement.values[5]),
      });
    } else if (statement.name === "work.acceptance.state_insert") {
      this.stateDigest = String(statement.values[2]);
    }
    return { rowCount: 1 };
  }
}

class FakePool implements PostgresTransactionPool {
  readonly options: SerializableTransactionOptions[] = [];
  constructor(readonly connection: FakeConnection) {}

  async withTransaction<Result>(
    options: SerializableTransactionOptions,
    callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
  ): Promise<Result> {
    this.options.push(options);
    const snapshot = this.connection.snapshot();
    try {
      return await callback(this.connection);
    } catch (error) {
      this.connection.restore(snapshot);
      throw error;
    }
  }
}

describe("PostgreSQL durable work acceptance", () => {
  test("persists exact strategy, manifest, pending state, and replays without duplicate writes", async () => {
    const connection = new FakeConnection();
    const pool = new FakePool(connection);
    const repository = createPostgresDurableMemoryWorkAcceptanceRepository({ pool });
    const acceptedRequest = request();

    await expect(repository.accept(context(), acceptedRequest)).resolves.toMatchObject({
      kind: "accepted", job: { job_id: "job:formation:one", state: "pending" },
    });
    const writeCount = connection.statements.filter((statement) =>
      statement.name.endsWith(".insert") || statement.name.includes("manifest_insert")).length;
    expect(connection.manifest.map((entry) => entry.input_kind))
      .toEqual(["evidence_revision", "graph_frontier"]);
    expect(connection.statements.map((statement) => statement.name)).toEqual(expect.arrayContaining([
      "authority.lock_and_revalidate", "work.strategy_definition.insert",
      "work.strategy_policy.insert", "work.strategy_bundle.insert",
      "work.execution_policy.insert",
      "work.acceptance.insert", "work.acceptance.state_insert", "work.acceptance.head_insert",
    ]));

    await expect(repository.accept(context(), acceptedRequest)).resolves.toMatchObject({
      kind: "replayed", job: { state: "pending" },
    });
    expect(connection.statements.filter((statement) =>
      statement.name.endsWith(".insert") || statement.name.includes("manifest_insert")).length)
      .toBe(writeCount);
    expect(pool.options).toEqual([
      { isolationLevel: "serializable", accessMode: "read write" },
      { isolationLevel: "serializable", accessMode: "read write" },
    ]);
  });

  test("different accepted bytes conflict and failed persistence rolls back content-safely", async () => {
    const connection = new FakeConnection();
    const repository = createPostgresDurableMemoryWorkAcceptanceRepository({ pool: new FakePool(connection) });
    const first = request();
    await expect(repository.accept(context(), first)).resolves.toMatchObject({ kind: "accepted" });
    await expect(repository.accept(context(), request(101))).resolves.toEqual({
      kind: "idempotency_conflict",
    });

    const freshConnection = new FakeConnection();
    freshConnection.failAt = "work.acceptance.state_insert";
    const failing = createPostgresDurableMemoryWorkAcceptanceRepository({ pool: new FakePool(freshConnection) });
    await expect(failing.accept(context(), request())).rejects.toMatchObject({
      code: "persistence_failed", message: "persistence_failed",
    });
    expect(freshConnection.acceptanceHash).toBeNull();
    expect(freshConnection.manifest).toEqual([]);
    expect(JSON.stringify(freshConnection.statements)).not.toContain("private transcript");
  });
});
