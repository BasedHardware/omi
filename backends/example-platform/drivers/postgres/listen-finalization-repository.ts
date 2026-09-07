import { randomUUID } from "node:crypto";
import type { DeviceTranscriptionRecord, DeviceTranscriptionRepository } from "../../apps/service/listen/device-transcription";
import { parsePrerecordedTranscription } from "../../apps/service/listen/prerecorded-transcription";
import { parseDeviceSessionUploadCreate, validateDeviceSessionUploadBatch, DEVICE_UPLOAD_SESSION_ID, type DeviceSessionUpload, type DeviceSessionUploadRepository } from "../../apps/service/stores/device-session-upload";
import { isProxy } from "node:util/types";

import {
  assertAuthorizedLedgerWriteContext,
  assertAuthorizedLedgerWriteContextCurrentAt,
  type AuthorizedLedgerWriteContext,
} from "../../apps/service/auth/authorized-context";
import {
  LISTEN_CAPTURE_APPEND_VERSION,
  LISTEN_CAPTURE_FINALIZE_VERSION,
  LISTEN_CAPTURE_INTERRUPT_VERSION,
  LISTEN_CAPTURE_OPEN_VERSION,
  LISTEN_CAPTURE_RESUME_VERSION,
  parseListenCaptureAppendRequest,
  parseListenCaptureFinalizeRequest,
  parseListenCaptureInterruptRequest,
  parseListenCaptureOpenRequest,
  parseListenCaptureResumeRequest,
  type ListenCaptureAppendOutcome,
  type ListenCaptureAppendRequest,
  type ListenCaptureFinalizeOutcome,
  type ListenCaptureFinalizeRequest,
  type ListenCaptureOpenOutcome,
  type ListenCaptureOpenRequest,
  type ListenCaptureStateOutcome,
  type ListenCaptureInterruptRequest,
  type ListenCaptureResumeRequest,
  type ListenFinalizationRepository,
} from "../../apps/service/stores/listen-finalization-repository";
import type { ListenSessionRecord, ListenTranscriptSegment } from "../../apps/service/stores/listen-store";
import { sealListenFormationFinalization } from "../../apps/service/listen/formation-ingestion";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SqlValue,
} from "./connection";
import {
  PostgresRepositoryError,
  type PostgresTransactionObservability,
  withAuthorizedSerializableConnectionTransaction,
} from "./transaction";

const CAPABILITY = "listen.capture.write";
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const SOURCE = /^[\x20-\x7e]{0,256}$/;
const HASH = /^[a-f0-9]{64}$/;

const OPEN_ROW_KEYS = ["result", "session_id", "conversation_id"] as const;
const APPEND_ROW_KEYS = ["result", "segment_id", "ordinal"] as const;
const STATE_ROW_KEYS = ["result", "state_sequence"] as const;
const FINALIZE_ROW_KEYS = [
  "result", "finalization_id", "formation_work_id", "transcript_digest",
  "finalization_digest", "segment_count",
] as const;
const INPUT_ROW_KEYS = [
  "session_id", "conversation_id", "client_conversation_id", "started_at", "source",
  "codec", "sample_rate", "channels", "current_state", "segment_ordinal", "segment_id",
  "text_content", "is_user", "start_seconds", "end_seconds",
] as const;

const fail = (code: PostgresRepositoryError["code"]): never => {
  throw new PostgresRepositoryError(code);
};

const exactRow = (value: unknown, keys: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("persistence_failed");
  const objectValue = value as object;
  const actual = Reflect.ownKeys(objectValue);
  const expected = [...keys].sort();
  if (actual.some((key) => typeof key !== "string") || actual.length !== expected.length
    || (actual as string[]).sort().some((key, index) => key !== expected[index])) {
    fail("persistence_failed");
  }
  const output: Record<string, unknown> = {};
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(objectValue, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("persistence_failed");
    output[key] = (descriptor as PropertyDescriptor & { readonly value: unknown }).value;
  }
  return output;
};

const rowsOne = <Row extends Record<string, unknown>>(
  rows: readonly Row[],
  keys: readonly string[],
): Record<string, unknown> => {
  if (rows.length !== 1 || !rows[0]) fail("persistence_failed");
  return exactRow(rows[0], keys);
};

const text = (value: unknown): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail("persistence_failed");
  return value as string;
};

