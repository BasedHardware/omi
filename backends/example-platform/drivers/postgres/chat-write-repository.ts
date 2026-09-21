// domain-pending(DIV-CHAT-SENDER-001)
// domain-pending(DIV-CHAT-TYPE-001)
// domain-pending(DIV-CHAT-SESSION-001)
// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
// domain-pending(DIV-CHAT-SOURCE-001)

import {
  assertAuthorizedLedgerWriteContextCurrentAt,
  type AuthorizedLedgerWriteContext,
} from "../../apps/service/auth/authorized-context";
import type {
  ChatAdmissionInput,
  ChatAdmissionOutcome,
} from "../../apps/service/stores/chat-admission";
import type {
  ChatGenerationEvent,
  ChatGenerationFrame,
} from "../../apps/service/stores/chat-generation-events-store";
import type {
  ChatGenerationFinalizationInput,
} from "../../apps/service/stores/chat-generation-finalization";
import {
  detachChatMessage,
  hasWritableChatMessageVocabulary,
  type CanonicalChatMessageWriteOutcome,
  type ChatMessageAdmissionOutcome,
  type ChatMessageRecord,
  type StoredChatMessage,
} from "../../apps/service/stores/chat-messages-store";
import type { PostgresTransactionPool } from "./connection";
import {
  PostgresRepositoryError,
  withAuthorizedSerializableConnectionTransaction,
} from "./transaction";

/** Caller-supplied reservation metadata recorded with admission. Not a producer. */
export interface ChatAdmissionReservation {
  readonly catalogRevision: string;
  readonly subscriptionRevision: string;
  readonly usagePeriodUtc: string;
  readonly billingUnit: string;
}

export interface ChatWriteStorage {
  /**
   * Unmounted storage foundation: persist a human message, its first accepted
   * event, and caller-supplied reservation metadata on one PostgreSQL
   * connection. A missing metadata object refuses. Exact replay of an already-
   * stored message does not insert another reservation row. Nonempty catalog,
   * subscription, period, or unit strings are not paid authorization and do
   * not enforce a budget. No source-owned producer or settlement exists here.
   */
  admit(
    input: ChatAdmissionInput,
    reservation: ChatAdmissionReservation | null,
  ): Promise<ChatAdmissionOutcome>;
  /** Storage-only terminal settlement. Does not record reservation metadata. */
  finalize(input: ChatGenerationFinalizationInput): Promise<ChatGenerationEvent>;
}

const fail = (): never => {
  throw new PostgresRepositoryError("persistence_failed");
};

const integer = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isSafeInteger(value) && value >= 0) return value;
  if (typeof value === "bigint" && value >= 0n && value <= BigInt(Number.MAX_SAFE_INTEGER)) {
    return Number(value);
  }
  if (typeof value === "string" && /^(0|[1-9][0-9]*)$/.test(value)) {
    const parsed = Number(value);
    return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : null;
  }
  return null;
};

const record = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;

const parseStored = (value: unknown): StoredChatMessage => {
  const row = record(value);
  if (row === null) return fail();
  const generationId = row.generationId;
  if (!(generationId === null || typeof generationId === "string")) return fail();
  let message: ChatMessageRecord;
  try {
    const createdAt = integer(row.createdAt);
    const updatedAt = integer(row.updatedAt);
    const journalRevision = integer(row.journalRevision);
    if (createdAt === null || updatedAt === null || journalRevision === null) return fail();
    message = detachChatMessage({
      id: row.id as never,
      text: row.text as never,
      sender: row.sender as never,
      type: row.type as never,
      createdAt,
      updatedAt,
      chatSessionId: row.chatSessionId as never,
      appId: row.appId as never,
      journalRevision,
      payloadHash: row.payloadHash as never,
      messageSource: row.messageSource as never,
      rating: row.rating as never,
      reported: row.reported as never,
      revision: row.revision as never,
      attachments: row.attachments as never,
    });
  } catch {
    return fail();
  }
  return Object.freeze({ message, generationId });
};

const parseFrame = (value: unknown): ChatGenerationFrame => {
  const frame = record(value);
  if (frame === null || typeof frame.kind !== "string" || frame.kind.length === 0) return fail();
  return frame as unknown as ChatGenerationFrame;
};

