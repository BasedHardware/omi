import { describe, expect, test } from "bun:test";

import { acceptDurableMemoryWork } from "../../core/consolidate/state-machine";
import type { GraphSnapshot } from "../../core/retrieve";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import { createAuthorizedLedgerWriteContextIssuer } from
  "../../apps/service/auth/authorized-context-internal";
import { durableMemoryWorkInputManifestDigest } from
  "../../apps/service/stores/durable-memory-work-repository";
import type { ListenSessionRecord, ListenTranscriptSegment } from
  "../../apps/service/stores/listen-store";
import {
  defineListenAttributionBeliefInputStager,
} from "../../apps/service/listen/attribution-belief-input-source";
import {
  materializeListenFormationSnapshot,
  sealListenFormationFinalization,
} from "../../apps/service/listen/formation-ingestion";
import {
  formationWorkInputManifest,
} from "../../apps/service/workers/formation-work-producer";
import {
  formationWorkInputStageRequestDigest,
  materializeStagedFormationWorkInput,
} from "../../apps/service/workers/formation-work-input-repository";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlStatement,
} from "./connection";
import {
  createPostgresAcceptedFormationBeliefSource,
  createPostgresListenAttributionBeliefInputRepository,
} from "./listen-attribution-belief-input";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const hex = (character: string): string => character.repeat(64);
const owner = "account:alice";

const authority = (overrides: Partial<AuthorityStateRow> = {}): AuthorityStateRow => ({
  account_id: owner, principal_id: "worker:belief-source", application_id: "app:belief-source",
  credential_id: "credential:belief-source", credential_generation: 1,
  capability: "memories.experiments.shadow", grant_id: "grant:belief-source", grant_version: 1,
  account_epoch: 7, control_conflict_reason: null, control_conflict_at_revision: null,
  destination_activation_epoch: 7, destination_activation_revision: 17,
  lifecycle_state: "active", deletion_epoch: null, account_generation: "new",
  credential_lifecycle: "active", grant_lifecycle: "active", grant_enabled: true,
  authentication_strength: "service-workload", credential_expires_at_epoch_seconds: 300,
  control_revision: 17, control_content_hash: hex("1"), credential_content_hash: hex("2"),
  grant_content_hash: hex("3"), db_now_epoch_seconds: 150, ...overrides,
});

const context = (row = authority()) => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1", principal_id: row.principal_id,
  account_id: row.account_id, application_id: row.application_id,
  credential_id: row.credential_id, credential_generation: row.credential_generation,
  capability: row.capability, grant_id: row.grant_id, grant_version: row.grant_version,
  account_epoch: row.account_epoch, destination_activation_revision: row.destination_activation_revision,
  lifecycle_state: row.lifecycle_state, deletion_epoch: row.deletion_epoch,
  authentication_strength: row.authentication_strength, issued_at_epoch_seconds: 100,
  expires_at_epoch_seconds: 200, authorization_state_digest: authorizationStateDigest(row),
}, 150);

const segments = (): readonly ListenTranscriptSegment[] => Object.freeze([
  Object.freeze({ id: "segment:one", text: "I am planning Atlas.", is_user: true, start: 1, end: 2 }),
  Object.freeze({ id: "segment:two", text: "Someone else answers.", is_user: false, start: 3, end: 4 }),
]);

const session = (): ListenSessionRecord => Object.freeze({
  id: "listen-session:pg-belief", conversationId: "conversation:pg-belief",
  clientConversationId: null, startedAt: "2026-08-12T12:00:00.000Z",
  updatedAt: "2026-08-12T12:01:00.000Z", endedAt: "2026-08-12T12:01:00.000Z",
  status: "completed", source: "omi", codec: "pcm16", sampleRate: 16_000, channels: 1,
});

const snapshot = () => materializeListenFormationSnapshot({
  finalization: sealListenFormationFinalization({ owner_account_id: owner, session: session(), segments: segments() }),
  graph_snapshot: {
    owner_account_id: owner, graph_generation: 7, claims: [], entities: [], predicates: [],
    identity_authorizations: [], adjacency: [],
  } satisfies GraphSnapshot,
  source_language: "en", account_timezone: "UTC",
  reference_clock_query_at: "2026-08-12T12:01:01.000Z", policy_version: "policy:listen:v1",
  predicate_alias_generation: "predicate:7", authorization_generation: "authorization:7",
  stm_generation: "stm:7",
});

const stagedFormation = () => {
  const input = snapshot();
  const pending = acceptDurableMemoryWork({
    version: "durable-memory-work-v1", job_id: input.work_id,
    owner_account_id: owner, account_epoch: 7, lifecycle_state: "active", deletion_epoch: null,
    work_kind: "formation", input_frontier: input.input_frontier,
    input_digest: durableMemoryWorkInputManifestDigest(formationWorkInputManifest(input)),
    execution_contract_digest: hex("4"), accepted_at_event_time: 100, max_attempts: 3,
  });
  const body = { pending_job: pending, snapshot: input };
  return materializeStagedFormationWorkInput({
    ...body, request_digest: formationWorkInputStageRequestDigest(body),
  });
};

const formationRow = () => {
  const input = stagedFormation();
  return {
    input_version: input.version, staged_input_id: input.staged_input_id,
    account_id: input.owner_account_id, job_id: input.job_id, account_epoch: input.account_epoch,
    accepted_work_digest: input.accepted_work_digest, input_frontier: input.input_frontier,
    input_digest: input.input_digest, execution_contract_digest: input.execution_contract_digest,
    snapshot_digest: input.snapshot_digest, snapshot_json: input.snapshot,
    stage_request_digest: input.stage_request_digest,
    content_hash: sha256CanonicalContent({
      contract_version: "formation-work-staged-input-content-v1", staged_input: input,
    }),
  };
};