const nullableText = (value: unknown): string | null => {
  if (value === null) return null;
  if (typeof value !== "string" || !SOURCE.test(value)) fail("persistence_failed");
  return value as string;
};

const digest = (value: unknown): string => {
  const result = text(value);
  if (!HASH.test(result)) fail("persistence_failed");
  return result;
};

const integer = (value: unknown): number => {
  if (typeof value !== "number" && typeof value !== "string" && typeof value !== "bigint") {
    fail("persistence_failed");
  }
  if (typeof value === "number" && !Number.isInteger(value)) fail("persistence_failed");
  if (typeof value === "string" && !/^(?:0|[1-9][0-9]*)$/.test(value)) fail("persistence_failed");
  const result = Number(value);
  if (!Number.isSafeInteger(result) || result < 0) fail("persistence_failed");
  return result;
};

/** Normalize both Postgres.js Date results and text results to the contract form. */
const timestamp = (value: unknown): string => {
  if (value instanceof Date) {
    if (!Number.isFinite(value.getTime())) fail("persistence_failed");
    return value.toISOString();
  }
  if (typeof value !== "string" || !TOKEN.test(value) || !Number.isFinite(Date.parse(value))) {
    fail("persistence_failed");
  }
  return new Date(value as string).toISOString();
};

const requestTimestamp = (value: string): string => {
  const millis = Date.parse(value);
  if (!Number.isFinite(millis)) throw new TypeError("invalid listen timestamp");
  return new Date(millis).toISOString();
};

const sessionHash = (
  accountId: string,
  request: Readonly<ListenCaptureOpenRequest>,
  startedAt: string,
): string => sha256CanonicalContent({
  contract_version: LISTEN_CAPTURE_OPEN_VERSION,
  account_id: accountId,
  session_id: request.session_id,
  conversation_id: request.conversation_id,
  client_conversation_id: request.client_conversation_id,
  started_at: startedAt,
  source: request.source,
  codec: request.codec,
  sample_rate: request.sample_rate,
  channels: request.channels,
});

const stateHash = (
  accountId: string,
  sessionId: string,
  version: string,
  state: string,
  eventAt: string,
): string => sha256CanonicalContent({
  contract_version: version,
  account_id: accountId,
  session_id: sessionId,
  state,
  event_at: eventAt,
});

const segmentHash = (
  accountId: string,
  sessionId: string,
  request: Readonly<ListenCaptureAppendRequest>,
  appendedAt: string,
): string => sha256CanonicalContent({
  contract_version: LISTEN_CAPTURE_APPEND_VERSION,
  account_id: accountId,
  session_id: sessionId,
  segment: request.segment,
  appended_at: appendedAt,
});

const finalizationRowHash = (finalization: ReturnType<typeof sealListenFormationFinalization>): string =>
  sha256CanonicalContent({ contract_version: "listen-finalization-row-v1", finalization });

const intentHash = (accountId: string, conversationId: string, finalizationId: string): string =>
  sha256CanonicalContent({
    contract_version: "listen-conversation-finalization-intent-v1",
    account_id: accountId, conversation_id: conversationId, finalization_id: finalizationId,
    intent: "process_memories", locked: true,
  });

const outboxId = (finalizationId: string): string => `listen-outbox:${finalizationId}`;

const outboxPayloadDigest = (finalization: ReturnType<typeof sealListenFormationFinalization>): string =>
  sha256CanonicalContent({ contract_version: "listen-formation-outbox-payload-v1", finalization });

const outboxHash = (
  accountId: string,
  finalization: ReturnType<typeof sealListenFormationFinalization>,
  payloadDigest: string,
): string => sha256CanonicalContent({
  contract_version: "listen-formation-outbox-v1",
  account_id: accountId,
  outbox_id: outboxId(finalization.finalization_id),
  finalization_id: finalization.finalization_id,
  formation_work_id: finalization.formation_work_id,
  state: "pending",
  finalization_digest: finalization.finalization_digest,
  payload_digest: payloadDigest,
  created_at: finalization.ended_at,
});

const preflight = (context: AuthorizedLedgerWriteContext): AuthorizedLedgerWriteContext => {
  const authorized = assertAuthorizedLedgerWriteContext(context);
  if (authorized.capability !== CAPABILITY) fail("capability_denied");
  return authorized;
};

