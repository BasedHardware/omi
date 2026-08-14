import {
  parseAttributionBeliefRevision,
  type AttributionBeliefRevision,
} from "../../core/consolidate/attribution-belief";
import {
  PRODUCT_PROJECTION_CONTRACT_VERSION,
  parseProductGroupProjection,
  type ProductGroupProjection,
} from "../../core/retrieve/product-projection";
import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import type { CheckedOutPostgresConnection, PostgresTransactionPool } from "./connection";
import {
  PostgresRepositoryError,
  type PostgresTransactionObservability,
  withAuthorizedSerializableConnectionTransaction,
} from "./transaction";

const READ_PORT: unique symbol = Symbol("postgres-derived-group-recall-read");

const MAX_GROUPS = 256;
const MAX_BELIEFS = 256;

interface GroupRow extends Record<string, unknown> {
  readonly account_id: string;
  readonly group_projection_id: string;
  readonly input_frontier: string;
  readonly projection_contract_digest: string;
  readonly result_digest: string;
  readonly created_at_event_time: number | string | bigint;
  readonly content_hash: string;
  readonly proposition_ids: readonly string[];
}

interface BeliefRow extends Record<string, unknown> {
  readonly account_id: string;
  readonly belief_revision_id: string;
  readonly belief_lineage_id: string;
  readonly belief_kind: string;
  readonly graph_frontier: string;
  readonly revision_contract_version: string;
  readonly revision_json: unknown;
  readonly content_hash: string;
}

const GROUP_KEYS = [
  "account_id", "group_projection_id", "input_frontier", "projection_contract_digest",
  "result_digest", "created_at_event_time", "content_hash", "proposition_ids",
] as const;
const BELIEF_KEYS = [
  "account_id", "belief_revision_id", "belief_lineage_id", "belief_kind",
  "graph_frontier", "revision_contract_version", "revision_json", "content_hash",
] as const;

const exactKeys = (value: Record<string, unknown>, expected: readonly string[]): void => {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    throw new PostgresRepositoryError("persistence_failed");
  }
};