class FakeConnection implements CheckedOutPostgresConnection {
  readonly connectionIdentity = Object.freeze({ id: "listen-belief-source" });
  readonly statements: SqlStatement[] = [];
  readonly beliefRows = new Map<string, Record<string, unknown>>();
  authority = authority();
  accepted = true;
  formationOverride: unknown = null;

  async query<Row extends Record<string, unknown>>(statement: SqlStatement): Promise<readonly Row[]> {
    this.statements.push(statement);
    if (statement.name === "authority.set_local") return [];
    if (statement.name === "authority.lock_and_revalidate") return [this.authority as unknown as Row];
    if (statement.name === "belief.accepted_formation_input.read") {
      return this.accepted
        ? [(this.formationOverride ?? formationRow()) as Row]
        : [];
    }
    if (statement.name === "belief.listen_input_set.lock") return [];
    if (statement.name === "belief.listen_input_set.read") {
      const selected = this.beliefRows.get(String(statement.values[0]));
      if (!selected) return [];
      return [...this.beliefRows.values()]
        .filter((row) => row.formation_work_id === selected.formation_work_id)
        .sort((left, right) => Number(left.input_ordinal) - Number(right.input_ordinal)) as Row[];
    }
    if (statement.name === "belief.listen_input.insert") {
      const value = statement.values;
      const row = {
        input_ref: value[0], input_version: value[1], account_epoch: value[2],
        formation_work_id: value[3], source_snapshot_digest: value[4], set_digest: value[5],
        input_count: value[6], input_ordinal: value[7], input_digest: value[8],
        graph_frontier: value[9], stage_request_digest: value[10],
        input_json: JSON.parse(String(value[11])), content_hash: value[12], account_id: owner,
      };
      this.beliefRows.set(String(row.input_ref), row);
      return [{ inserted: true } as unknown as Row];
    }
    return [];
  }

  async execute(statement: SqlStatement): Promise<{ rowCount: number }> {
    this.statements.push(statement);
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
    return callback(this.connection);
  }
}

describe("PostgreSQL Listen attribution belief inputs", () => {
  test("reads only accepted formation, stages the complete set, and replays", async () => {
    const connection = new FakeConnection();
    const pool = new FakePool(connection);
    const source = createPostgresAcceptedFormationBeliefSource({ pool });
    const repository = createPostgresListenAttributionBeliefInputRepository({ pool });
    const stager = defineListenAttributionBeliefInputStager({ source, repository });
    const workId = snapshot().work_id;
    const staged = await stager.stageAcceptedFormation(context(), workId);
    expect(staged.kind).toBe("staged");
    if (staged.kind !== "staged") throw new Error("expected staged set");
    expect(connection.beliefRows.size).toBe(2);
    await expect(stager.stageAcceptedFormation(context(), workId))
      .resolves.toMatchObject({ kind: "replayed" });
    await expect(repository.load(context(), staged.set.inputs[0]!.input_ref))
      .resolves.toMatchObject({ kind: "found" });
    expect(JSON.stringify([...connection.beliefRows.values()])).not.toContain("Atlas");
    expect(pool.options.every((option) => option.isolationLevel === "serializable")).toBeTrue();
  });

  test("unaccepted formation is unavailable and revocation stops before source SQL", async () => {
    const connection = new FakeConnection();
    const pool = new FakePool(connection);
    const source = createPostgresAcceptedFormationBeliefSource({ pool });
    connection.accepted = false;
    await expect(source.load(context(), snapshot().work_id)).resolves.toEqual({ kind: "not_found" });
    const before = connection.statements.length;
    connection.authority = authority({ grant_lifecycle: "revoked", grant_enabled: false });
    await expect(source.load(context(), snapshot().work_id)).resolves.toEqual({
      kind: "authorization_denied", reason: "grant_inactive",
    });
    expect(connection.statements.slice(before).map((statement) => statement.name)).toEqual([
      "authority.set_local", "authority.lock_and_revalidate",
    ]);
  });

  test("incomplete or corrupted persisted sets fail closed", async () => {
    const connection = new FakeConnection();
    const pool = new FakePool(connection);
    const source = createPostgresAcceptedFormationBeliefSource({ pool });
    const repository = createPostgresListenAttributionBeliefInputRepository({ pool });
    const stager = defineListenAttributionBeliefInputStager({ source, repository });
    const staged = await stager.stageAcceptedFormation(context(), snapshot().work_id);
    if (staged.kind !== "staged") throw new Error("expected staged set");
    connection.beliefRows.delete(staged.set.inputs[1]!.input_ref);
    await expect(repository.load(context(), staged.set.inputs[0]!.input_ref))
      .rejects.toThrow("persistence_failed");
    const row = connection.beliefRows.get(staged.set.inputs[0]!.input_ref)!;
    row.content_hash = hex("f");
    await expect(repository.load(context(), staged.set.inputs[0]!.input_ref))
      .rejects.toThrow("persistence_failed");
  });

  test("hostile persistence rows fail closed without invoking accessors", async () => {
    const connection = new FakeConnection();
    const source = createPostgresAcceptedFormationBeliefSource({ pool: new FakePool(connection) });
    let getterCalls = 0;
    const hostile = { ...formationRow() };
    Object.defineProperty(hostile, "snapshot_json", {
      enumerable: true,
      get() { getterCalls += 1; return snapshot(); },
    });
    connection.formationOverride = hostile;
    await expect(source.load(context(), snapshot().work_id)).rejects.toThrow("persistence_failed");
    expect(getterCalls).toBe(0);
  });
});