const parseOpen = (rows: readonly Record<string, unknown>[]): ListenCaptureOpenOutcome => {
  const row = rowsOne(rows, OPEN_ROW_KEYS);
  const result = text(row.result);
  if (result !== "opened" && result !== "replayed") fail("persistence_failed");
  return Object.freeze({
    kind: result === "opened" ? "opened" : "replayed",
    session_id: text(row.session_id), conversation_id: text(row.conversation_id),
  });
};

const parseAppend = (rows: readonly Record<string, unknown>[]): ListenCaptureAppendOutcome => {
  const row = rowsOne(rows, APPEND_ROW_KEYS);
  const result = text(row.result);
  if (result !== "appended" && result !== "replayed") fail("persistence_failed");
  return Object.freeze({
    kind: result === "appended" ? "appended" : "replayed",
    session_id: "", segment_id: text(row.segment_id), ordinal: integer(row.ordinal),
  });
};

const parseState = (
  rows: readonly Record<string, unknown>[],
  operation: "interrupt" | "resume",
): ListenCaptureStateOutcome => {
  const row = rowsOne(rows, STATE_ROW_KEYS);
  const result = text(row.result);
  const expected = operation === "interrupt" ? "interrupted" : "resumed";
  if (result !== expected && result !== "replayed") fail("persistence_failed");
  return Object.freeze({
    kind: result === "interrupted" ? "interrupted" : result === "resumed" ? "resumed" : "replayed",
    session_id: "", state_sequence: integer(row.state_sequence),
  });
};

const parseFinalize = (rows: readonly Record<string, unknown>[]): ListenCaptureFinalizeOutcome => {
  const row = rowsOne(rows, FINALIZE_ROW_KEYS);
  const result = text(row.result);
  if (result !== "sealed" && result !== "replayed") fail("persistence_failed");
  return Object.freeze({
    kind: result === "sealed" ? "sealed" : "replayed",
    finalization_id: text(row.finalization_id),
    formation_work_id: text(row.formation_work_id),
    transcript_digest: digest(row.transcript_digest),
    finalization_digest: digest(row.finalization_digest),
    segment_count: integer(row.segment_count),
  });
};

interface ParsedInput {
  readonly session: Readonly<ListenSessionRecord>;
  readonly segments: readonly Readonly<ListenTranscriptSegment>[];
}

const parseInput = (rows: readonly Record<string, unknown>[]): ParsedInput => {
  if (rows.length === 0) fail("persistence_failed");
  const first = exactRow(rows[0], INPUT_ROW_KEYS);
  const sessionId = text(first.session_id);
  const conversationId = text(first.conversation_id);
  const clientConversationId = nullableText(first.client_conversation_id);
  const startedAt = timestamp(first.started_at);
  const source = nullableText(first.source);
  const codec = text(first.codec);
  const sampleRate = integer(first.sample_rate);
  const channels = integer(first.channels);
  const currentState = text(first.current_state);
  if (!["active", "interrupted", "completed", "entitlement_exhausted"].includes(currentState)) {
    fail("persistence_failed");
  }
  const segments: ListenTranscriptSegment[] = [];
  rows.forEach((raw, index) => {
    const row = index === 0 ? first : exactRow(raw, INPUT_ROW_KEYS);
    if (text(row.session_id) !== sessionId || text(row.conversation_id) !== conversationId
      || nullableText(row.client_conversation_id) !== clientConversationId
      || timestamp(row.started_at) !== startedAt || nullableText(row.source) !== source
      || text(row.codec) !== codec || integer(row.sample_rate) !== sampleRate
      || integer(row.channels) !== channels || text(row.current_state) !== currentState) {
      fail("persistence_failed");
    }
    const allNull = row.segment_ordinal === null && row.segment_id === null
      && row.text_content === null && row.is_user === null
      && row.start_seconds === null && row.end_seconds === null;
    if (allNull) {
      if (rows.length !== 1) fail("persistence_failed");
      return;
    }
    if (row.segment_ordinal === null || row.segment_id === null || row.text_content === null
      || row.is_user === null || row.start_seconds === null || row.end_seconds === null
      || typeof row.is_user !== "boolean" || typeof row.text_content !== "string"
      || row.text_content.length === 0 || row.text_content.length > 1_500
      || typeof row.start_seconds !== "number" || !Number.isFinite(row.start_seconds)
      || typeof row.end_seconds !== "number" || !Number.isFinite(row.end_seconds)
      || row.start_seconds < 0 || row.end_seconds < row.start_seconds) fail("persistence_failed");
    const ordinal = integer(row.segment_ordinal);
    if (ordinal !== segments.length) fail("persistence_failed");
    segments.push(Object.freeze({
      id: text(row.segment_id), text: row.text_content as string,
      is_user: row.is_user as boolean, start: row.start_seconds as number, end: row.end_seconds as number,
    }));
  });
  const session: ListenSessionRecord = Object.freeze({
    id: sessionId, conversationId, clientConversationId, startedAt,
    updatedAt: startedAt, endedAt: null, status: currentState as ListenSessionRecord["status"],
    source, codec, sampleRate, channels,
  });
  return Object.freeze({ session, segments: Object.freeze(segments) });
};