const integer = (value: unknown): number => {
  if (typeof value !== "number" && typeof value !== "string" && typeof value !== "bigint") {
    throw new PostgresRepositoryError("persistence_failed");
  }
  if (typeof value === "string" && !/^(?:0|[1-9][0-9]*)$/.test(value)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const result = Number(value);
  if (!Number.isSafeInteger(result) || result < 0) throw new PostgresRepositoryError("persistence_failed");
  return result;
};

/**
 * Rebuild the exact `ProductGroupProjection` from persisted columns plus
 * ordinal-ordered members. `parseProductGroupProjection` recomputes the
 * content-addressed `group_projection_id`, so a row that does not rebuild to
 * the identifier it was stored under fails closed rather than answering.
 */
const parseGroupRow = (row: GroupRow, accountId: string): ProductGroupProjection => {
  exactKeys(row, GROUP_KEYS);
  if (row.account_id !== accountId) throw new PostgresRepositoryError("persistence_failed");
  if (!Array.isArray(row.proposition_ids)) throw new PostgresRepositoryError("persistence_failed");
  if (row.content_hash !== row.result_digest) throw new PostgresRepositoryError("persistence_failed");
  let group: ProductGroupProjection;
  try {
    group = parseProductGroupProjection({
      version: PRODUCT_PROJECTION_CONTRACT_VERSION,
      owner_account_id: row.account_id,
      group_projection_id: row.group_projection_id,
      proposition_ids: row.proposition_ids,
      input_frontier: row.input_frontier,
      projection_contract_digest: row.projection_contract_digest,
      result_digest: row.result_digest,
      created_at_event_time: integer(row.created_at_event_time),
    });
  } catch {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return group;
};

const parseBeliefRow = (row: BeliefRow, accountId: string): AttributionBeliefRevision => {
  exactKeys(row, BELIEF_KEYS);
  if (row.account_id !== accountId
    || row.revision_contract_version !== "attribution-belief-v1") {
    throw new PostgresRepositoryError("persistence_failed");
  }
  let belief: AttributionBeliefRevision;
  try {
    belief = parseAttributionBeliefRevision(row.revision_json);
  } catch {
    throw new PostgresRepositoryError("persistence_failed");
  }
  /**
   * Bind the belief's own owner to the reading tenant. The revision id is
   * content-addressed over `owner_account_id`, so a bare edit of the JSON
   * already fails — but that check validates the payload against itself, not
   * against the column it was stored under. Without this line an internally
   * consistent belief owned by another account, filed under this one, would be
   * returned as valid. The group path gets this for free by feeding
   * `row.account_id` into the id recomputation; beliefs need it stated.
   */
  if (belief.owner_account_id !== accountId
    || belief.belief_revision_id !== row.belief_revision_id
    || belief.belief_lineage_id !== row.belief_lineage_id
    || belief.belief_kind !== row.belief_kind
    || belief.graph_frontier !== row.graph_frontier
    || belief.observation_content_digest !== row.content_hash) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return belief;
};

export type DerivedGroupProjectionLoadOutcome =
  | Readonly<{ kind: "found"; groups: readonly ProductGroupProjection[] }>
  | Readonly<{ kind: "stale_context"; reason: string }>
  | Readonly<{ kind: "authorization_denied"; reason: string }>
  | Readonly<{ kind: "serialization_retryable" }>;

export type AttributionBeliefLoadOutcome =
  | Readonly<{ kind: "found"; beliefs: readonly AttributionBeliefRevision[] }>
  | Readonly<{ kind: "stale_context"; reason: string }>
  | Readonly<{ kind: "authorization_denied"; reason: string }>
  | Readonly<{ kind: "serialization_retryable" }>;

const commonFailure = (error: unknown): unknown => {
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
    case "retryable_serialization":
      return Object.freeze({ kind: "serialization_retryable" as const });
    default:
      throw error;
  }
};

export interface PostgresDerivedGroupRecallRead {
  readonly [READ_PORT]: true;
  loadGroupProjections(
    context: AuthorizedLedgerWriteContext,
  ): Promise<DerivedGroupProjectionLoadOutcome>;
  loadAttributionBeliefs(
    context: AuthorizedLedgerWriteContext,
  ): Promise<AttributionBeliefLoadOutcome>;
}

export interface PostgresDerivedGroupRecallReadOptions {
  readonly pool: PostgresTransactionPool;
  readonly observability?: PostgresTransactionObservability;
}

/**
 * Ask PostgreSQL for one row more than we can accept, so overflow is detected
 * without transferring an unbounded result set, and fail closed on it.
 *
 * Returning the first `MAX` rows instead would let recall answer from a
 * silently partial group set, which is worse than refusing: the product owes a
 * grounded answer with typed completeness, not a confident subset. Paging this
 * honestly (a declared `truncated` signal the kernel can turn into stated
 * incompleteness) is the follow-up; it is a contract change, not a patch.
 */
const readGroups = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
): Promise<readonly ProductGroupProjection[]> => {
  const rows = await connection.query<GroupRow>({
    name: "derived-group-recall.groups.read",
    text: "SELECT * FROM omi_memory.read_derived_group_projections($1, $2)",
    values: [accountId, MAX_GROUPS + 1],
  });
  if (rows.length > MAX_GROUPS) throw new PostgresRepositoryError("persistence_failed");
  return Object.freeze(rows.map((row) => parseGroupRow(row, accountId)));
};

const readBeliefs = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
): Promise<readonly AttributionBeliefRevision[]> => {
  const rows = await connection.query<BeliefRow>({
    name: "derived-group-recall.beliefs.read",
    text: "SELECT * FROM omi_memory.read_attribution_belief_revisions($1, $2)",
    values: [accountId, MAX_BELIEFS + 1],
  });
  if (rows.length > MAX_BELIEFS) throw new PostgresRepositoryError("persistence_failed");
  return Object.freeze(rows.map((row) => parseBeliefRow(row, accountId)));
};

/**
 * Owner-scoped read seam over already-committed dream output.
 *
 * It opens no route, mints no authority, and observes only rows the dream
 * success transaction already wrote. Recall composition must supply a
 * separately issued `memories.read` context; the SQL definer functions reject
 * every other capability.
 */
export const createPostgresDerivedGroupRecallRead = (
  options: PostgresDerivedGroupRecallReadOptions,
): PostgresDerivedGroupRecallRead => {
  const observability = options.observability ?? {};
  return Object.freeze({
    [READ_PORT]: true as const,
    async loadGroupProjections(context: AuthorizedLedgerWriteContext) {
      try {
        return await withAuthorizedSerializableConnectionTransaction(
          options.pool,
          context,
          async ({ authority, connection }) => Object.freeze({
            kind: "found" as const,
            groups: await readGroups(connection, authority.account_id),
          }),
          observability,
        );
      } catch (error) {
        return commonFailure(error) as DerivedGroupProjectionLoadOutcome;
      }
    },
    async loadAttributionBeliefs(context: AuthorizedLedgerWriteContext) {
      try {
        return await withAuthorizedSerializableConnectionTransaction(
          options.pool,
          context,
          async ({ authority, connection }) => Object.freeze({
            kind: "found" as const,
            beliefs: await readBeliefs(connection, authority.account_id),
          }),
          observability,
        );
      } catch (error) {
        return commonFailure(error) as AttributionBeliefLoadOutcome;
      }
    },
  });
};
