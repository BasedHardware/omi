import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import { isProxy } from "node:util/types";
import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import { assertAuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import {
  sealListenFormationFinalization,
} from "../../apps/service/listen/formation-ingestion";
import {
  LISTEN_FORMATION_OUTBOX_LEASE_VERSION,
  LISTEN_FORMATION_OUTBOX_PAYLOAD_VERSION,
  type ListenFormationOutboxAckOutcome,
  type ListenFormationOutboxClaimOutcome,
  type ListenFormationOutboxFailureCode,
  type ListenFormationOutboxFailureOutcome,
  type ListenFormationOutboxLease,
  type ListenFormationOutboxLoadOutcome,
  type ListenFormationOutboxRepository,
} from "../../apps/service/listen/formation-outbox-consumer";
import type { ListenSessionRecord, ListenTranscriptSegment } from "../../apps/service/stores/listen-store";
import type { CheckedOutPostgresConnection, PostgresTransactionPool } from "./connection";
import {
  PostgresRepositoryError,
  withAuthorizedSerializableConnectionTransaction,
  type PostgresTransactionObservability,
} from "./transaction";

const CAPABILITY = "memories.work.accept";
const OPEN_VERSION = "listen-capture-open-v1";
const APPEND_VERSION = "listen-capture-append-v1";
const DIGEST = /^[a-f0-9]{64}$/;

interface DeliveryPolicy {
  readonly lease_duration_seconds: number;
  readonly retry_delay_seconds: number;
  readonly max_attempts: number;
}

export interface PostgresListenFormationOutboxOptions extends DeliveryPolicy {
  readonly pool: PostgresTransactionPool;
  readonly observability?: PostgresTransactionObservability;
}

const fail = (): never => { throw new PostgresRepositoryError("persistence_failed"); };
const integer = (value: unknown): number => {
  if (typeof value === "string" && !/^(?:0|[1-9][0-9]*)$/.test(value)) return fail();
  if (typeof value !== "number" && typeof value !== "string" && typeof value !== "bigint") return fail();
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 0) return fail();
  return parsed;
};
const text = (value: unknown): string => typeof value === "string" && value.length > 0 ? value : fail();
const nullableText = (value: unknown): string | null => value === null ? null : text(value);
const digest = (value: unknown): string => {
  const parsed = text(value);
  return DIGEST.test(parsed) ? parsed : fail();
};
const timestamp = (value: unknown): string => {
  const date = value instanceof Date ? value : typeof value === "string" ? new Date(value) : null;
  if (!date || !Number.isFinite(date.getTime())) return fail();
  return date.toISOString();
};
const exactRow = (value: Record<string, unknown>, expected: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || (Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null)) return fail();
  const ownKeys = Reflect.ownKeys(value);
  if (ownKeys.some((key) => typeof key !== "string")) return fail();
  const keys = (ownKeys as string[]).sort();
  const sorted = [...expected].sort();
  if (keys.length !== sorted.length || keys.some((key, index) => key !== sorted[index])) return fail();
  const detached: Record<string, unknown> = {};
  for (const key of expected) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) return fail();
    detached[key] = descriptor.value;
  }
  return detached;
};
const preflight = (context: AuthorizedLedgerWriteContext): AuthorizedLedgerWriteContext => {
  const authorized = assertAuthorizedLedgerWriteContext(context);
  if (authorized.capability !== CAPABILITY) throw new PostgresRepositoryError("capability_denied");
  return authorized;
};

const common = (error: unknown):
  | { kind: "stale_context"; reason: string }
  | { kind: "authorization_denied"; reason: string }
  | { kind: "serialization_retryable" }
  | null => {
  if (!(error instanceof PostgresRepositoryError)) return null;
  if (["expired_context", "stale_epoch", "destination_inactive", "lifecycle_inactive"]
    .includes(error.code)) return { kind: "stale_context", reason: error.code };
  if (["credential_inactive", "grant_inactive", "capability_denied", "authorization_state_denied"]
    .includes(error.code)) return { kind: "authorization_denied", reason: error.code };
  if (error.code === "retryable_serialization") return { kind: "serialization_retryable" };
  return null;
};