const normalizeOpen = (request: Readonly<ListenCaptureOpenRequest>): Readonly<ListenCaptureOpenRequest> =>
  Object.freeze({ ...request, started_at: requestTimestamp(request.started_at) });
const normalizeAppend = (request: Readonly<ListenCaptureAppendRequest>): Readonly<ListenCaptureAppendRequest> =>
  Object.freeze({ ...request, appended_at: requestTimestamp(request.appended_at) });

export interface PostgresListenFinalizationRepositoryOptions {
  readonly pool: PostgresTransactionPool;
  readonly observability?: PostgresTransactionObservability;
}

/**
 * Inert PostgreSQL persistence adapter for Listen capture.  It is deliberately
 * not composed into a route or worker: callers must provide an already-issued
 * listen.capture.write authority and all writes go through fixed security-
 * definer functions on one serializable connection.
 */
export const createPostgresListenFinalizationRepository = (
  options: PostgresListenFinalizationRepositoryOptions,
): ListenFinalizationRepository => {
  const run = <Result>(
    context: AuthorizedLedgerWriteContext,
    callback: (args: { readonly authority: AuthorizedLedgerWriteContext; readonly connection: CheckedOutPostgresConnection }) => Promise<Result>,
  ): Promise<Result> => {
    return withAuthorizedSerializableConnectionTransaction(
      options.pool,
      preflight(context),
      async (transaction) => {
        const result = await callback(transaction);
        const rows = await transaction.connection.query<{ now: unknown }>({ name: "listen.capture.final_clock", text: "SELECT floor(extract(epoch FROM clock_timestamp()))::bigint AS now", values: [] });
        try { assertAuthorizedLedgerWriteContextCurrentAt(transaction.authority, integer(rows[0]?.now)); }
        catch { throw new PostgresRepositoryError("expired_context"); }
        return result;
      },
      options.observability ?? {},
    );
  };

  const open = async (context: AuthorizedLedgerWriteContext, value: ListenCaptureOpenRequest): Promise<ListenCaptureOpenOutcome> => {
    const request = normalizeOpen(parseListenCaptureOpenRequest(value));
    return run(context, async ({ authority, connection }) => {
      const rows = await connection.query<Record<string, unknown>>({
        name: "listen.capture.open",
        text: `SELECT * FROM omi_memory.open_listen_capture_session($1, $2, $3, $4::timestamptz, $5, $6, $7, $8, $9, $10)`,
        values: [request.session_id, request.conversation_id, request.client_conversation_id,
          request.started_at, request.source, request.codec, request.sample_rate, request.channels,
          sessionHash(authority.account_id, request, request.started_at),
          stateHash(authority.account_id, request.session_id, LISTEN_CAPTURE_OPEN_VERSION, "active", request.started_at)],
      });
      const result = parseOpen(rows);
      if (result.session_id !== request.session_id || result.conversation_id !== request.conversation_id) fail("persistence_failed");
      return result;
    });
  };

  const append = async (context: AuthorizedLedgerWriteContext, value: ListenCaptureAppendRequest): Promise<ListenCaptureAppendOutcome> => {
    const request = normalizeAppend(parseListenCaptureAppendRequest(value));
    return run(context, async ({ authority, connection }) => {
      const rows = await connection.query<Record<string, unknown>>({
        name: "listen.capture.append",
        text: `SELECT * FROM omi_memory.append_listen_capture_segment($1, $2, $3, $4, $5, $6, $7::timestamptz, $8)`,
        values: [request.session_id, request.segment.id, request.segment.text, request.segment.is_user,
          request.segment.start, request.segment.end, request.appended_at,
          segmentHash(authority.account_id, request.session_id, request, request.appended_at)],
      });
      const result = parseAppend(rows);
      return Object.freeze({ ...result, session_id: request.session_id });
    });
  };

  const transition = async (
    context: AuthorizedLedgerWriteContext,
    request: Readonly<ListenCaptureInterruptRequest | ListenCaptureResumeRequest>,
    operation: "interrupt" | "resume",
  ): Promise<ListenCaptureStateOutcome> => {
    const parsed = operation === "interrupt"
      ? parseListenCaptureInterruptRequest(request)
      : parseListenCaptureResumeRequest(request);
    const eventAt = requestTimestamp(
      operation === "interrupt"
        ? (parsed as Readonly<ListenCaptureInterruptRequest>).interrupted_at
        : (parsed as Readonly<ListenCaptureResumeRequest>).resumed_at,
    );
    return run(context, async ({ authority, connection }) => {
      const rows = await connection.query<Record<string, unknown>>({
        name: `listen.capture.${operation}`,
        text: `SELECT * FROM omi_memory.transition_listen_capture_state($1, $2, $3::timestamptz, $4)`,
        values: [parsed.session_id, operation, eventAt,
          stateHash(authority.account_id, parsed.session_id,
            operation === "interrupt" ? LISTEN_CAPTURE_INTERRUPT_VERSION : LISTEN_CAPTURE_RESUME_VERSION,
            operation === "interrupt" ? "interrupted" : "active", eventAt)],
      });
      const result = parseState(rows, operation);
      return Object.freeze({ ...result, session_id: parsed.session_id });
    });
  };

  const finalize = async (context: AuthorizedLedgerWriteContext, value: ListenCaptureFinalizeRequest): Promise<ListenCaptureFinalizeOutcome> => {
    const request = parseListenCaptureFinalizeRequest(value);
    const endedAt = requestTimestamp(request.ended_at);
    return run(context, async ({ authority, connection }) => {
      const inputRows = await connection.query<Record<string, unknown>>({
        name: "listen.capture.read_finalization_input",
        text: "SELECT * FROM omi_memory.read_listen_capture_finalization_input($1)",
        values: [request.session_id],
      });
      const input = parseInput(inputRows);
      if (input.session.status === "interrupted") fail("transition_invalid");
      if (input.session.status !== "active" && input.session.status !== request.terminal_status) {
        fail("transition_invalid");
      }
      if (input.segments.length === 0) fail("transition_invalid");
      const startedMillis = Date.parse(input.session.startedAt);
      const endedMillis = Date.parse(endedAt);
      if (!Number.isFinite(startedMillis) || !Number.isFinite(endedMillis)
        || endedMillis < startedMillis
        || input.segments.some((segment) => segment.end > (endedMillis - startedMillis) / 1_000 + 0.001)) {
        fail("transition_invalid");
      }
      const finalization = sealListenFormationFinalization({
        owner_account_id: authority.account_id,
        session: Object.freeze({ ...input.session, status: request.terminal_status,
          updatedAt: endedAt, endedAt }),
        segments: input.segments,
      });
      const payloadDigest = outboxPayloadDigest(finalization);
      const rows = await connection.query<Record<string, unknown>>({
        name: "listen.capture.finalize",
        text: `SELECT * FROM omi_memory.seal_listen_capture_finalization($1, $2, $3, $4, $5, $6, $7::timestamptz, $8::timestamptz, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)`,
        values: [finalization.session_id, finalization.finalization_id, finalization.formation_work_id,
          finalization.conversation_id, finalization.terminal_status, finalization.capture_completeness,
          finalization.started_at, finalization.ended_at, finalization.source, finalization.segments.length,
          finalization.transcript_digest, finalization.finalization_digest, finalizationRowHash(finalization),
          stateHash(authority.account_id, finalization.session_id, LISTEN_CAPTURE_FINALIZE_VERSION,
            finalization.terminal_status, finalization.ended_at),
          intentHash(authority.account_id, finalization.conversation_id, finalization.finalization_id),
          outboxId(finalization.finalization_id), payloadDigest,
          outboxHash(authority.account_id, finalization, payloadDigest)],
      });
      const result = parseFinalize(rows);
      if (result.finalization_id !== finalization.finalization_id
        || result.formation_work_id !== finalization.formation_work_id
        || result.transcript_digest !== finalization.transcript_digest
        || result.finalization_digest !== finalization.finalization_digest
        || result.segment_count !== finalization.segments.length) fail("persistence_failed");
      return result;
    });
  };

  return Object.freeze({
    open,
    append,
    interrupt: (context: AuthorizedLedgerWriteContext, request: ListenCaptureInterruptRequest) =>
      transition(context, request, "interrupt"),
    resume: (context: AuthorizedLedgerWriteContext, request: ListenCaptureResumeRequest) =>
      transition(context, request, "resume"),
    finalize,
  });
};

