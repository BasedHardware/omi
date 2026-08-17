import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import {
  defineProductProjectionWriteRepository,
  type ProductProjectionWriteOutcome,
  type ProductProjectionWriteRepository,
  type ProductProjectionWriteRequest,
} from "../../apps/service/stores/product-projection-repository";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import type {
  ProductMembershipRevision,
  ProductProjectionRevision,
  ProductPropositionIdentity,
} from "../../core/retrieve/product-projection";
import type { CheckedOutPostgresConnection, PostgresTransactionPool, SqlValue } from "./connection";
import {
  PostgresRepositoryError,
  withAuthorizedSerializableConnectionTransaction,
  type PostgresTransactionObservability,
} from "./transaction";

interface ProductReceiptRow extends Record<string, unknown> {
  readonly request_digest: string;
  readonly operation: string;
  readonly operation_identity: string;
  readonly graph_frontier: string;
  readonly graph_commit_id: string;
  readonly graph_commit_sequence: string | number | bigint;
  readonly receipt_contract_version: string;
}

interface GraphHeadRow extends Record<string, unknown> {
  readonly commit_id: string | null;
  readonly sequence: string | number | bigint;
}

interface HashRow extends Record<string, unknown> {
  readonly content_hash: string;
}

interface MembershipHeadRow extends HashRow {
  readonly membership_revision_id: string;
  readonly revision_sequence: string | number | bigint;
}

interface ProjectionHeadRow extends Record<string, unknown> {
  readonly projection_revision_id: string;
  readonly projection_sequence: string | number | bigint;
}

interface RedirectEdgeRow extends Record<string, unknown> {
  readonly source_proposition_id: string;
  readonly successor_proposition_id: string;
}

const RECEIPT_VERSION = "product-operation-receipt-v1";
const MAX_REDIRECT_ROWS = 10_001;

const counter = (value: unknown): number => {
  if (typeof value === "string" && !/^(?:0|[1-9][0-9]*)$/.test(value)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  if (typeof value !== "string" && typeof value !== "number" && typeof value !== "bigint") {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 0) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return parsed;
};

const operationIdentity = (request: ProductProjectionWriteRequest): string => {
  switch (request.operation) {
    case "birth": return request.identity.proposition_id;
    case "membership": return request.membership.membership_revision_id;
    case "projection": return request.projection.projection_revision_id;
    case "redirect": return request.redirect.redirect_id;
    case "group": return request.group.group_projection_id;
  }
};

const executeOne = async (
  connection: CheckedOutPostgresConnection,
  name: string,
  text: string,
  values: readonly SqlValue[],
): Promise<void> => {
  const result = await connection.execute({ name, text, values });
  if (result.rowCount !== 1) throw new PostgresRepositoryError("persistence_failed");
};

const exactHash = async (
  connection: CheckedOutPostgresConnection,
  name: string,
  text: string,
  values: readonly SqlValue[],
  expected: string,
): Promise<void> => {
  const rows = await connection.query<HashRow>({ name, text, values });
  if (rows.length !== 1 || !rows[0] || rows[0].content_hash !== expected) {
    throw new PostgresRepositoryError("idempotency_conflict");
  }
};

const contentHash = (value: unknown): string => sha256CanonicalContent(value);

const verifyIdentity = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  identity: ProductPropositionIdentity,
): Promise<void> => exactHash(
  connection,
  "product.identity_verify",
  `SELECT content_hash
   FROM omi_memory.memory_product_propositions
   WHERE account_id = $1 AND proposition_id = $2`,
  [accountId, identity.proposition_id],
  contentHash(identity),
);

const verifyMembership = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  membership: ProductMembershipRevision,
): Promise<void> => exactHash(
  connection,
  "product.membership_verify",
  `SELECT content_hash
   FROM omi_memory.memory_product_membership_revisions
   WHERE account_id = $1 AND membership_revision_id = $2`,
  [accountId, membership.membership_revision_id],
  contentHash(membership),
);