const stateContent = (input: {
  account_id: string; outbox_id: string; state_revision: number; state: string;
  attempt: number; lease_fence: number; worker_id: string;
  leased_at: string | null; lease_expires_at: string | null;
  failure_code: string | null; failed_at: string | null; next_eligible_at: string | null;
  accepted_work_digest: string | null; accepted_at: string | null;
}) => Object.freeze({ contract_version: "listen-formation-delivery-state-v1", ...input });

const sessionHash = (owner: string, session: ListenSessionRecord): string => sha256CanonicalContent({
  contract_version: OPEN_VERSION,
  account_id: owner,
  session_id: session.id,
  conversation_id: session.conversationId,
  client_conversation_id: session.clientConversationId,
  started_at: session.startedAt,
  source: session.source,
  codec: session.codec,
  sample_rate: session.sampleRate,
  channels: session.channels,
});

const segmentHash = (
  owner: string,
  sessionId: string,
  segment: ListenTranscriptSegment,
  appendedAt: string,
): string => sha256CanonicalContent({
  contract_version: APPEND_VERSION,
  account_id: owner,
  session_id: sessionId,
  segment,
  appended_at: appendedAt,
});

const finalizationRowHash = (finalization: ReturnType<typeof sealListenFormationFinalization>): string =>
  sha256CanonicalContent({ contract_version: "listen-finalization-row-v1", finalization });
const payloadDigest = (finalization: ReturnType<typeof sealListenFormationFinalization>): string =>
  sha256CanonicalContent({ contract_version: "listen-formation-outbox-payload-v1", finalization });
const outboxHash = (
  owner: string,
  outboxId: string,
  finalization: ReturnType<typeof sealListenFormationFinalization>,
  payload: string,
): string => sha256CanonicalContent({
  contract_version: "listen-formation-outbox-v1",
  account_id: owner,
  outbox_id: outboxId,
  finalization_id: finalization.finalization_id,
  formation_work_id: finalization.formation_work_id,
  state: "pending",
  finalization_digest: finalization.finalization_digest,
  payload_digest: payload,
  created_at: finalization.ended_at,
});

const SELECT_KEYS = [
  "outbox_id", "finalization_id", "formation_work_id", "finalization_digest",
  "payload_digest", "previous_state_revision", "previous_state_digest",
  "previous_state", "previous_attempt", "previous_lease_expires_at", "db_now",
] as const;
const CLAIM_KEYS = ["result", "worker_id", "leased_at", "lease_expires_at", "lease_fence"] as const;
const HEAD_KEYS = [
  "finalization_id", "formation_work_id", "finalization_digest", "payload_digest",
  "state_revision", "state_digest", "state", "attempt", "lease_fence", "worker_id",
  "lease_expires_at", "failure_code", "failed_at", "next_eligible_at",
  "accepted_work_digest", "accepted_at", "db_now",
] as const;
const PAYLOAD_KEYS = [
  "outbox_id", "finalization_id", "formation_work_id", "outbox_finalization_digest",
  "payload_digest", "outbox_created_at", "outbox_content_hash", "session_id",
  "conversation_id", "client_conversation_id", "terminal_status", "capture_completeness",
  "started_at", "ended_at", "source", "codec", "sample_rate", "channels",
  "session_content_hash", "segment_count", "transcript_digest", "finalization_digest",
  "finalization_content_hash", "segment_ordinal", "segment_id", "text_content", "is_user",
  "start_seconds", "end_seconds", "appended_at", "segment_content_hash",
] as const;