export function createPostgresDeviceSessionUploadRepository(options: PostgresListenFinalizationRepositoryOptions): DeviceSessionUploadRepository {
  const parse = (value: unknown): DeviceSessionUpload | null => {
    if (value === null) return null;
    const hasCapturedAt = typeof value === "object" && Object.prototype.hasOwnProperty.call(value, "capturedAtMs");
    const row = exactRow(value, ["id", "deviceId", "deviceName", "codec", "state", "byteCount", "chunkCount", "startedAt", "endedAt", ...(hasCapturedAt ? ["capturedAtMs"] : [])]);
    const capturedAtMs = hasCapturedAt ? integer(row.capturedAtMs) : undefined;
    if (capturedAtMs !== undefined && (capturedAtMs < 0 || capturedAtMs > 8_640_000_000_000_000)) fail("persistence_failed");
    if (typeof row.id !== "string" || !DEVICE_UPLOAD_SESSION_ID.test(row.id)
      || typeof row.deviceId !== "string" || (row.deviceName !== null && typeof row.deviceName !== "string")
      || (row.state !== "open" && row.state !== "complete")) fail("persistence_failed");
    return Object.freeze({ ...(capturedAtMs === undefined ? {} : { capturedAtMs }), id: row.id as string, deviceId: row.deviceId as string, deviceName: row.deviceName as string | null,
      codec: integer(row.codec), state: row.state as "open" | "complete", byteCount: integer(row.byteCount),
      chunkCount: integer(row.chunkCount), startedAt: integer(row.startedAt), endedAt: row.endedAt === null ? null : integer(row.endedAt) });
  };
  const query = (context: AuthorizedLedgerWriteContext, statement: import("./connection").SqlStatement) =>
    withAuthorizedSerializableConnectionTransaction(options.pool, preflight(context), async ({ connection }) => {
      const rows = await connection.query<{ session: unknown }>(statement);
      if (rows.length !== 1) fail("persistence_failed");
      const session = parse(rows[0]!.session);
      const clocks = await connection.query({ name: "listen.audio.final_clock",
        text: "SELECT floor(extract(epoch FROM clock_timestamp()))::bigint AS now", values: [] });
      if (clocks.length !== 1) fail("persistence_failed");
      const now = integer(clocks[0]!.now);
      try { assertAuthorizedLedgerWriteContextCurrentAt(context, now); }
      catch { fail("expired_context"); }
      return session;
    }, options.observability ?? {});
  const id = (value: string) => { if (!DEVICE_UPLOAD_SESSION_ID.test(value)) throw new TypeError("invalid_device_request"); return value; };
  return Object.freeze<DeviceSessionUploadRepository>({
    async open(context, value) {
      const input = parseDeviceSessionUploadCreate(value);
      const sessionId = randomUUID();
      const request = normalizeOpen(parseListenCaptureOpenRequest({
        version: LISTEN_CAPTURE_OPEN_VERSION, session_id: sessionId, conversation_id: randomUUID(),
        client_conversation_id: input.captureId, started_at: new Date().toISOString(), source: "omi-device",
        codec: input.codec === 1 ? "pcm8" : input.codec === 20 || input.codec === 21 ? "opus" : String(input.codec),
        sample_rate: 16000, channels: 1,
      }));
      const result = await query(context, {
        name: "listen.audio.open", text: "SELECT omi_memory.open_listen_audio_upload($1::uuid,$2,$3,$4,$5,$6,$7::timestamptz,$8,$9,$10,$11,$12::bigint) AS session",
        values: [input.captureId, input.deviceId, input.deviceName, input.codec, request.session_id, request.conversation_id,
          request.started_at, request.codec, request.sample_rate, sessionHash(context.account_id, request, request.started_at),
          stateHash(context.account_id, request.session_id, LISTEN_CAPTURE_OPEN_VERSION, "active", request.started_at), input.capturedAtMs ?? null],
      });
      if (result === null) fail("persistence_failed");
      return result as DeviceSessionUpload;
    },
    read: (context, sessionId) => query(context, { name: "listen.audio.read", text: "SELECT omi_memory.read_listen_audio_upload($1) AS session", values: [id(sessionId)] }),
    append(context, sessionId, index, bytes) {
      if (!Number.isSafeInteger(index) || index < 0 || index > 65535 || !(bytes instanceof Uint8Array)
        || bytes.length < 1 || bytes.length > 1048576) throw new TypeError("invalid_device_request");
      return query(context, { name: "listen.audio.append", text: "SELECT omi_memory.append_listen_audio_upload($1,$2,$3::bytea) AS session", values: [id(sessionId), index, new Uint8Array(bytes)] });
    },
    appendBatch(context, sessionId, chunks) {
      validateDeviceSessionUploadBatch(chunks);
      const encoded = chunks.map(chunk => ({ chunkIndex: chunk.index, bytesBase64: Buffer.from(chunk.bytes).toString("base64") }));
      return query(context, { name: "listen.audio.append_batch", text: "SELECT omi_memory.append_listen_audio_upload_batch($1,$2::text::jsonb) AS session", values: [id(sessionId), JSON.stringify(encoded)] });
    },
    complete: (context, sessionId) => query(context, { name: "listen.audio.complete", text: "SELECT omi_memory.complete_listen_audio_upload($1) AS session", values: [id(sessionId)] }),
  });
}