const insertMembership = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  request: Extract<ProductProjectionWriteRequest, { operation: "birth" | "membership" | "projection" }>,
): Promise<void> => {
  const membership = request.membership;
  await executeOne(connection, "product.membership_insert", `
INSERT INTO omi_memory.memory_product_membership_revisions
  (account_id, proposition_id, membership_revision_id, revision_sequence,
   parent_membership_revision_id, cause, graph_frontier, graph_commit_id,
   graph_commit_sequence, input_digest, result_digest, created_at_event_time, content_hash)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
`, [
    accountId, membership.proposition_id, membership.membership_revision_id,
    membership.revision_sequence, membership.parent_membership_revision_id,
    membership.cause, membership.graph_frontier, request.graph.graph_commit_id,
    request.graph.graph_commit_sequence, membership.input_digest, membership.result_digest,
    membership.created_at_event_time, contentHash(membership),
  ]);
  for (let ordinal = 0; ordinal < membership.member_claim_lineage_ids.length; ordinal += 1) {
    await executeOne(connection, "product.membership_lineage_insert", `
INSERT INTO omi_memory.memory_product_membership_claim_lineages
  (account_id, membership_revision_id, member_ordinal, claim_lineage_id)
VALUES ($1, $2, $3, $4)
`, [accountId, membership.membership_revision_id, ordinal, membership.member_claim_lineage_ids[ordinal]!]);
  }
};

const persistBirth = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  request: Extract<ProductProjectionWriteRequest, { operation: "birth" }>,
): Promise<void> => {
  if (request.identity.origin !== "native") {
    throw new PostgresRepositoryError("transition_invalid");
  }
  await executeOne(connection, "product.identity_insert", `
INSERT INTO omi_memory.memory_product_propositions
  (account_id, proposition_id, product_contract_version, birth_claim_lineage_id,
   birth_commit_id, birth_commit_sequence, origin, legacy_source_id,
   created_at_event_time, content_hash)
VALUES ($1, $2, $3, $4, $5, $6, $7, NULL, $8, $9)
`, [
    accountId, request.identity.proposition_id, request.identity.version,
    request.identity.birth_claim_lineage_id, request.graph.graph_commit_id,
    request.graph.graph_commit_sequence, request.identity.origin,
    request.identity.created_at_event_time, contentHash(request.identity),
  ]);
  await insertMembership(connection, accountId, request);
};

const persistMembership = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  request: Extract<ProductProjectionWriteRequest, { operation: "membership" }>,
): Promise<void> => {
  await verifyIdentity(connection, accountId, request.identity);
  const heads = await connection.query<MembershipHeadRow>({
    name: "product.membership_head",
    text: `SELECT membership_revision_id, revision_sequence, content_hash
           FROM omi_memory.memory_product_membership_revisions
           WHERE account_id = $1 AND proposition_id = $2
           ORDER BY revision_sequence DESC, membership_revision_id DESC LIMIT 1`,
    values: [accountId, request.identity.proposition_id],
  });
  const head = heads[0];
  if (heads.length !== 1 || !head
    || request.membership.parent_membership_revision_id !== head.membership_revision_id
    || request.membership.revision_sequence !== counter(head.revision_sequence) + 1) {
    throw new PostgresRepositoryError("stale_parent");
  }
  await insertMembership(connection, accountId, request);
};

