import { InvalidMcpCursorError } from "../../apps/mcp/cursor";
import {
  assertAuthorizedLedgerWriteContextCurrentAt,
  type AuthorizedLedgerWriteContext,
} from "../../apps/service/auth/authorized-context";
import type { PostgresTransactionPool } from "./connection";
import {
  PostgresRepositoryError,
  withAuthorizedSerializableConnectionTransaction,
} from "./transaction";
import {
  parseConversationReadSnapshot,
  type ConversationReadSnapshot,
} from "./conversation-read-projection";

export interface ConversationUnionCursorAfter {
  readonly updatedAt: number;
  readonly id: string;
}

const parseConversationUnionAfter = (
  value: unknown
): ConversationUnionCursorAfter | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const after = (value as { after?: unknown }).after;
  if (after === null || after === undefined) return null;
  if (typeof after !== "object" || Array.isArray(after)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const row = after as Record<string, unknown>;
  const updatedAt =
    typeof row.updatedAt === "number"
      ? row.updatedAt
      : typeof row.updatedAt === "string" && /^(0|[1-9][0-9]*)$/.test(row.updatedAt)
        ? Number(row.updatedAt)
        : null;
  if (
    updatedAt === null
    || !Number.isSafeInteger(updatedAt)
    || updatedAt < 0
    || typeof row.id !== "string"
    || !/^[!-~]{1,256}$/.test(row.id)
  ) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return Object.freeze({ updatedAt, id: row.id });
};

export interface ConversationUnionPageLoad {
  readonly snapshot: ConversationReadSnapshot;
  readonly after: ConversationUnionCursorAfter | null;
}

export interface ConversationPageStorage {
  load(
    limit: number,
    cursorHash: string | null,
    bindingDigest: string,
    revision: number
  ): Promise<ConversationReadSnapshot>;
  save(
    cursorHash: string,
    bindingDigest: string,
    revision: number,
    sequence: number,
    expiresAt: number
  ): Promise<void>;
  loadUnion(
    limit: number,
    cursorHash: string | null,
    bindingDigest: string,
    revision: number,
    chatSnapshotSequence: number
  ): Promise<ConversationUnionPageLoad>;
  saveUnion(
    cursorHash: string,
    bindingDigest: string,
    revision: number,
    chatSnapshotSequence: number,
    lastUpdatedAt: string,
    lastUpdatedAtMs: number,
    lastId: string,
    lastKind: "listen" | "chat",
    expiresAt: number
  ): Promise<void>;
}

export async function withAuthorizedConversationRead<Result>(
  pool: PostgresTransactionPool,
  authority: AuthorizedLedgerWriteContext,
  signal: AbortSignal,
  project: (
    snapshot: ConversationReadSnapshot,
    nowEpochSeconds: number,
    storage: ConversationPageStorage
  ) => Result | Promise<Result>
): Promise<Result> {
  if (authority.capability !== "conversations.read")
    throw new PostgresRepositoryError("capability_denied");
  signal.throwIfAborted();
  const boundedPool: PostgresTransactionPool = {
    withTransaction: (options, operation) =>
      pool.withTransaction({ ...options, signal }, operation),
  };
  return withAuthorizedSerializableConnectionTransaction(
    boundedPool,
    authority,
    async ({ connection, dbNowEpochSeconds }) => {
      const rows = await connection.query({
        name: "conversations.read_snapshot",
        text: "SELECT omi_memory.read_listen_conversation_metadata() AS snapshot",
        values: [],
      });
      if (rows.length !== 1)
        throw new PostgresRepositoryError("persistence_failed");
      const result = await project(
        parseConversationReadSnapshot(rows[0]!.snapshot),
        dbNowEpochSeconds,
        {
          async load(limit, cursorHash, bindingDigest, revision) {
            const page = await connection.query({
              name: "conversations.read_page",
              text: "SELECT omi_memory.read_listen_conversation_page($1,$2,$3,$4) AS snapshot",
              values: [limit, cursorHash, bindingDigest, revision],
            });
            if (page.length !== 1)
              throw new PostgresRepositoryError("persistence_failed");
            if (page[0]!.snapshot === null) throw new InvalidMcpCursorError();
            return parseConversationReadSnapshot(page[0]!.snapshot);
          },
          async save(cursorHash, bindingDigest, revision, sequence, expiresAt) {
            await connection.query({
              name: "conversations.save_cursor",
              text: "SELECT omi_memory.save_listen_conversation_cursor($1,$2,$3,$4,$5)",
              values: [
                cursorHash,
                bindingDigest,
                revision,
                sequence,
                expiresAt,
              ],
            });
          },
          async loadUnion(
            limit,
            cursorHash,
            bindingDigest,
            revision,
            chatSnapshotSequence
          ) {
            const page = await connection.query({
              name: "conversations.read_union_page",
              text: "SELECT omi_memory.read_listen_conversation_union_page($1,$2,$3,$4,$5) AS snapshot",
              values: [
                limit,
                cursorHash,
                bindingDigest,
                revision,
                chatSnapshotSequence,
              ],
            });
            if (page.length !== 1)
              throw new PostgresRepositoryError("persistence_failed");
            if (page[0]!.snapshot === null) throw new InvalidMcpCursorError();
            const snapshotValue = page[0]!.snapshot;
            if (
              snapshotValue === null ||
              typeof snapshotValue !== "object" ||
              Array.isArray(snapshotValue)
            ) {
              throw new PostgresRepositoryError("persistence_failed");
            }
            const snapshotRecord = snapshotValue as Record<string, unknown>;
            return {
              snapshot: parseConversationReadSnapshot({
                revision: snapshotRecord.revision,
                records: snapshotRecord.records,
              }),
              after: parseConversationUnionAfter(snapshotValue),
            };
          },
          async saveUnion(
            cursorHash,
            bindingDigest,
            revision,
            chatSnapshotSequence,
            lastUpdatedAt,
            lastUpdatedAtMs,
            lastId,
            lastKind,
            expiresAt
          ) {
            if (!Number.isSafeInteger(lastUpdatedAtMs) || lastUpdatedAtMs < 0) {
              throw new PostgresRepositoryError("persistence_failed");
            }
            await connection.query({
              name: "conversations.save_union_cursor",
              text: "SELECT omi_memory.save_conversation_union_cursor($1,$2,$3::bigint,$4::bigint,$5::timestamptz,$6::bigint,$7,$8,$9::bigint)",
              values: [
                cursorHash,
                bindingDigest,
                revision,
                chatSnapshotSequence,
                lastUpdatedAt,
                BigInt(lastUpdatedAtMs),
                lastId,
                lastKind,
                expiresAt,
              ],
            });
          },
        }
      );
      const clocks = await connection.query({
        name: "conversations.final_clock",
        text: "SELECT floor(extract(epoch FROM clock_timestamp()))::bigint AS now",
        values: [],
      });
      const now = Number(clocks[0]?.now);
      if (clocks.length !== 1 || !Number.isSafeInteger(now) || now < 0)
        throw new PostgresRepositoryError("persistence_failed");
      signal.throwIfAborted();
      try {
        assertAuthorizedLedgerWriteContextCurrentAt(authority, now);
      } catch {
        throw new PostgresRepositoryError("expired_context");
      }
      return result;
    }
  );
}
