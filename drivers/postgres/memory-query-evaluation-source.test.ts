import { describe, expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import {
  defineMemoryQueryEvaluationInputRepository,
  materializeMemoryQueryEvaluationInput,
} from
  "../../apps/service/stores/memory-query-evaluation-input-repository";
import type { GraphSnapshot } from "../../core/retrieve";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlStatement,
} from "./connection";
import {
  createPostgresMemoryQueryEvaluationGraphSource,
  createPostgresMemoryQueryEvaluationInputRepository,
} from "./memory-query-evaluation-source";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const hex = (character: string): string => character.repeat(64);
const authority = (overrides: Partial<AuthorityStateRow> = {}): AuthorityStateRow => ({
  account_id: "account:alice", principal_id: "worker:evaluator", application_id: "app:evaluator",
  credential_id: "credential:evaluator", credential_generation: 1,
  capability: "memories.experiments.shadow", grant_id: "grant:evaluator", grant_version: 1,
  account_epoch: 7, control_conflict_reason: null, control_conflict_at_revision: null,
  destination_activation_epoch: 7, destination_activation_revision: 17,
  lifecycle_state: "active", deletion_epoch: null, account_generation: "new",
  credential_lifecycle: "active", grant_lifecycle: "active", grant_enabled: true,
  authentication_strength: "service-workload", credential_expires_at_epoch_seconds: 300,
  control_revision: 17, control_content_hash: hex("1"), credential_content_hash: hex("2"),
  grant_content_hash: hex("3"), db_now_epoch_seconds: 150, ...overrides,
});
const context = (row = authority()) => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1", principal_id: "worker:evaluator",
  account_id: "account:alice", application_id: "app:evaluator",
  credential_id: "credential:evaluator", credential_generation: 1,
  capability: "memories.experiments.shadow", grant_id: "grant:evaluator", grant_version: 1,
  account_epoch: 7, destination_activation_revision: 17, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 200,
  authorization_state_digest: authorizationStateDigest(row),
}, 150);

const graph = (generation = 0): GraphSnapshot => Object.freeze({
  owner_account_id: "account:alice", graph_generation: generation,
  claims: Object.freeze([]), entities: Object.freeze([]), predicates: Object.freeze([]),
  predicate_assertions: Object.freeze([]), identity_constraints: Object.freeze([]),
  mentions: Object.freeze([]), identity_authorizations: Object.freeze([]), identity_support: Object.freeze([]),
  events: Object.freeze([]), evidence: Object.freeze([]),
  liveness_causes: Object.freeze({
    purged_claim_revision_ids: Object.freeze([]), forgotten_claim_revision_ids: Object.freeze([]),
  }),
  adjacency: Object.freeze([]), source_local_roles: Object.freeze([]), placement_artifacts: Object.freeze([]),
});

class FakeConnection implements CheckedOutPostgresConnection {
  readonly connectionIdentity = Object.freeze({ id: "query-source" });
  readonly statements: SqlStatement[] = [];
  readonly inputs = new Map<string, Record<string, unknown>>();
  graphGeneration = 0;
  authority = authority();
  insertRowCount = 1;

  async query<Row extends Record<string, unknown>>(statement: SqlStatement): Promise<readonly Row[]> {
    this.statements.push(statement);
    if (statement.name === "authority.set_local") return [];
    if (statement.name === "authority.lock_and_revalidate") return [this.authority as unknown as Row];
    if (statement.name === "experiment.query_input_load") {
      const value = this.inputs.get(String(statement.values[1]));
      return value ? [value as Row] : [];
    }
    if (statement.name === "snapshot.graph_head") return [{ sequence: this.graphGeneration } as unknown as Row];
    if ([
      "snapshot.revisions", "snapshot.identity_support", "snapshot.adjacency",
      "snapshot.source_local_roles", "snapshot.liveness", "snapshot.placement_artifacts",
    ].includes(statement.name)) return [];
    return [];
  }

  async execute(statement: SqlStatement): Promise<{ rowCount: number }> {
    this.statements.push(statement);
    if (statement.name === "experiment.query_input_insert") {
      const value = statement.values;
      this.inputs.set(String(value[1]), {
        account_id: value[0], source_ref: value[1], input_version: value[2], account_epoch: value[3],
        input_ref: value[4], input_frontier: value[5], query_text: value[6], account_timezone: value[7],
        graph_generation: value[8], graph_snapshot_digest: value[9], stage_request_digest: value[10],
        content_hash: value[11],
      });
    }
    return { rowCount: this.insertRowCount };
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
    return callback(this.connection);
  }
}