const parseEvent = (value: unknown): ChatGenerationEvent => {
  const row = record(value);
  if (row === null) return fail();
  const sequence = integer(row.sequence);
  const createdAt = integer(row.createdAt);
  if (typeof row.id !== "string" || row.id.length === 0
    || typeof row.generationId !== "string" || row.generationId.length === 0
    || sequence === null || sequence < 1 || createdAt === null) return fail();
  return Object.freeze({
    id: row.id,
    generationId: row.generationId,
    sequence,
    createdAt,
    frame: parseFrame(row.frame),
  });
};

const isTerminalKind = (kind: string): boolean =>
  kind === "done" || kind === "failed" || kind === "cancelled";

const attachmentsJson = (message: ChatMessageRecord): string =>
  JSON.stringify(message.attachments ?? []);

const messageRowFromSql = (row: Record<string, unknown>): StoredChatMessage => parseStored({
  id: row.id,
  text: row.text,
  sender: row.sender,
  type: row.message_type,
  createdAt: row.created_at,
  updatedAt: row.updated_at,
  chatSessionId: row.chat_session_id,
  appId: row.app_id,
  journalRevision: row.journal_revision,
  payloadHash: row.payload_hash,
  messageSource: row.message_source,
  rating: row.rating,
  reported: row.reported,
  revision: row.server_revision,
  attachments: row.attachments_json ?? [],
  generationId: row.generation_id,
});

const eventRowFromSql = (row: Record<string, unknown>): ChatGenerationEvent => parseEvent({
  id: row.event_id,
  generationId: row.generation_id,
  sequence: row.sequence,
  createdAt: row.created_at,
  frame: row.frame_json,
});

const assertSameAccount = (
  authority: AuthorizedLedgerWriteContext,
  accountId: string,
): void => {
  if (accountId !== authority.account_id) {
    throw new PostgresRepositoryError("authorization_state_denied");
  }
};