const persistProjection = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  request: Extract<ProductProjectionWriteRequest, { operation: "projection" }>,
): Promise<void> => {
  await verifyIdentity(connection, accountId, request.identity);
  await verifyMembership(connection, accountId, request.membership);
  const heads = await connection.query<ProjectionHeadRow>({
    name: "product.projection_head",
    text: `SELECT projection_revision_id, projection_sequence
           FROM omi_memory.memory_product_projection_revisions
           WHERE account_id = $1 AND proposition_id = $2
           ORDER BY projection_sequence DESC, projection_revision_id DESC LIMIT 1`,
    values: [accountId, request.identity.proposition_id],
  });
  const expectedSequence = heads.length === 0 ? 1 : counter(heads[0]!.projection_sequence) + 1;
  if (heads.length > 1 || request.projection.projection_sequence !== expectedSequence) {
    throw new PostgresRepositoryError("stale_parent");
  }
  const projection = request.projection;
  await executeOne(connection, "product.projection_insert", `
INSERT INTO omi_memory.memory_product_projection_revisions
  (account_id, proposition_id, projection_revision_id, projection_sequence,
   membership_revision_id, graph_frontier, graph_commit_id, graph_commit_sequence,
   renderer_contract_digest, rendered_content_digest, created_at_event_time, content_hash)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
`, [
    accountId, projection.proposition_id, projection.projection_revision_id,
    projection.projection_sequence, projection.membership_revision_id,
    projection.graph_frontier, request.graph.graph_commit_id,
    request.graph.graph_commit_sequence, projection.renderer_contract_digest,
    projection.rendered_content_digest, projection.created_at_event_time,
    contentHash(projection),
  ]);
  await executeOne(connection, "product.payload_insert", `
INSERT INTO omi_memory.memory_product_projection_payloads
  (account_id, projection_revision_id, rendered_content_digest,
   payload_contract_version, rendered_content_json, content_hash)
VALUES ($1, $2, $3, $4, ($5::text)::jsonb, $6)
`, [
    accountId, projection.projection_revision_id, request.payload.rendered_content_digest,
    request.payload.payload_contract_version, JSON.stringify(request.payload.rendered_content),
    contentHash(request.payload),
  ]);
  for (let citationOrdinal = 0; citationOrdinal < projection.citations.length; citationOrdinal += 1) {
    const citation = projection.citations[citationOrdinal]!;
    await executeOne(connection, "product.citation_insert", `
INSERT INTO omi_memory.memory_product_projection_citations
  (account_id, projection_revision_id, membership_revision_id, citation_ordinal,
   claim_lineage_id, claim_revision_id)
VALUES ($1, $2, $3, $4, $5, $6)
`, [
      accountId, projection.projection_revision_id, projection.membership_revision_id,
      citationOrdinal, citation.claim_lineage_id, citation.claim_revision_id,
    ]);
    for (let evidenceOrdinal = 0; evidenceOrdinal < citation.evidence_refs.length; evidenceOrdinal += 1) {
      await executeOne(connection, "product.citation_evidence_insert", `
INSERT INTO omi_memory.memory_product_projection_citation_evidence_refs
  (account_id, projection_revision_id, citation_ordinal, evidence_ordinal,
   claim_revision_id, evidence_id)
VALUES ($1, $2, $3, $4, $5, $6)
`, [
        accountId, projection.projection_revision_id, citationOrdinal, evidenceOrdinal,
        citation.claim_revision_id, citation.evidence_refs[evidenceOrdinal]!,
      ]);
    }
  }
};

const assertRedirectGraph = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  source: string,
  successors: readonly string[],
): Promise<void> => {
  const propositionRows = await connection.query<{ proposition_id: string }>({
    name: "product.redirect_propositions",
    text: `SELECT proposition_id FROM omi_memory.memory_product_propositions
           WHERE account_id = $1 ORDER BY proposition_id LIMIT ${MAX_REDIRECT_ROWS}`,
    values: [accountId],
  });
  if (propositionRows.length >= MAX_REDIRECT_ROWS) throw new PostgresRepositoryError("transition_invalid");
  const known = new Set(propositionRows.map((row) => row.proposition_id));
  if (!known.has(source) || successors.some((id) => !known.has(id))) {
    throw new PostgresRepositoryError("transition_invalid");
  }
  const rows = await connection.query<RedirectEdgeRow>({
    name: "product.redirect_edges",
    text: `SELECT r.source_proposition_id, s.successor_proposition_id
           FROM omi_memory.memory_product_redirects AS r
           JOIN omi_memory.memory_product_redirect_successors AS s
             ON s.account_id = r.account_id AND s.redirect_id = r.redirect_id
           WHERE r.account_id = $1
           ORDER BY r.source_proposition_id, s.successor_ordinal
           LIMIT ${MAX_REDIRECT_ROWS}`,
    values: [accountId],
  });
  if (rows.length >= MAX_REDIRECT_ROWS) throw new PostgresRepositoryError("transition_invalid");
  const edges = new Map<string, string[]>();
  for (const row of rows) {
    const list = edges.get(row.source_proposition_id) ?? [];
    list.push(row.successor_proposition_id);
    edges.set(row.source_proposition_id, list);
  }
  if (edges.has(source)) throw new PostgresRepositoryError("idempotency_conflict");
  edges.set(source, [...successors]);
  const visiting = new Set<string>();
  const visited = new Set<string>();
  const walk = (id: string, depth: number): void => {
    if (depth > 64 || visiting.has(id)) throw new PostgresRepositoryError("transition_invalid");
    if (visited.has(id)) return;
    visiting.add(id);
    for (const successor of edges.get(id) ?? []) walk(successor, depth + 1);
    visiting.delete(id);
    visited.add(id);
  };
  for (const id of edges.keys()) walk(id, 0);
};

