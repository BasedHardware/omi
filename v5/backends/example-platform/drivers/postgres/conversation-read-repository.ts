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
