import { describe, expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import {
  productProjectionWriteRequestDigest,
  type ProductGraphCoordinate,
  type ProductProjectionPayload,
  type ProductProjectionWriteBody,
} from "../../apps/service/stores/product-projection-repository";
import {
  appendProductMembership,
  birthProductProposition,
  buildProductGroupProjection,
  buildProductProjectionRevision,
  buildProductPropositionRedirect,
} from "../../core/retrieve/product-projection";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlStatement,
} from "./connection";
import { createPostgresProductProjectionWriteRepository } from "./product-projection-repository";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const digest = (character: string): string => character.repeat(64);

const authorityRow = (overrides: Partial<AuthorityStateRow> = {}): AuthorityStateRow => ({
  account_id: "account:alice", principal_id: "principal:alice", application_id: "app:projector",
  credential_id: "credential:projector", credential_generation: 4, capability: "memories.project",
  grant_id: "grant:projector", grant_version: 9, account_epoch: 12,
  control_conflict_reason: null, control_conflict_at_revision: null,
  destination_activation_epoch: 12, destination_activation_revision: 17,
  lifecycle_state: "active", deletion_epoch: null, account_generation: "new",
  credential_lifecycle: "active", grant_lifecycle: "active", grant_enabled: true,
  authentication_strength: "service-workload", credential_expires_at_epoch_seconds: 300,
  control_revision: 17, control_content_hash: digest("1"),
  credential_content_hash: digest("2"), grant_content_hash: digest("3"),
  db_now_epoch_seconds: 150,
  ...overrides,
});

const context = (row = authorityRow()) => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1", principal_id: "principal:alice",
  account_id: "account:alice", application_id: "app:projector",
  credential_id: "credential:projector", credential_generation: 4,
  capability: "memories.project", grant_id: "grant:projector", grant_version: 9,
  account_epoch: 12, destination_activation_revision: 17, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 200,
  authorization_state_digest: authorizationStateDigest(row),
}, 150);

const fixture = () => {
  const graph: ProductGraphCoordinate = {
    owner_account_id: "account:alice", graph_frontier: "frontier:one",
    graph_commit_id: "commit:one", graph_commit_sequence: 1,
  };
  const born = birthProductProposition({
    owner_account_id: "account:alice", proposition_id: "proposition:one",
    birth_claim_lineage_id: "lineage:one", origin: "native",
    graph_frontier: graph.graph_frontier, input_digest: digest("4"),
    result_digest: digest("5"), created_at_event_time: 10,
  });
  const rendered_content = Object.freeze({ title: "safe rendered product" });
  const rendered_content_digest = sha256CanonicalContent(rendered_content);
  const projection = buildProductProjectionRevision({
    identity: born.identity, membership: born.membership, projection_sequence: 1,
    graph_frontier: graph.graph_frontier, renderer_contract_digest: digest("6"),
    rendered_content_digest,
    citations: [{
      claim_lineage_id: "lineage:one", claim_revision_id: "claim:one",
      evidence_refs: ["evidence:one"],
    }],
    created_at_event_time: 20,
  });
  const payload: ProductProjectionPayload = {
    owner_account_id: "account:alice", projection_revision_id: projection.projection_revision_id,
    rendered_content_digest, payload_contract_version: "product-rendered-content-v1",
    rendered_content,
  };
  return { graph, born, projection, payload };
};

const request = <Body extends ProductProjectionWriteBody>(body: Body): Body & { request_digest: string } => ({
  ...body, request_digest: productProjectionWriteRequestDigest(body),
});

type QueryRows = Readonly<Record<string, readonly Record<string, unknown>[]>>;

class FakeConnection implements CheckedOutPostgresConnection {
  readonly connectionIdentity = Object.freeze({ client: "product-only-client" });
  readonly statements: SqlStatement[] = [];

  constructor(
    readonly authority: AuthorityStateRow,
    readonly rows: QueryRows = {},
    readonly failExecuteName: string | null = null,
    readonly failExecuteCode: string | null = null,
  ) {}

  async query<Row extends Record<string, unknown>>(statement: SqlStatement): Promise<readonly Row[]> {
    this.statements.push(statement);
    if (statement.name === "authority.set_local") return [];
    if (statement.name === "authority.lock_and_revalidate") return [this.authority as unknown as Row];
    return (this.rows[statement.name] ?? []) as readonly Row[];
  }