const persistRedirect = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  request: Extract<ProductProjectionWriteRequest, { operation: "redirect" }>,
): Promise<void> => {
  const redirect = request.redirect;
  await assertRedirectGraph(
    connection, accountId, redirect.source_proposition_id, redirect.successor_proposition_ids,
  );
  await executeOne(connection, "product.redirect_insert", `
INSERT INTO omi_memory.memory_product_redirects
  (account_id, redirect_id, source_proposition_id, operation, operation_ref,
   created_at_event_time, content_hash)
VALUES ($1, $2, $3, $4, $5, $6, $7)
`, [
    accountId, redirect.redirect_id, redirect.source_proposition_id, redirect.operation,
    redirect.operation_ref, redirect.created_at_event_time, contentHash(redirect),
  ]);
  for (let ordinal = 0; ordinal < redirect.successor_proposition_ids.length; ordinal += 1) {
    await executeOne(connection, "product.redirect_successor_insert", `
INSERT INTO omi_memory.memory_product_redirect_successors
  (account_id, redirect_id, successor_ordinal, source_proposition_id, successor_proposition_id)
VALUES ($1, $2, $3, $4, $5)
`, [
      accountId, redirect.redirect_id, ordinal, redirect.source_proposition_id,
      redirect.successor_proposition_ids[ordinal]!,
    ]);
  }
};

const persistGroup = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  request: Extract<ProductProjectionWriteRequest, { operation: "group" }>,
): Promise<void> => {
  const group = request.group;
  await executeOne(connection, "product.group_insert", `
INSERT INTO omi_memory.memory_product_group_projections
  (account_id, group_projection_id, input_frontier, graph_commit_id,
   graph_commit_sequence, projection_contract_digest, result_digest,
   created_at_event_time, content_hash)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
`, [
    accountId, group.group_projection_id, group.input_frontier,
    request.graph.graph_commit_id, request.graph.graph_commit_sequence,
    group.projection_contract_digest, group.result_digest,
    group.created_at_event_time, contentHash(group),
  ]);
  for (let ordinal = 0; ordinal < group.proposition_ids.length; ordinal += 1) {
    await executeOne(connection, "product.group_member_insert", `
INSERT INTO omi_memory.memory_product_group_members
  (account_id, group_projection_id, member_ordinal, proposition_id)
VALUES ($1, $2, $3, $4)
`, [accountId, group.group_projection_id, ordinal, group.proposition_ids[ordinal]!]);
  }
};

const replayOrConflict = (
  rows: readonly ProductReceiptRow[],
  request: ProductProjectionWriteRequest,
  identity: string,
): ProductProjectionWriteOutcome | null => {
  if (rows.length === 0) return null;
  if (rows.length !== 1 || !rows[0]) throw new PostgresRepositoryError("persistence_failed");
  const row = rows[0];
  if (row.request_digest !== request.request_digest
    || row.operation !== request.operation
    || row.operation_identity !== identity) {
    return Object.freeze({ kind: "idempotency_conflict" as const });
  }
  if (row.graph_frontier !== request.graph.graph_frontier
    || row.graph_commit_id !== request.graph.graph_commit_id
    || counter(row.graph_commit_sequence) !== request.graph.graph_commit_sequence
    || row.receipt_contract_version !== RECEIPT_VERSION) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return Object.freeze({ kind: "replayed" as const });
};

