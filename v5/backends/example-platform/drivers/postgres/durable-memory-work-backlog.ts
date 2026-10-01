import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import {
  DURABLE_MEMORY_BACKLOG_WORK_KINDS,
  defineDurableMemoryWorkBacklogSource,
  type DurableMemoryWorkBacklogSource,
} from "../../apps/service/observability/durable-memory-work-backlog";
import type { PostgresTransactionPool } from "./connection";
import {
  PostgresRepositoryError,
  type PostgresTransactionObservability,
  withAuthorizedSerializableConnectionTransaction,
} from "./transaction";

interface BacklogRow extends Record<string, unknown> {
  readonly work_kind: string;
  readonly ready: number | string | bigint;
  readonly leased: number | string | bigint;
  readonly retry_wait: number | string | bigint;
  readonly dead: number | string | bigint;
  readonly oldest_ready_event_time: number | string | bigint | null;
}

const ROW_KEYS = [
  "work_kind", "ready", "leased", "retry_wait", "dead", "oldest_ready_event_time",
] as const;
const MAX_COUNT = 1_000_000_000;
const MAX_AGE_MS = 86_400_000;

const integer = (value: unknown, maximum: number): number => {
  if (typeof value !== "number" && typeof value !== "string" && typeof value !== "bigint") {
    throw new PostgresRepositoryError("persistence_failed");
  }
  if (typeof value === "string" && !/^(?:0|[1-9][0-9]*)$/.test(value)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const normalized = Number(value);
  if (!Number.isSafeInteger(normalized) || normalized < 0 || normalized > maximum) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return normalized;
};

const exactRow = (row: BacklogRow): void => {
  const keys = Object.keys(row).sort();
  const expected = [...ROW_KEYS].sort();
  if (keys.length !== expected.length || keys.some((key, index) => key !== expected[index])) {
    throw new PostgresRepositoryError("persistence_failed");
  }
};

const ageMilliseconds = (now: number, oldest: unknown, ready: number): number | null => {
  if (oldest === null && ready === 0) return null;
  if (oldest === null || ready === 0) throw new PostgresRepositoryError("persistence_failed");
  const eventTime = integer(oldest, Number.MAX_SAFE_INTEGER);
  if (eventTime > now) throw new PostgresRepositoryError("persistence_failed");
  const seconds = now - eventTime;
  if (!Number.isSafeInteger(seconds)) throw new PostgresRepositoryError("persistence_failed");
  return Math.min(seconds * 1_000, MAX_AGE_MS);
};

const snapshot = async (
  pool: PostgresTransactionPool,
  context: AuthorizedLedgerWriteContext,
  observability: PostgresTransactionObservability,
): Promise<unknown> => withAuthorizedSerializableConnectionTransaction(
  pool,
  context,
  async ({ authority, connection, dbNowEpochSeconds }) => {
    const rows = await connection.query<BacklogRow>({
      name: "work.backlog.coherent_snapshot",
      text: `
WITH work_kinds(work_kind, ordinal) AS (
  VALUES
    ('formation'::text, 1),
    ('promotion'::text, 2),
    ('identity_cluster'::text, 3),
    ('predicate_batch'::text, 4)
)
SELECT
  k.work_kind,
  count(a.job_id) FILTER (WHERE
    (s.state = 'pending' AND a.accepted_at_event_time <= $3)
    OR (s.state = 'retryable_failed' AND s.next_eligible_event_time <= $3)
  )::bigint AS ready,
  count(a.job_id) FILTER (WHERE s.state = 'leased')::bigint AS leased,
  count(a.job_id) FILTER (WHERE
    (s.state = 'pending' AND a.accepted_at_event_time > $3)
    OR (s.state = 'retryable_failed' AND s.next_eligible_event_time > $3)
  )::bigint AS retry_wait,
  count(a.job_id) FILTER (WHERE s.state = 'dead_letter')::bigint AS dead,
  min(a.accepted_at_event_time) FILTER (WHERE
    (s.state = 'pending' AND a.accepted_at_event_time <= $3)
    OR (s.state = 'retryable_failed' AND s.next_eligible_event_time <= $3)
  ) AS oldest_ready_event_time
FROM work_kinds AS k
LEFT JOIN omi_memory.memory_work_acceptances AS a
  ON a.account_id = $1 AND a.account_epoch = $2 AND a.work_kind = k.work_kind
LEFT JOIN omi_memory.memory_work_heads AS h
  ON h.account_id = a.account_id AND h.job_id = a.job_id
LEFT JOIN omi_memory.memory_work_state_revisions AS s
  ON s.account_id = h.account_id AND s.job_id = h.job_id
 AND s.state_revision = h.state_revision AND s.state_digest = h.state_digest
GROUP BY k.work_kind, k.ordinal
ORDER BY k.ordinal
`,
      values: [authority.account_id, authority.account_epoch, dbNowEpochSeconds],
    });
    if (rows.length !== DURABLE_MEMORY_BACKLOG_WORK_KINDS.length) {
      throw new PostgresRepositoryError("persistence_failed");
    }
    const normalized = rows.map((row, index) => {
      exactRow(row);
      const expectedKind = DURABLE_MEMORY_BACKLOG_WORK_KINDS[index];
      if (!expectedKind || row.work_kind !== expectedKind) {
        throw new PostgresRepositoryError("persistence_failed");
      }
      const ready = integer(row.ready, MAX_COUNT);
      return Object.freeze({
        work_kind: expectedKind,
        ready,
        leased: integer(row.leased, MAX_COUNT),
        retry_wait: integer(row.retry_wait, MAX_COUNT),
        dead: integer(row.dead, MAX_COUNT),
        oldest_ready_age_ms: ageMilliseconds(
          dbNowEpochSeconds, row.oldest_ready_event_time, ready,
        ),
      });
    });
    return Object.freeze({
      version: "durable-memory-work-backlog-snapshot-v1" as const,
      rows: Object.freeze(normalized),
    });
  },
  observability,
);

export interface PostgresDurableMemoryWorkBacklogOptions {
  readonly pool: PostgresTransactionPool;
  readonly observability?: PostgresTransactionObservability;
}

/** Route-free, account-scoped, authority-checked coherent backlog source. */
export const createPostgresDurableMemoryWorkBacklogSource = (
  options: PostgresDurableMemoryWorkBacklogOptions,
): DurableMemoryWorkBacklogSource => defineDurableMemoryWorkBacklogSource(
  (context) => snapshot(options.pool, context, options.observability ?? {}),
);