export async function withAuthorizedChatWrite<Result>(
  pool: PostgresTransactionPool,
  authority: AuthorizedLedgerWriteContext,
  signal: AbortSignal,
  project: (storage: ChatWriteStorage) => Result | Promise<Result>,
): Promise<Result> {
  if (authority.capability !== "chat.write") {
    throw new PostgresRepositoryError("capability_denied");
  }
  signal.throwIfAborted();
  const boundedPool: PostgresTransactionPool = {
    withTransaction: (options, operation) =>
      pool.withTransaction({ ...options, signal }, operation),
  };
  return withAuthorizedSerializableConnectionTransaction(
    boundedPool,
    authority,
    async ({ connection, dbNowEpochSeconds }) => {
      const readMessage = async (messageId: string): Promise<StoredChatMessage | null> => {
        const rows = await connection.query({
          name: "chat.write_read_message",
          text: `SELECT id, text, sender, message_type, created_at, updated_at, chat_session_id,
            app_id, journal_revision, payload_hash, message_source, rating, reported,
            server_revision, attachments_json, generation_id
            FROM omi_memory.chat_messages WHERE account_id=$1 AND id=$2`,
          values: [authority.account_id, messageId],
        });
        if (rows.length === 0) return null;
        if (rows.length !== 1) return fail();
        return messageRowFromSql(rows[0]!);
      };

      const listEvents = async (generationId: string): Promise<readonly ChatGenerationEvent[]> => {
        const rows = await connection.query({
          name: "chat.write_list_events",
          text: `SELECT event_id, generation_id, sequence, created_at, frame_json
            FROM omi_memory.chat_generation_events
            WHERE account_id=$1 AND generation_id=$2
            ORDER BY sequence ASC`,
          values: [authority.account_id, generationId],
        });
        return Object.freeze(rows.map(eventRowFromSql));
      };

      const writeMessage = async (
        message: ChatMessageRecord,
        generationId: string | null,
      ): Promise<CanonicalChatMessageWriteOutcome> => {
        const detached = detachChatMessage(message);
        if (!hasWritableChatMessageVocabulary(detached)) {
          return { kind: "invalid_vocabulary" };
        }
        const inserted = await connection.execute({
          name: "chat.write_insert_message",
          text: `INSERT INTO omi_memory.chat_messages (
            account_id, id, text, sender, message_type, created_at, updated_at,
            chat_session_id, app_id, journal_revision, payload_hash, message_source,
            rating, reported, server_revision, attachments_json, generation_id
          ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,($16::text)::jsonb,$17
          ) ON CONFLICT (account_id, id) DO NOTHING`,
          values: [
            authority.account_id,
            detached.id,
            detached.text,
            detached.sender,
            detached.type,
            detached.createdAt,
            detached.updatedAt,
            detached.chatSessionId,
            detached.appId,
            detached.journalRevision,
            detached.payloadHash,
            detached.messageSource,
            detached.rating,
            detached.reported,
            detached.revision,
            attachmentsJson(detached),
            generationId,
          ],
        });
        if (inserted.rowCount === 1) {
          const stored = await readMessage(detached.id);
          if (stored === null) return fail();
          return { kind: "created", stored };
        }
        const current = await readMessage(detached.id);
        if (current === null) return fail();
        if (current.message.payloadHash !== detached.payloadHash) return { kind: "conflict" };
        if (detached.journalRevision <= current.message.journalRevision) {
          return { kind: "replay", stored: current };
        }
        const updated = await connection.execute({
          name: "chat.write_update_message",
          text: `UPDATE omi_memory.chat_messages SET
            text=$1, sender=$2, message_type=$3, created_at=$4, updated_at=$5,
            chat_session_id=$6, app_id=$7, journal_revision=$8, message_source=$9,
            rating=$10, reported=$11, server_revision=$12, attachments_json=($13::text)::jsonb,
            generation_id=COALESCE(generation_id, $14)
            WHERE account_id=$15 AND id=$16 AND payload_hash=$17 AND journal_revision<$18`,
          values: [
            detached.text,
            detached.sender,
            detached.type,
            detached.createdAt,
            detached.updatedAt,
            detached.chatSessionId,
            detached.appId,
            detached.journalRevision,
            detached.messageSource,
            detached.rating,
            detached.reported,
            detached.revision,
            attachmentsJson(detached),
            generationId,
            authority.account_id,
            detached.id,
            detached.payloadHash,
            detached.journalRevision,
          ],
        });
        if (updated.rowCount !== 1) return fail();
        const stored = await readMessage(detached.id);
        if (stored === null) return fail();
        return { kind: "updated", stored };
      };

      const admitHuman = async (
        message: ChatMessageRecord,
        generationId: string,
      ): Promise<ChatMessageAdmissionOutcome> => {
        if (message.sender !== "human") return { kind: "conflict" };
        const outcome = await writeMessage(message, generationId);
        if (outcome.kind === "invalid_vocabulary" || outcome.kind === "conflict") {
          return { kind: "conflict" };
        }
        return {
          kind: outcome.kind === "created" ? "created" : "replay",
          stored: outcome.stored,
        };
      };

      const appendEvent = async (input: {
        readonly generationId: string;
        readonly eventId: string;
        readonly createdAt: number;
        readonly frame: ChatGenerationFrame;
      }): Promise<{ kind: "appended" | "replay" | "conflict"; event: ChatGenerationEvent }> => {
        const existing = await connection.query({
          name: "chat.write_read_event",
          text: `SELECT event_id, generation_id, sequence, created_at, frame_json
            FROM omi_memory.chat_generation_events
            WHERE account_id=$1 AND generation_id=$2 AND event_id=$3`,
          values: [authority.account_id, input.generationId, input.eventId],
        });
        if (existing.length > 1) return fail();
        if (existing.length === 1) {
          const event = eventRowFromSql(existing[0]!);
          return event.createdAt === input.createdAt
            && JSON.stringify(event.frame) === JSON.stringify(input.frame)
            ? { kind: "replay", event }
            : { kind: "conflict", event };
        }
        const events = await listEvents(input.generationId);
        const terminal = events.find((event) => isTerminalKind(event.frame.kind));
        if (terminal !== undefined) return { kind: "replay", event: terminal };
        const nextSequence = (events.at(-1)?.sequence ?? 0) + 1;
        const inserted = await connection.execute({
          name: "chat.write_insert_event",
          text: `INSERT INTO omi_memory.chat_generation_events (
            account_id, generation_id, sequence, event_id, created_at, frame_json
          ) VALUES ($1,$2,$3,$4,$5,($6::text)::jsonb)`,
          values: [
            authority.account_id,
            input.generationId,
            nextSequence,
            input.eventId,
            input.createdAt,
            JSON.stringify(input.frame),
          ],
        });
        if (inserted.rowCount !== 1) return fail();
        return {
          kind: "appended",
          event: Object.freeze({
            id: input.eventId,
            generationId: input.generationId,
            sequence: nextSequence,
            createdAt: input.createdAt,
            frame: structuredClone(input.frame),
          }),
        };
      };

      const storage: ChatWriteStorage = {
        async admit(input, reservation) {
          assertSameAccount(authority, input.accountId);
          const messageAttachmentIds = (input.message.attachments ?? []).map(
            (attachment) => attachment.id,
          );
          if (messageAttachmentIds.length !== input.attachmentIds.length
            || messageAttachmentIds.some((id, index) => id !== input.attachmentIds[index])) {
            return { kind: "conflict" };
          }
          if (input.attachmentIds.length > 0) return { kind: "attachment_not_found" };

          const existing = await readMessage(input.message.id);
          if (existing !== null) {
            if (existing.message.payloadHash !== input.message.payloadHash) {
              return { kind: "conflict" };
            }
            const replay = await admitHuman(
              input.message,
              existing.generationId ?? input.generationId,
            );
            if (replay.kind === "conflict") return { kind: "conflict" };
            return { kind: "replay", stored: replay.stored };
          }

          if (reservation === null
            || reservation.catalogRevision.length === 0
            || reservation.subscriptionRevision.length === 0
            || reservation.usagePeriodUtc.length === 0
            || reservation.billingUnit.length === 0) {
            return { kind: "entitlement" };
          }

          const admitted = await admitHuman(input.message, input.generationId);
          if (admitted.kind === "conflict") return { kind: "conflict" };
          if (admitted.kind === "replay") return { kind: "replay", stored: admitted.stored };

          const reserved = await connection.execute({
            name: "chat.write_insert_reservation",
            text: `INSERT INTO omi_memory.chat_admission_reservations (
              account_id, message_id, payload_hash, catalog_revision,
              subscription_revision, usage_period_utc, billing_unit, reserved_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)`,
            values: [
              authority.account_id,
              input.message.id,
              input.message.payloadHash,
              reservation.catalogRevision,
              reservation.subscriptionRevision,
              reservation.usagePeriodUtc,
              reservation.billingUnit,
              input.admittedAt,
            ],
          });
          if (reserved.rowCount !== 1) return fail();

          const accepted = await appendEvent({
            generationId: input.generationId,
            eventId: input.acceptedEventId,
            createdAt: input.admittedAt,
            frame: {
              kind: "accepted",
              message: admitted.stored.message,
              generation: { id: input.generationId },
            },
          });
          if (accepted.kind === "conflict") {
            throw new TypeError("chat admission event identity conflict");
          }
          if (accepted.kind !== "appended") {
            throw new TypeError("chat admission event identity conflict");
          }
          return {
            kind: "created",
            stored: admitted.stored,
            acceptedEvent: accepted.event,
          };
        },

        async finalize(input) {
          assertSameAccount(authority, input.accountId);
          const events = await listEvents(input.generationId);
          const terminal = events.find((event) => isTerminalKind(event.frame.kind));
          if (terminal !== undefined) return terminal;
          const message = input.frame.kind === "failed" ? null : input.frame.message;
          if (message !== null) {
            const written = await writeMessage(message, input.generationId);
            if (written.kind === "conflict" || written.kind === "invalid_vocabulary") {
              throw new TypeError("canonical chat generation message was refused");
            }
          }
          const appended = await appendEvent({
            generationId: input.generationId,
            eventId: input.eventId,
            createdAt: input.createdAt,
            frame: input.frame,
          });
          if (appended.kind === "conflict") {
            throw new TypeError("chat generation terminal event identity conflict");
          }
          return appended.event;
        },
      };

      const result = await project(storage);
      const clocks = await connection.query({
        name: "chat.write_final_clock",
        text: "SELECT floor(extract(epoch FROM clock_timestamp()))::bigint AS now",
        values: [],
      });
      const now = integer(clocks[0]?.now);
      if (clocks.length !== 1 || now === null) return fail();
      void dbNowEpochSeconds;
      signal.throwIfAborted();
      try {
        assertAuthorizedLedgerWriteContextCurrentAt(authority, now);
      } catch {
        throw new PostgresRepositoryError("expired_context");
      }
      return result;
    },
  );
}