const appendWithinTransaction = async (
  connection: CheckedOutPostgresConnection,
  context: AuthorizedLedgerWriteContext,
  request: ProductProjectionWriteRequest,
): Promise<ProductProjectionWriteOutcome> => {
  const accountId = context.account_id;
  const identity = operationIdentity(request);
  const receipts = await connection.query<ProductReceiptRow>({
    name: "product.receipt_lookup",
    text: `SELECT request_digest, operation, operation_identity, graph_frontier,
                  graph_commit_id, graph_commit_sequence, receipt_contract_version
           FROM omi_memory.memory_product_operation_receipts
           WHERE account_id = $1
             AND (request_digest = $2 OR (operation = $3 AND operation_identity = $4))
           `,
    values: [accountId, request.request_digest, request.operation, identity],
  });
  const prior = replayOrConflict(receipts, request, identity);
  if (prior) return prior;

  const heads = await connection.query<GraphHeadRow>({
    name: "product.graph_head",
    text: `SELECT commit_id, sequence FROM omi_memory.memory_graph_heads
           WHERE account_id = $1 FOR SHARE`,
    values: [accountId],
  });
  const head = heads[0];
  if (heads.length !== 1 || !head
    || head.commit_id !== request.graph.graph_commit_id
    || counter(head.sequence) !== request.graph.graph_commit_sequence) {
    throw new PostgresRepositoryError("stale_parent");
  }

  switch (request.operation) {
    case "birth": await persistBirth(connection, accountId, request); break;
    case "membership": await persistMembership(connection, accountId, request); break;
    case "projection": await persistProjection(connection, accountId, request); break;
    case "redirect": await persistRedirect(connection, accountId, request); break;
    case "group": await persistGroup(connection, accountId, request); break;
  }
  await executeOne(connection, "product.receipt_insert", `
INSERT INTO omi_memory.memory_product_operation_receipts
  (account_id, request_digest, operation, operation_identity, graph_frontier,
   graph_commit_id, graph_commit_sequence, receipt_contract_version)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
`, [
    accountId, request.request_digest, request.operation, identity,
    request.graph.graph_frontier, request.graph.graph_commit_id,
    request.graph.graph_commit_sequence, RECEIPT_VERSION,
  ]);
  return Object.freeze({ kind: "appended" as const });
};

const providerCode = (error: unknown): string | undefined => {
  if (!error || typeof error !== "object") return undefined;
  const code = Reflect.get(error, "code");
  return typeof code === "string" ? code : undefined;
};

const append = async (
  pool: PostgresTransactionPool,
  context: AuthorizedLedgerWriteContext,
  request: ProductProjectionWriteRequest,
  observability: PostgresTransactionObservability,
): Promise<ProductProjectionWriteOutcome> => {
  try {
    return await withAuthorizedSerializableConnectionTransaction(
      pool,
      context,
      async ({ authority, connection }) => {
        try {
          return await appendWithinTransaction(connection, authority, request);
        } catch (error) {
          if (providerCode(error) === "23505") {
            throw new PostgresRepositoryError("idempotency_conflict");
          }
          throw error;
        }
      },
      observability,
    );
  } catch (error) {
    if (!(error instanceof PostgresRepositoryError)) throw error;
    switch (error.code) {
      case "expired_context":
      case "stale_epoch":
      case "destination_inactive":
      case "lifecycle_inactive":
        return Object.freeze({ kind: "stale_context" as const, reason: error.code });
      case "credential_inactive":
      case "grant_inactive":
      case "capability_denied":
        return Object.freeze({ kind: "authorization_denied" as const, reason: error.code });
      case "idempotency_conflict":
        return Object.freeze({ kind: "idempotency_conflict" as const });
      case "stale_parent":
        return Object.freeze({ kind: "stale_graph" as const });
      case "retryable_serialization":
        return Object.freeze({ kind: "serialization_retryable" as const });
      default:
        throw error;
    }
  }
};

export interface PostgresProductProjectionRepositoryOptions {
  readonly pool: PostgresTransactionPool;
  readonly observability?: PostgresTransactionObservability;
}

/**
 * Inert named-operation product projection writer. It revalidates projector
 * authority before replay, binds every operation to the exact current graph
 * commit, and exposes no SQL capability or route composition.
 */
export const createPostgresProductProjectionWriteRepository = (
  options: PostgresProductProjectionRepositoryOptions,
): ProductProjectionWriteRepository => defineProductProjectionWriteRepository(
  (context, request) => append(options.pool, context, request, options.observability ?? {}),
);