  async execute(statement: SqlStatement): Promise<{ rowCount: number }> {
    this.statements.push(statement);
    if (statement.name === this.failExecuteName) {
      if (this.failExecuteCode) throw Object.assign(new Error("private provider row"), { code: this.failExecuteCode });
      throw new Error("private provider row");
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
    return callback(this.connection);
  }
}

const baseRows = (): QueryRows => ({
  "product.receipt_lookup": [],
  "product.graph_head": [{ commit_id: "commit:one", sequence: "1" }],
});

describe("PostgreSQL product projection writer", () => {
  test("birth revalidates authority before replay and persists identity, membership, lineage, then receipt", async () => {
    const data = fixture();
    const connection = new FakeConnection(authorityRow(), baseRows());
    const repository = createPostgresProductProjectionWriteRepository({ pool: new FakePool(connection) });
    const outcome = await repository.append(context(), request({
      operation: "birth", graph: data.graph, identity: data.born.identity,
      membership: data.born.membership,
    }));

    expect(outcome).toEqual({ kind: "appended" });
    expect(connection.statements.map((statement) => statement.name)).toEqual([
      "authority.set_local", "authority.lock_and_revalidate", "product.receipt_lookup",
      "product.graph_head", "product.identity_insert", "product.membership_insert",
      "product.membership_lineage_insert", "product.receipt_insert",
    ]);
    expect(connection.statements.at(-1)?.values[0]).toBe("account:alice");
    expect(Object.keys(repository)).toEqual(["append"]);
  });

  test("exact receipt replays and changed bytes conflict without observing the graph or target", async () => {
    const data = fixture();
    const body = {
      operation: "birth" as const, graph: data.graph, identity: data.born.identity,
      membership: data.born.membership,
    };
    const accepted = request(body);
    const receipt = {
      request_digest: accepted.request_digest, operation: "birth",
      operation_identity: data.born.identity.proposition_id,
      graph_frontier: data.graph.graph_frontier, graph_commit_id: data.graph.graph_commit_id,
      graph_commit_sequence: "1", receipt_contract_version: "product-operation-receipt-v1",
    };
    const replayConnection = new FakeConnection(authorityRow(), { "product.receipt_lookup": [receipt] });
    const replayRepository = createPostgresProductProjectionWriteRepository({ pool: new FakePool(replayConnection) });
    await expect(replayRepository.append(context(), accepted)).resolves.toEqual({ kind: "replayed" });
    expect(replayConnection.statements.map((statement) => statement.name)).toEqual([
      "authority.set_local", "authority.lock_and_revalidate", "product.receipt_lookup",
    ]);

    const conflictConnection = new FakeConnection(authorityRow(), {
      "product.receipt_lookup": [{ ...receipt, request_digest: digest("f") }],
    });
    const conflictRepository = createPostgresProductProjectionWriteRepository({ pool: new FakePool(conflictConnection) });
    await expect(conflictRepository.append(context(), accepted)).resolves.toEqual({ kind: "idempotency_conflict" });
    expect(conflictConnection.statements.map((statement) => statement.name)).toEqual([
      "authority.set_local", "authority.lock_and_revalidate", "product.receipt_lookup",
    ]);
  });

  test("a stale graph fails before any product row mutation", async () => {
    const data = fixture();
    const rows = { ...baseRows(), "product.graph_head": [{ commit_id: "commit:new", sequence: "2" }] };
    const connection = new FakeConnection(authorityRow(), rows);
    const repository = createPostgresProductProjectionWriteRepository({ pool: new FakePool(connection) });
    await expect(repository.append(context(), request({
      operation: "birth", graph: data.graph, identity: data.born.identity,
      membership: data.born.membership,
    }))).resolves.toEqual({ kind: "stale_graph" });
    expect(connection.statements.some((statement) => statement.name.endsWith("_insert"))).toBe(false);
  });

  test("projection metadata, payload, citations, evidence, and receipt share one transaction", async () => {
    const data = fixture();
    const rows: QueryRows = {
      ...baseRows(),
      "product.identity_verify": [{ content_hash: sha256CanonicalContent(data.born.identity) }],
      "product.membership_verify": [{ content_hash: sha256CanonicalContent(data.born.membership) }],
      "product.projection_head": [],
    };
    const connection = new FakeConnection(authorityRow(), rows);
    const repository = createPostgresProductProjectionWriteRepository({ pool: new FakePool(connection) });
    await expect(repository.append(context(), request({
      operation: "projection", graph: data.graph, identity: data.born.identity,
      membership: data.born.membership, projection: data.projection, payload: data.payload,
    }))).resolves.toEqual({ kind: "appended" });
    expect(connection.statements.map((statement) => statement.name).slice(-5)).toEqual([
      "product.projection_insert", "product.payload_insert", "product.citation_insert",
      "product.citation_evidence_insert", "product.receipt_insert",
    ]);
  });

  test("later membership and disposable grouping use their closed append-only tables", async () => {
    const data = fixture();
    const membership = appendProductMembership({
      identity: data.born.identity, parent: data.born.membership,
      member_claim_lineage_ids: ["lineage:one", "lineage:two"],
      cause: "ledger_consolidation", graph_frontier: data.graph.graph_frontier,
      input_digest: digest("a"), result_digest: digest("b"), created_at_event_time: 30,
    });
    const membershipRows: QueryRows = {
      ...baseRows(),
      "product.identity_verify": [{ content_hash: sha256CanonicalContent(data.born.identity) }],
      "product.membership_head": [{
        membership_revision_id: data.born.membership.membership_revision_id,
        revision_sequence: "1", content_hash: sha256CanonicalContent(data.born.membership),
      }],
    };
    const membershipConnection = new FakeConnection(authorityRow(), membershipRows);
    const membershipRepository = createPostgresProductProjectionWriteRepository({
      pool: new FakePool(membershipConnection),
    });
    await expect(membershipRepository.append(context(), request({
      operation: "membership", graph: data.graph,
      identity: data.born.identity, membership,
    }))).resolves.toEqual({ kind: "appended" });
    expect(membershipConnection.statements.map((statement) => statement.name).slice(-4)).toEqual([
      "product.membership_insert", "product.membership_lineage_insert",
      "product.membership_lineage_insert", "product.receipt_insert",
    ]);

    const group = buildProductGroupProjection({
      owner_account_id: "account:alice",
      proposition_ids: ["proposition:one", "proposition:two"],
      input_frontier: data.graph.graph_frontier,
      projection_contract_digest: digest("c"), result_digest: digest("d"),
      created_at_event_time: 40,
    });
    const groupConnection = new FakeConnection(authorityRow(), baseRows());
    const groupRepository = createPostgresProductProjectionWriteRepository({
      pool: new FakePool(groupConnection),
    });
    await expect(groupRepository.append(context(), request({
      operation: "group", graph: data.graph, group,
    }))).resolves.toEqual({ kind: "appended" });
    expect(groupConnection.statements.map((statement) => statement.name).slice(-4)).toEqual([
      "product.group_insert", "product.group_member_insert",
      "product.group_member_insert", "product.receipt_insert",
    ]);
  });

  test("redirect cycle and dangling checks run against the persisted owner-local graph", async () => {
    const data = fixture();
    const second = birthProductProposition({
      owner_account_id: "account:alice", proposition_id: "proposition:two",
      birth_claim_lineage_id: "lineage:two", origin: "native",
      graph_frontier: data.graph.graph_frontier, input_digest: digest("7"),
      result_digest: digest("8"), created_at_event_time: 20,
    });
    const redirect = buildProductPropositionRedirect({
      owner_account_id: "account:alice", source_proposition_id: data.born.identity.proposition_id,
      successor_proposition_ids: [second.identity.proposition_id], operation: "merge",
      operation_ref: "opref1_" + digest("9"), created_at_event_time: 30,
    });
    const rows: QueryRows = {
      ...baseRows(),
      "product.redirect_propositions": [
        { proposition_id: data.born.identity.proposition_id },
        { proposition_id: second.identity.proposition_id },
      ],
      "product.redirect_edges": [{
        source_proposition_id: second.identity.proposition_id,
        successor_proposition_id: data.born.identity.proposition_id,
      }],
    };
    const connection = new FakeConnection(authorityRow(), rows);
    const repository = createPostgresProductProjectionWriteRepository({ pool: new FakePool(connection) });
    await expect(repository.append(context(), request({
      operation: "redirect", graph: data.graph, redirect,
    }))).rejects.toMatchObject({ code: "transition_invalid", message: "transition_invalid" });
    expect(connection.statements.some((statement) => statement.name === "product.redirect_insert")).toBe(false);
  });

  test("provider details remain closed and stale authority is returned before receipt lookup", async () => {
    const data = fixture();
    const failing = new FakeConnection(authorityRow(), baseRows(), "product.identity_insert");
    const repository = createPostgresProductProjectionWriteRepository({ pool: new FakePool(failing) });
    await expect(repository.append(context(), request({
      operation: "birth", graph: data.graph, identity: data.born.identity,
      membership: data.born.membership,
    }))).rejects.toMatchObject({ code: "persistence_failed", message: "persistence_failed" });

    const revoked = authorityRow({ grant_lifecycle: "revoked" });
    const deniedConnection = new FakeConnection(revoked, baseRows());
    const deniedRepository = createPostgresProductProjectionWriteRepository({ pool: new FakePool(deniedConnection) });
    await expect(deniedRepository.append(context(), request({
      operation: "birth", graph: data.graph, identity: data.born.identity,
      membership: data.born.membership,
    }))).resolves.toEqual({ kind: "authorization_denied", reason: "grant_inactive" });
    expect(deniedConnection.statements.map((statement) => statement.name)).toEqual([
      "authority.set_local", "authority.lock_and_revalidate",
    ]);
  });

  test("a concurrent immutable unique winner is a typed conflict", async () => {
    const data = fixture();
    const connection = new FakeConnection(
      authorityRow(), baseRows(), "product.receipt_insert", "23505",
    );
    const repository = createPostgresProductProjectionWriteRepository({ pool: new FakePool(connection) });
    await expect(repository.append(context(), request({
      operation: "birth", graph: data.graph, identity: data.born.identity,
      membership: data.born.membership,
    }))).resolves.toEqual({ kind: "idempotency_conflict" });
  });
});