const parseLease = (
  owner: string,
  selected: Record<string, unknown>,
  claimed: Record<string, unknown>,
): Readonly<ListenFormationOutboxLease> => {
  exactRow(selected, SELECT_KEYS); exactRow(claimed, CLAIM_KEYS);
  if (claimed.result !== "claimed") return fail();
  return Object.freeze({
    version: LISTEN_FORMATION_OUTBOX_LEASE_VERSION,
    owner_account_id: owner,
    outbox_id: text(selected.outbox_id),
    finalization_id: text(selected.finalization_id),
    formation_work_id: text(selected.formation_work_id),
    finalization_digest: digest(selected.finalization_digest),
    payload_digest: digest(selected.payload_digest),
    lease_fence: integer(claimed.lease_fence),
  });
};

const assertLease = (context: AuthorizedLedgerWriteContext, lease: Readonly<ListenFormationOutboxLease>) => {
  if (lease.version !== LISTEN_FORMATION_OUTBOX_LEASE_VERSION
    || lease.owner_account_id !== context.account_id || !Number.isSafeInteger(lease.lease_fence)
    || lease.lease_fence < 1 || !DIGEST.test(lease.finalization_digest)
    || !DIGEST.test(lease.payload_digest)) throw new PostgresRepositoryError("transition_invalid");
};

const parsePayload = (
  owner: string,
  lease: Readonly<ListenFormationOutboxLease>,
  rows: readonly Record<string, unknown>[],
): Extract<ListenFormationOutboxLoadOutcome, { kind: "found" }> => {
  if (rows.length < 1 || rows.length > 4_096) return fail();
  const first = exactRow(rows[0]!, PAYLOAD_KEYS);
  const sessionId = text(first.session_id);
  const startedAt = timestamp(first.started_at);
  const endedAt = timestamp(first.ended_at);
  const session: ListenSessionRecord = Object.freeze({
    id: sessionId,
    conversationId: text(first.conversation_id),
    clientConversationId: nullableText(first.client_conversation_id),
    startedAt,
    updatedAt: endedAt,
    endedAt,
    status: text(first.terminal_status) as "completed" | "entitlement_exhausted",
    source: nullableText(first.source),
    codec: text(first.codec),
    sampleRate: integer(first.sample_rate),
    channels: integer(first.channels),
  });
  if (!['completed', 'entitlement_exhausted'].includes(session.status)
    || digest(first.session_content_hash) !== sessionHash(owner, session)) return fail();
  const segments: ListenTranscriptSegment[] = [];
  for (let index = 0; index < rows.length; index += 1) {
    const row = index === 0 ? first : exactRow(rows[index]!, PAYLOAD_KEYS);
    if (text(row.outbox_id) !== lease.outbox_id || text(row.finalization_id) !== lease.finalization_id
      || text(row.formation_work_id) !== lease.formation_work_id || text(row.session_id) !== sessionId
      || timestamp(row.started_at) !== startedAt || timestamp(row.ended_at) !== endedAt
      || integer(row.segment_ordinal) !== index || typeof row.text_content !== "string"
      || typeof row.is_user !== "boolean" || typeof row.start_seconds !== "number"
      || typeof row.end_seconds !== "number") return fail();
    const segment = Object.freeze({
      id: text(row.segment_id), text: row.text_content,
      is_user: row.is_user, start: row.start_seconds, end: row.end_seconds,
    });
    if (digest(row.segment_content_hash) !== segmentHash(owner, sessionId, segment, timestamp(row.appended_at))) {
      return fail();
    }
    segments.push(segment);
  }
  if (integer(first.segment_count) !== segments.length) return fail();
  const finalization = sealListenFormationFinalization({ owner_account_id: owner, session, segments });
  const computedPayload = payloadDigest(finalization);
  if (finalization.finalization_id !== lease.finalization_id
    || finalization.formation_work_id !== lease.formation_work_id
    || finalization.finalization_digest !== lease.finalization_digest
    || text(first.capture_completeness) !== finalization.capture_completeness
    || digest(first.transcript_digest) !== finalization.transcript_digest
    || digest(first.finalization_digest) !== finalization.finalization_digest
    || digest(first.outbox_finalization_digest) !== finalization.finalization_digest
    || digest(first.finalization_content_hash) !== finalizationRowHash(finalization)
    || computedPayload !== lease.payload_digest || digest(first.payload_digest) !== computedPayload
    || timestamp(first.outbox_created_at) !== finalization.ended_at
    || digest(first.outbox_content_hash) !== outboxHash(owner, lease.outbox_id, finalization, computedPayload)) {
    return fail();
  }
  return Object.freeze({ kind: "found" as const, payload: Object.freeze({
    version: LISTEN_FORMATION_OUTBOX_PAYLOAD_VERSION,
    owner_account_id: owner, outbox_id: lease.outbox_id,
    finalization_id: lease.finalization_id, formation_work_id: lease.formation_work_id,
    finalization_digest: lease.finalization_digest, payload_digest: lease.payload_digest,
    finalization,
  }) });
};

