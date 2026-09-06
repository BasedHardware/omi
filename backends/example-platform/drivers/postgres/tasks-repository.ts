import { createHash } from "node:crypto";
import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import type { PostgresTransactionPool } from "./connection";
import type { PreservedEnvelope } from "../../apps/service/stores/straggler-table";
import { withAuthorizedSerializableConnectionTransaction } from "./transaction";
import { defineWriteUnitOfWork } from "../../apps/service/stores/write-unit-of-work";
import { createUnitOfWorkContext } from "../../apps/service/stores/unit-of-work-context";
import {
  computeTasksRevision,
  tasksPreconditionHolds,
  type TasksRecord,
  type TasksReadStore,
} from "../../apps/service/stores/tasks-store";
import {
  stableSerialize,
  type RecordedWriteOutcome,
} from "../../apps/service/stores/write-id-registry";
import type { CheckedOutPostgresConnection } from "./connection";

interface StoredTask {
  record_id: string;
  revision: string;
  content_json: string | null;
  first_seen_seq: number;
  last_applied_seq: number;
}
const safeSequence = (value: unknown): number => {
  const number = Number(value);
  if (!Number.isSafeInteger(number) || number < 0)
    throw Error("task_sequence_unavailable");
  return number;
};
async function loadPostgresTasks(
  connection: CheckedOutPostgresConnection,
  accountId: string
) {
  const rows = await connection.query({
    name: "tasks.snapshot",
    text: "SELECT record_id,revision,content_json,first_seen_seq,last_applied_seq FROM omi_memory.task_records WHERE account_id=$1 ORDER BY first_seen_seq,record_id LIMIT 10001",
    values: [accountId],
  });
  if (rows.length > 10000) throw Error("task_capacity_unavailable");
  const stored = new Map<string, StoredTask>();
  for (const row of rows) {
    if (
      typeof row.record_id !== "string" ||
      typeof row.revision !== "string" ||
      !/^[a-f0-9]{64}$/.test(row.revision) ||
      !(row.content_json === null || typeof row.content_json === "string")
    )
      throw Error("task_snapshot_unavailable");
    stored.set(row.record_id, {
      record_id: row.record_id,
      revision: row.revision,
      content_json: row.content_json,
      first_seen_seq: safeSequence(row.first_seen_seq),
      last_applied_seq: safeSequence(row.last_applied_seq),
    });
  }
  const live = (row: StoredTask): TasksRecord | null =>
    row.content_json === null
      ? null
      : {
          record_id: row.record_id,
          revision: row.revision,
          content: JSON.parse(row.content_json),
          first_seen_seq: row.first_seen_seq,
          last_applied_seq: row.last_applied_seq,
        };
  const store: TasksReadStore = {
    listRecords(owner) {
      if (owner !== accountId) throw Error("task_owner_mismatch");
      return [...stored.values()].flatMap((row) => {
        const record = live(row);
        return record ? [record] : [];
      });
    },
    readRecord(owner, id) {
      if (owner !== accountId) throw Error("task_owner_mismatch");
      const row = stored.get(id);
      return row ? live(row) : null;
    },
  };
  const state = {
    receipt: undefined as Record<string, unknown> | undefined,
    next: undefined as StoredTask | undefined,
    outcome: undefined as RecordedWriteOutcome | undefined,
    sequence: 0,
    failed: false,
  };
  const unitOfWork = defineWriteUnitOfWork<typeof state>(
    {
      async execute(input, operation) {
        try {
          if (input.accountId !== accountId) throw Error("task_owner_mismatch");
          const receipts = await connection.query({
            name: "tasks.receipt",
            text: "SELECT fingerprint,outcome_json FROM omi_memory.task_write_receipts WHERE account_id=$1 AND write_id=$2",
            values: [accountId, input.writeId],
          });
          state.receipt = receipts[0];
          state.next = undefined;
          state.outcome = undefined;
          const sequences = await connection.query({
            name: "tasks.sequence",
            text: "SELECT sequence FROM omi_memory.task_sequences WHERE account_id=$1",
            values: [accountId],
          });
          state.sequence = safeSequence(sequences[0]?.sequence ?? 0);
          const context = createUnitOfWorkContext(state);
          const result = operation(context);
          const appliedState = (() => ({ ...state }))();
          if (appliedState.outcome) {
            if (appliedState.next)
              await connection.execute({
                name: "tasks.persist",
                text: "INSERT INTO omi_memory.task_records (account_id,record_id,revision,content_json,first_seen_seq,last_applied_seq) VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT(account_id,record_id) DO UPDATE SET revision=EXCLUDED.revision,content_json=EXCLUDED.content_json,last_applied_seq=EXCLUDED.last_applied_seq",
                values: [
                  accountId,
                  appliedState.next.record_id,
                  appliedState.next.revision,
                  appliedState.next.content_json,
                  appliedState.next.first_seen_seq,
                  appliedState.next.last_applied_seq,
                ],
              });
            await connection.execute({
              name: "tasks.advance",
              text: "INSERT INTO omi_memory.task_sequences(account_id,sequence) VALUES ($1,$2) ON CONFLICT(account_id) DO UPDATE SET sequence=EXCLUDED.sequence",
              values: [accountId, state.sequence],
            });
            await connection.execute({
              name: "tasks.record_receipt",
              text: "INSERT INTO omi_memory.task_write_receipts(account_id,write_id,account_epoch,fingerprint,outcome_json) VALUES ($1,$2,$3,$4,$5)",
              values: [
                accountId,
                input.writeId,
                input.accountEpoch,
                stableSerialize(input.fingerprintOf),
                JSON.stringify(appliedState.outcome),
              ],
            });
          }
          return result;
        } catch (error) {
          state.failed = true;
          throw error;
        }
      },
    },
    {
      lookup(context, input) {
        return context.perform(state, () => {
          if (!state.receipt) return { kind: "fresh" as const };
          if (
            state.receipt.fingerprint !== stableSerialize(input.fingerprintOf)
          )
            return { kind: "reuse" as const };
          if (typeof state.receipt.outcome_json !== "string")
            throw Error("task_receipt_unavailable");
          return {
            kind: "replay" as const,
            outcome: JSON.parse(
              state.receipt.outcome_json
            ) as RecordedWriteOutcome,
          };
        });
      },
      apply(context, input) {
        return context.perform(state, () => {
          const op = input.op;
          const prior = stored.get(op.record_id);
          const current = prior ? live(prior) ?? undefined : undefined;
          if (
            op.op !== "create" &&
            !tasksPreconditionHolds(current, op.base_revision)
          )
            return { applied: false as const, reason: "conflict" as const };
          if (op.op === "delete") {
            if (prior && current) state.next = { ...prior, content_json: null };
            return {
              applied: true as const,
              record_id: op.record_id,
              revision: null,
            };
          }
          if (!prior && stored.size >= 10000)
            throw Error("task_capacity_unavailable");
          state.sequence = safeSequence(state.sequence + 1);
          const content =
            op.op === "create"
              ? op.content
              : { ...(current?.content ?? {}), ...op.patch };
          const revision = computeTasksRevision(
            prior?.revision ?? null,
            op.record_id,
            content
          );
          state.next = {
            record_id: op.record_id,
            revision,
            content_json: JSON.stringify(content),
            first_seen_seq: prior?.first_seen_seq ?? state.sequence,
            last_applied_seq: state.sequence,
          };
          return { applied: true as const, record_id: op.record_id, revision };
        });
      },
      record(context, input, outcome) {
        return context.perform(state, () => {
          state.outcome = outcome;
        });
      },
    }
  );
  return {
    store,
    unitOfWork,
    assertHealthy() {
      if (state.failed) throw Error("task_transaction_failed");
    },
  };
}