describe("PostgreSQL query evaluation input and graph source", () => {
  test("stages, replays, and loads one exact query against the matching coherent graph", async () => {
    const connection = new FakeConnection();
    const pool = new FakePool(connection);
    const inputs = createPostgresMemoryQueryEvaluationInputRepository({ pool });
    const source = createPostgresMemoryQueryEvaluationGraphSource({ pool });
    const input = materializeMemoryQueryEvaluationInput(context(), {
      input_ref: `mqir1_${hex("a")}`, query_text: "Where do I work?",
      account_timezone: "America/New_York", graph_snapshot: graph(),
    });
    await expect(inputs.stage(context(), input)).resolves.toEqual({ kind: "staged", input });
    await expect(inputs.stage(context(), input)).resolves.toEqual({ kind: "replayed", input });
    await expect(source.load(context(), {
      source_kind: "authorized_graph_snapshot", source_ref: input.source_ref,
      input_frontier: input.input_frontier,
    })).resolves.toEqual({
      kind: "found", owner_account_id: "account:alice", account_epoch: 7,
      source_ref: input.source_ref, input_frontier: input.input_frontier,
      query_text: input.query_text, account_timezone: input.account_timezone,
      graph_snapshot: graph(),
    });
    expect(connection.statements.slice(0, 3).map((statement) => statement.name)).toEqual([
      "authority.set_local", "authority.lock_and_revalidate", "experiment.query_input_load",
    ]);
  });

  test("frontier or graph drift returns not found and revocation is checked before stored input", async () => {
    const connection = new FakeConnection();
    const pool = new FakePool(connection);
    const inputs = createPostgresMemoryQueryEvaluationInputRepository({ pool });
    const source = createPostgresMemoryQueryEvaluationGraphSource({ pool });
    const input = materializeMemoryQueryEvaluationInput(context(), {
      input_ref: `mqir1_${hex("b")}`, query_text: "What changed?",
      account_timezone: "UTC", graph_snapshot: graph(),
    });
    await inputs.stage(context(), input);
    await expect(source.load(context(), {
      source_kind: "authorized_graph_snapshot", source_ref: input.source_ref,
      input_frontier: `mqef1_${hex("c")}`,
    })).resolves.toEqual({ kind: "not_found" });
    connection.graphGeneration = 1;
    await expect(source.load(context(), {
      source_kind: "authorized_graph_snapshot", source_ref: input.source_ref,
      input_frontier: input.input_frontier,
    })).resolves.toEqual({ kind: "not_found" });
    connection.authority = authority({ grant_lifecycle: "revoked", grant_enabled: false });
    await expect(inputs.load(context(), input.source_ref)).resolves.toEqual({
      kind: "authorization_denied", reason: "grant_inactive",
    });
  });

  test("a concurrent exact insert replays while changed bytes conflict", async () => {
    const connection = new FakeConnection();
    const pool = new FakePool(connection);
    const inputs = createPostgresMemoryQueryEvaluationInputRepository({ pool });
    const input = materializeMemoryQueryEvaluationInput(context(), {
      input_ref: `mqir1_${hex("e")}`, query_text: "Where was I?",
      account_timezone: "UTC", graph_snapshot: graph(),
    });
    await expect(inputs.stage(context(), input)).resolves.toEqual({ kind: "staged", input });
    connection.insertRowCount = 0;
    await expect(inputs.stage(context(), input)).resolves.toEqual({ kind: "replayed", input });
    const stored = connection.inputs.get(input.source_ref)!;
    stored.query_text = "changed";
    await expect(inputs.stage(context(), input)).resolves.toEqual({ kind: "idempotency_conflict" });
  });

  test("owner, graph, query, timezone, and forged input fail before persistence", async () => {
    expect(() => materializeMemoryQueryEvaluationInput(context(), {
      input_ref: `mqir1_${hex("d")}`, query_text: " bad ", account_timezone: "UTC",
      graph_snapshot: graph(),
    })).toThrow("invalid_query");
    expect(() => materializeMemoryQueryEvaluationInput(context(), {
      input_ref: `mqir1_${hex("d")}`, query_text: "good", account_timezone: "bad timezone",
      graph_snapshot: graph(),
    })).toThrow("invalid_input");
    expect(() => materializeMemoryQueryEvaluationInput(context(), {
      input_ref: `mqir1_${hex("d")}`, query_text: "good", account_timezone: "Not/A_Real_Zone",
      graph_snapshot: graph(),
    })).toThrow("invalid_input");
    expect(() => materializeMemoryQueryEvaluationInput(context(), {
      input_ref: `mqir1_${hex("d")}`, query_text: "good", account_timezone: "UTC",
      graph_snapshot: { ...graph(), owner_account_id: "account:bob" },
    })).toThrow("invalid_input");
    const input = materializeMemoryQueryEvaluationInput(context(), {
      input_ref: `mqir1_${hex("f")}`, query_text: "good", account_timezone: "UTC",
      graph_snapshot: graph(),
    });
    const repository = createPostgresMemoryQueryEvaluationInputRepository({
      pool: new FakePool(new FakeConnection()),
    });
    await expect(repository.stage(context(), { ...input })).rejects.toThrow("unverified_input");
  });

  test("hostile repository outcomes never execute accessors", async () => {
    let getterCalls = 0;
    const hostile = () => Object.defineProperty({}, "kind", {
      enumerable: true,
      get() { getterCalls += 1; return "staged"; },
    });
    const repository = defineMemoryQueryEvaluationInputRepository({
      stage: async () => hostile(),
      load: async () => hostile(),
    });
    const input = materializeMemoryQueryEvaluationInput(context(), {
      input_ref: `mqir1_${hex("9")}`, query_text: "good", account_timezone: "UTC",
      graph_snapshot: graph(),
    });
    await expect(repository.stage(context(), input)).rejects.toThrow("invalid_outcome");
    await expect(repository.load(context(), input.source_ref)).rejects.toThrow("invalid_outcome");
    expect(getterCalls).toBe(0);
  });
});