const policy = (options: PostgresListenFormationOutboxOptions): DeliveryPolicy => {
  const values = [options.lease_duration_seconds, options.retry_delay_seconds, options.max_attempts];
  if (values.some((value) => !Number.isSafeInteger(value) || value < 1)
    || options.lease_duration_seconds > 3_600 || options.retry_delay_seconds > 86_400
    || options.max_attempts > 100) throw new TypeError("postgres listen outbox invalid_policy");
  return Object.freeze({
    lease_duration_seconds: options.lease_duration_seconds,
    retry_delay_seconds: options.retry_delay_seconds,
    max_attempts: options.max_attempts,
  });
};

export const createPostgresListenFormationOutboxRepository = (
  options: PostgresListenFormationOutboxOptions,
): ListenFormationOutboxRepository => {
  const deliveryPolicy = policy(options);
  const run = <Result>(context: AuthorizedLedgerWriteContext, callback: (
    authority: AuthorizedLedgerWriteContext,
    connection: CheckedOutPostgresConnection,
  ) => Promise<Result>): Promise<Result> => withAuthorizedSerializableConnectionTransaction(
    options.pool, preflight(context), ({ authority, connection }) => callback(authority, connection),
    options.observability ?? {},
  );

  const head = async (connection: CheckedOutPostgresConnection, outboxId: string) => {
    const rows = await connection.query<Record<string, unknown>>({
      name: "listen.delivery.head",
      text: "SELECT * FROM omi_memory.read_listen_formation_delivery_head($1)",
      values: [outboxId],
    });
    if (rows.length !== 1) return fail();
    return exactRow(rows[0]!, HEAD_KEYS);
  };

  const assertHeadCoordinates = (
    lease: Readonly<ListenFormationOutboxLease>,
    current: Record<string, unknown>,
  ): void => {
    if (text(current.finalization_id) !== lease.finalization_id
      || text(current.formation_work_id) !== lease.formation_work_id
      || digest(current.finalization_digest) !== lease.finalization_digest
      || digest(current.payload_digest) !== lease.payload_digest) fail();
  };

  const appendOutcome = async (
    connection: CheckedOutPostgresConnection,
    owner: string,
    lease: Readonly<ListenFormationOutboxLease>,
    current: Record<string, unknown>,
    state: "retryable_failed" | "dead_letter" | "accepted",
    failureCode: ListenFormationOutboxFailureCode | null,
    acceptedWorkDigest: string | null,
  ) => {
    assertHeadCoordinates(lease, current);
    const now = timestamp(current.db_now);
    const nextEligible = state === "retryable_failed"
      ? new Date(Date.parse(now) + deliveryPolicy.retry_delay_seconds * 1_000).toISOString() : null;
    const record = stateContent({
      account_id: owner, outbox_id: lease.outbox_id,
      state_revision: integer(current.state_revision) + 1, state,
      attempt: integer(current.attempt), lease_fence: lease.lease_fence,
      worker_id: text(current.worker_id), leased_at: null, lease_expires_at: null,
      failure_code: failureCode, failed_at: state === "accepted" ? null : now,
      next_eligible_at: nextEligible, accepted_work_digest: acceptedWorkDigest,
      accepted_at: state === "accepted" ? now : null,
    });
    const stateDigest = sha256CanonicalContent(record);
    const result = await connection.query<Record<string, unknown>>({
      name: "listen.delivery.outcome",
      text: `SELECT * FROM omi_memory.append_listen_formation_delivery_outcome(
        $1, $2, $3, $4, $5, $6, $7::timestamptz, $8, $9, $10)`,
      values: [lease.outbox_id, integer(current.state_revision), digest(current.state_digest),
        lease.lease_fence, state, failureCode, nextEligible, acceptedWorkDigest,
        stateDigest, sha256CanonicalContent(record)],
    });
    if (result.length !== 1 || result[0]?.result !== "recorded"
      || integer(result[0].state_revision) !== record.state_revision
      || digest(result[0].state_digest) !== stateDigest) return fail();
  };

  return Object.freeze({
    async claimNext(context: AuthorizedLedgerWriteContext): Promise<ListenFormationOutboxClaimOutcome> {
      try {
        return await run(context, async (authority, connection) => {
          const selected = await connection.query<Record<string, unknown>>({
            name: "listen.delivery.select", text: "SELECT * FROM omi_memory.select_next_listen_formation_delivery()", values: [],
          });
          if (selected.length === 0) return Object.freeze({ kind: "none_available" as const });
          if (selected.length !== 1) return fail();
          const row = exactRow(selected[0]!, SELECT_KEYS);
          const now = timestamp(row.db_now);
          const previousRevision = row.previous_state_revision === null ? null : integer(row.previous_state_revision);
          const previousAttempt = row.previous_attempt === null ? 0 : integer(row.previous_attempt);
          const revision = (previousRevision ?? 0) + 1;
          const attempt = previousAttempt + 1;
          const expires = new Date(Date.parse(now) + deliveryPolicy.lease_duration_seconds * 1_000).toISOString();
          const record = stateContent({
            account_id: authority.account_id, outbox_id: text(row.outbox_id), state_revision: revision,
            state: "leased", attempt, lease_fence: attempt, worker_id: authority.principal_id,
            leased_at: now, lease_expires_at: expires, failure_code: null, failed_at: null,
            next_eligible_at: null, accepted_work_digest: null, accepted_at: null,
          });
          const stateDigest = sha256CanonicalContent(record);
          const claimed = await connection.query<Record<string, unknown>>({
            name: "listen.delivery.claim",
            text: `SELECT * FROM omi_memory.claim_listen_formation_delivery(
              $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::timestamptz,$12)`,
            values: [text(row.outbox_id), text(row.finalization_id), text(row.formation_work_id),
              digest(row.finalization_digest), digest(row.payload_digest), previousRevision,
              row.previous_state_digest === null ? null : digest(row.previous_state_digest), revision, stateDigest, attempt, expires,
              sha256CanonicalContent(record)],
          });
          if (claimed.length !== 1) return fail();
          const lease = parseLease(authority.account_id, row, claimed[0]!);
          if (text(claimed[0]!.worker_id) !== authority.principal_id
            || timestamp(claimed[0]!.leased_at) !== now
            || timestamp(claimed[0]!.lease_expires_at) !== expires) return fail();
          return Object.freeze({ kind: "claimed" as const, lease });
        });
      } catch (error) {
        const mapped = common(error); if (mapped) return mapped;
        if (error instanceof PostgresRepositoryError && error.code === "transition_invalid") {
          return Object.freeze({ kind: "serialization_retryable" as const });
        }
        throw new PostgresRepositoryError("persistence_failed");
      }
    },

    async load(
      context: AuthorizedLedgerWriteContext,
      lease: Readonly<ListenFormationOutboxLease>,
    ): Promise<ListenFormationOutboxLoadOutcome> {
      try {
        assertLease(preflight(context), lease);
        return await run(context, async (authority, connection) => {
          const rows = await connection.query<Record<string, unknown>>({
            name: "listen.delivery.payload",
            text: "SELECT * FROM omi_memory.read_listen_formation_delivery_payload($1,$2)",
            values: [lease.outbox_id, lease.lease_fence],
          });
          return parsePayload(authority.account_id, lease, rows);
        });
      } catch (error) {
        const mapped = common(error); if (mapped) return mapped;
        if (error instanceof PostgresRepositoryError && error.code === "transition_invalid") {
          return Object.freeze({ kind: "stale_lease" as const });
        }
        throw new PostgresRepositoryError("persistence_failed");
      }
    },

    async markAccepted(
      context: AuthorizedLedgerWriteContext,
      lease: Readonly<ListenFormationOutboxLease>,
      request: Parameters<ListenFormationOutboxRepository["markAccepted"]>[2],
    ): Promise<ListenFormationOutboxAckOutcome> {
      try {
        const authority = preflight(context); assertLease(authority, lease);
        if (!DIGEST.test(request.accepted_work_digest)) return Object.freeze({ kind: "idempotency_conflict" as const });
        return await run(context, async (authorized, connection) => {
          const current = await head(connection, lease.outbox_id);
          assertHeadCoordinates(lease, current);
          if (text(current.state) === "accepted") {
            return Object.freeze({ kind: digest(current.accepted_work_digest) === request.accepted_work_digest
              ? "replayed" as const : "idempotency_conflict" as const });
          }
          if (text(current.state) !== "leased" || integer(current.lease_fence) !== lease.lease_fence
            || text(current.worker_id) !== authorized.principal_id
            || Date.parse(timestamp(current.lease_expires_at)) <= Date.parse(timestamp(current.db_now))) {
            return Object.freeze({ kind: "stale_lease" as const });
          }
          await appendOutcome(connection, authorized.account_id, lease, current, "accepted", null, request.accepted_work_digest);
          return Object.freeze({ kind: "accepted" as const });
        });
      } catch (error) {
        const mapped = common(error); if (mapped) return mapped;
        if (error instanceof PostgresRepositoryError && error.code === "transition_invalid") {
          return Object.freeze({ kind: "stale_lease" as const });
        }
        throw new PostgresRepositoryError("persistence_failed");
      }
    },

    async recordFailure(
      context: AuthorizedLedgerWriteContext,
      lease: Readonly<ListenFormationOutboxLease>,
      request: Parameters<ListenFormationOutboxRepository["recordFailure"]>[2],
    ): Promise<ListenFormationOutboxFailureOutcome> {
      try {
        const authority = preflight(context); assertLease(authority, lease);
        return await run(context, async (authorized, connection) => {
          const current = await head(connection, lease.outbox_id);
          assertHeadCoordinates(lease, current);
          const state = text(current.state);
          if (state === "retryable_failed" || state === "dead_letter") {
            return Object.freeze({ kind: text(current.failure_code) === request.code
              ? "replayed" as const : "idempotency_conflict" as const });
          }
          if (state !== "leased" || integer(current.lease_fence) !== lease.lease_fence
            || text(current.worker_id) !== authorized.principal_id
            || Date.parse(timestamp(current.lease_expires_at)) <= Date.parse(timestamp(current.db_now))) {
            return Object.freeze({ kind: "stale_lease" as const });
          }
          const nextState = integer(current.attempt) >= deliveryPolicy.max_attempts
            ? "dead_letter" as const : "retryable_failed" as const;
          await appendOutcome(connection, authorized.account_id, lease, current, nextState, request.code, null);
          return Object.freeze({ kind: "recorded" as const });
        });
      } catch (error) {
        const mapped = common(error); if (mapped) return mapped;
        if (error instanceof PostgresRepositoryError && error.code === "transition_invalid") {
          return Object.freeze({ kind: "stale_lease" as const });
        }
        throw new PostgresRepositoryError("persistence_failed");
      }
    },
  });
};