export async function withAuthorizedTasks<Result>(
  pool: PostgresTransactionPool,
  authority: AuthorizedLedgerWriteContext,
  signal: AbortSignal,
  operation: (
    snapshot: Awaited<ReturnType<typeof loadPostgresTasks>> & {
      dbNowEpochSeconds: number;
      lockedControlRevision: number;
      replayRecordId: (writeId: string) => Promise<string | null>;
      preserve: (rows: readonly PreservedEnvelope[]) => Promise<void>;
    }
  ) => Promise<Result>
): Promise<Result> {
  if (
    authority.capability !== "tasks.read" &&
    authority.capability !== "tasks.write"
  )
    throw Error("task_capability_denied");
  const boundedPool: PostgresTransactionPool = {
    withTransaction: (options, callback) =>
      pool.withTransaction({ ...options, signal }, callback),
  };
  return withAuthorizedSerializableConnectionTransaction(
    boundedPool,
    authority,
    async (transaction) => {
      const { connection } = transaction;
      const snapshot = await loadPostgresTasks(
        connection,
        authority.account_id
      );
      const result = await operation({
        ...snapshot,
        dbNowEpochSeconds: transaction.dbNowEpochSeconds,
        lockedControlRevision: transaction.lockedControlRevision,
        async replayRecordId(writeId) {
          const rows = await connection.query({
            name: "tasks.replay_handle",
            text: "SELECT outcome_json FROM omi_memory.task_write_receipts WHERE account_id=$1 AND write_id=$2",
            values: [authority.account_id, writeId],
          });
          return rows.length === 1 && typeof rows[0]!.outcome_json === "string"
            ? (JSON.parse(rows[0]!.outcome_json) as RecordedWriteOutcome)
                .record_id
            : null;
        },
        async preserve(rows) {
          for (const row of rows)
            await connection.execute({
              name: "tasks.preserve",
              text: "INSERT INTO omi_memory.task_stragglers(account_id,write_id,envelope_digest,envelope_json,account_epoch,retained_at_epoch_seconds) VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT(account_id,write_id,envelope_digest) DO NOTHING",
              values: [
                authority.account_id,
                row.write_id,
                createHash("sha256").update(row.envelope_json).digest("hex"),
                row.envelope_json,
                row.account_epoch,
                row.retained_at_epoch_seconds,
              ],
            });
        },
      });
      snapshot.assertHealthy();
      const clocks = await connection.query({
        name: "tasks.final_clock",
        text: "SELECT floor(extract(epoch FROM clock_timestamp()))::bigint AS now",
        values: [],
      });
      if (
        signal.aborted ||
        safeSequence(clocks[0]?.now) >= authority.expires_at_epoch_seconds
      )
        throw Error("task_authority_expired");
      return result;
    }
  );
}