export function createPostgresDeviceTranscriptionRepository(options: PostgresListenFinalizationRepositoryOptions): DeviceTranscriptionRepository {
  const parse = (value: unknown): DeviceTranscriptionRecord | null => {
    if (value === null) return null;
    if (typeof value !== "object" || Array.isArray(value)) return fail("persistence_failed");
    const row = value as Record<string, unknown>;
    if (typeof row.sessionId !== "string" || !DEVICE_UPLOAD_SESSION_ID.test(row.sessionId)
      || !["queued", "running", "completed", "failed"].includes(String(row.state))
      || typeof row.startedAt !== "string" || !Number.isFinite(Date.parse(row.startedAt))
      || (row.errorCode !== null && typeof row.errorCode !== "string")) return fail("persistence_failed");
    return Object.freeze({ sessionId: row.sessionId, state: row.state as DeviceTranscriptionRecord["state"],
      providerResult: row.providerResult === null ? null : parsePrerecordedTranscription(row.providerResult),
      discardedLeadingPackets: integer(row.discardedLeadingPackets), errorCode: row.errorCode as string | null,
      updatedAt: integer(row.updatedAt), startedAt: new Date(row.startedAt).toISOString(), codec: integer(row.codec),
      chunkCount: integer(row.chunkCount), byteCount: integer(row.byteCount),
    });
  };
  const run = <Result>(context: AuthorizedLedgerWriteContext, callback: (connection: CheckedOutPostgresConnection) => Promise<Result>): Promise<Result> =>
    withAuthorizedSerializableConnectionTransaction(options.pool, preflight(context), async ({ authority, connection }) => {
      const result = await callback(connection);
      const rows = await connection.query<{ now: unknown }>({ name: "listen.transcription.final_clock", text: "SELECT floor(extract(epoch FROM clock_timestamp()))::bigint AS now", values: [] });
      try { assertAuthorizedLedgerWriteContextCurrentAt(authority, integer(rows[0]?.now)); }
      catch { throw new PostgresRepositoryError("expired_context"); }
      return result;
    }, options.observability ?? {});
  const id = (value: string) => { if (!DEVICE_UPLOAD_SESSION_ID.test(value)) throw new TypeError("invalid_device_request"); return value; };
  const execute = (context: AuthorizedLedgerWriteContext, name: string, query: string, values: readonly SqlValue[]) => run(context, async connection => {
    const rows = await connection.query<{ result: unknown }>({ name, text: query, values });
    if (rows.length !== 1) return fail("persistence_failed");
    return rows[0]!.result;
  });
  return Object.freeze({
    async read(context, sessionId) { return parse(await execute(context, "listen.transcription.read", "SELECT omi_memory.read_listen_audio_transcription($1) AS result", [id(sessionId)])); },
    async claim(context, sessionId, token) {
      const value = await execute(context, "listen.transcription.claim", "SELECT omi_memory.claim_listen_audio_transcription($1,$2::uuid) AS result", [id(sessionId), id(token)]);
      const result = parse(value);
      if (result === null) return null;
      const owned = (value as Record<string, unknown>).owned;
      if (typeof owned !== "boolean") return fail("persistence_failed");
      return Object.freeze({ ...result, owned });
    },
    async loadAudio(context, sessionId, token) {
      return run(context, async connection => {
        const rows = await connection.query<{ chunk_index: unknown; bytes: unknown }>({ name: "listen.transcription.audio", text: "SELECT * FROM omi_memory.load_listen_transcription_audio($1,$2::uuid)", values: [id(sessionId), id(token)] });
        let bytes = 0;
        if (rows.length > 65536) return fail("persistence_failed");
        return Object.freeze(rows.map((row, index) => {
          if (integer(row.chunk_index) !== index || !(row.bytes instanceof Uint8Array) || row.bytes.length < 1 || row.bytes.length > 1048576) return fail("persistence_failed");
          bytes += row.bytes.length;
          if (bytes > 8388608) return fail("persistence_failed");
          return new Uint8Array(row.bytes);
        }));
      });
    },
    async save(context, sessionId, token, result, discarded, error, retryable) {
      if (!Number.isSafeInteger(discarded) || discarded < 0 || discarded > 65536
        || (error !== null && !["transcription_unavailable", "invalid_audio", "invalid_transcript", "attempt_limit"].includes(error))
        || (result === null) === (error === null)) throw new TypeError("invalid_transcription");
      const saved = parse(await execute(context, "listen.transcription.save", "SELECT omi_memory.save_listen_audio_transcription($1,$2::uuid,$3::text::jsonb,$4,$5,$6) AS result",
        [id(sessionId), id(token), result === null ? null : JSON.stringify(parsePrerecordedTranscription(result)), discarded, error, retryable]));
      return saved ?? fail("persistence_failed");
    },
    async complete(context, sessionId) {
      return parse(await execute(context, "listen.transcription.complete", "SELECT omi_memory.complete_listen_audio_transcription($1) AS result", [id(sessionId)])) ?? fail("persistence_failed");
    },
    async appendSegments(context, sessionId, segments, appendedAt) {
      if (segments.length < 1 || segments.length > 128) throw new TypeError("invalid_transcription_batch");
      const requests = segments.map(segment => normalizeAppend(parseListenCaptureAppendRequest({ version: LISTEN_CAPTURE_APPEND_VERSION,
        session_id: id(sessionId), segment, appended_at: appendedAt })));
      await run(context, async connection => {
        const rows = await connection.query<Record<string, unknown>>({ name: "listen.transcription.append_segments",
          text: `SELECT appended.* FROM jsonb_array_elements($2::text::jsonb) WITH ORDINALITY AS input(value,position)
            CROSS JOIN LATERAL omi_memory.append_listen_capture_segment($1,input.value->>'id',input.value->>'text',
              (input.value->>'is_user')::boolean,(input.value->>'start')::double precision,(input.value->>'end')::double precision,
              $3::timestamptz,input.value->>'content_hash') AS appended ORDER BY input.position`,
          values: [id(sessionId), JSON.stringify(requests.map(request => ({ ...request.segment,
            content_hash: segmentHash(context.account_id, sessionId, request, request.appended_at) }))), requests[0]!.appended_at],
        });
        if (rows.length !== requests.length) fail("persistence_failed");
        for (const [index, row] of rows.entries()) {
          const appended = parseAppend([row]);
          if (appended.segment_id !== requests[index]!.segment.id) fail("persistence_failed");
        }
      });
    },
  });
}
