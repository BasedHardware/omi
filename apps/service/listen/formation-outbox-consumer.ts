import { isProxy } from "node:util/types";

import type {
  AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import { assertAuthorizedLedgerWriteContext } from "../auth/authorized-context";
import type {
  ListenFormationFinalization,
  ListenFormationIngestionRequest,
  ListenFormationIngestionOutcome,
  ListenFormationIngestionPort,
} from "./formation-ingestion";

const CONSUMER_PORT: unique symbol = Symbol("listen-formation-outbox-consumer");
export const LISTEN_FORMATION_OUTBOX_LEASE_VERSION =
  "listen-formation-outbox-lease-v1" as const;
export const LISTEN_FORMATION_OUTBOX_PAYLOAD_VERSION =
  "listen-formation-outbox-payload-v1" as const;

const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;

export interface ListenFormationOutboxLease {
  readonly version: typeof LISTEN_FORMATION_OUTBOX_LEASE_VERSION;
  readonly owner_account_id: string;
  readonly outbox_id: string;
  readonly finalization_id: string;
  readonly formation_work_id: string;
  readonly finalization_digest: string;
  readonly payload_digest: string;
  readonly lease_fence: number;
}

export interface ListenFormationOutboxPayload {
  readonly version: typeof LISTEN_FORMATION_OUTBOX_PAYLOAD_VERSION;
  readonly owner_account_id: string;
  readonly outbox_id: string;
  readonly finalization_id: string;
  readonly formation_work_id: string;
  readonly finalization_digest: string;
  readonly payload_digest: string;
  readonly finalization: Readonly<ListenFormationFinalization>;
}

export type ListenFormationOutboxClaimOutcome =
  | Readonly<{ kind: "claimed"; lease: Readonly<ListenFormationOutboxLease> }>
  | Readonly<{ kind: "none_available" }>
  | Readonly<{ kind: "stale_context"; reason: string }>
  | Readonly<{ kind: "authorization_denied"; reason: string }>
  | Readonly<{ kind: "serialization_retryable" }>;

export type ListenFormationOutboxLoadOutcome =
  | Readonly<{ kind: "found"; payload: Readonly<ListenFormationOutboxPayload> }>
  | Readonly<{ kind: "not_found" | "stale_lease" | "ineligible_state" }>
  | Readonly<{ kind: "stale_context"; reason: string }>
  | Readonly<{ kind: "authorization_denied"; reason: string }>
  | Readonly<{ kind: "serialization_retryable" }>;

export type ListenFormationOutboxAckOutcome =
  | Readonly<{ kind: "accepted" | "replayed" }>
  | Readonly<{ kind: "stale_lease" | "ineligible_state" | "idempotency_conflict" }>
  | Readonly<{ kind: "stale_context"; reason: string }>
  | Readonly<{ kind: "authorization_denied"; reason: string }>
  | Readonly<{ kind: "serialization_retryable" }>;

export type ListenFormationOutboxFailureCode =
  | "dependency_unavailable"
  | "serialization_retryable"
  | "payload_invalid"
  | "formation_ineligible"
  | "acceptance_conflict";

export type ListenFormationOutboxFailureOutcome =
  | Readonly<{ kind: "recorded" | "replayed" }>
  | Readonly<{ kind: "stale_lease" | "ineligible_state" | "idempotency_conflict" }>
  | Readonly<{ kind: "stale_context"; reason: string }>
  | Readonly<{ kind: "authorization_denied"; reason: string }>
  | Readonly<{ kind: "serialization_retryable" }>;

export interface ListenFormationOutboxRepository {
  claimNext(context: AuthorizedLedgerWriteContext): Promise<ListenFormationOutboxClaimOutcome>;
  load(
    context: AuthorizedLedgerWriteContext,
    lease: Readonly<ListenFormationOutboxLease>,
  ): Promise<ListenFormationOutboxLoadOutcome>;
  markAccepted(
    context: AuthorizedLedgerWriteContext,
    lease: Readonly<ListenFormationOutboxLease>,
    request: Readonly<{ accepted_work_digest: string }>,
  ): Promise<ListenFormationOutboxAckOutcome>;
  recordFailure(
    context: AuthorizedLedgerWriteContext,
    lease: Readonly<ListenFormationOutboxLease>,
    request: Readonly<{ code: ListenFormationOutboxFailureCode }>,
  ): Promise<ListenFormationOutboxFailureOutcome>;
}

/** Loads every versioned coordinate needed for formation from durable state. */
export type ListenFormationIngestionRequestLoader = (
  context: AuthorizedLedgerWriteContext,
  payload: Readonly<ListenFormationOutboxPayload>,
) => Promise<Readonly<ListenFormationIngestionRequest>>;

export type ListenFormationOutboxConsumerStopCode =
  | "authorization_or_context"
  | "storage_retryable"
  | "stale_lease"
  | "ineligible_state"
  | "idempotency_conflict"
  | "invalid_lease"
  | "invalid_payload";

export type ListenFormationOutboxConsumerOutcome =
  | Readonly<{ kind: "idle"; leased: 0; formation_calls: 0 }>
  | Readonly<{
      kind: "accepted";
      result: "accepted" | "replayed";
      leased: 1;
      formation_calls: 1;
    }>
  | Readonly<{
      kind: "failed";
      leased: 1;
      formation_calls: 0 | 1;
    }>
  | Readonly<{
      kind: "stopped";
      stop_code: ListenFormationOutboxConsumerStopCode;
      leased: 0 | 1;
      formation_calls: 0 | 1;
    }>;

export interface ListenFormationOutboxConsumer {
  readonly [CONSUMER_PORT]: true;
  runNext(context: AuthorizedLedgerWriteContext): Promise<ListenFormationOutboxConsumerOutcome>;
}

const fail = (code: string): never => {
  throw new TypeError(`listen formation outbox consumer ${code}`);
};

const exactRecord = (
  value: unknown,
  keys: readonly string[],
  code: string,
): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const objectValue = value as object;
  const ownKeys = Reflect.ownKeys(objectValue);
  const actual = ownKeys.filter((key): key is string => typeof key === "string").sort();
  if (actual.length !== ownKeys.length || actual.length !== keys.length
    || actual.some((key, index) => key !== [...keys].sort()[index])) fail(code);
  const output: Record<string, unknown> = {};
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(objectValue, key);
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
    output[key] = (descriptor as PropertyDescriptor & { readonly value: unknown }).value;
  }
  return output;
};

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value as string;
};

const digest = (value: unknown, code: string): string => {
  const result = token(value, code);
  if (!DIGEST.test(result)) fail(code);
  return result;
};

const ownDataValue = (value: unknown, key: string, code: string): unknown => {
  if (value === null || typeof value !== "object") fail(code);
  const objectValue = value as object;
  if (isProxy(objectValue)) fail(code);
  const descriptor = Object.getOwnPropertyDescriptor(objectValue, key);
  if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
  return (descriptor as PropertyDescriptor & { readonly value: unknown }).value;
};

const nonnegativeInteger = (value: unknown, code: string): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0) fail(code);
  return value as number;
};

const leaseFence = (value: unknown, code: string): number => {
  const result = nonnegativeInteger(value, code);
  if (result < 1) fail(code);
  return result;
};

const parseLease = (value: unknown): Readonly<ListenFormationOutboxLease> => {
  const input = exactRecord(value, [
    "version", "owner_account_id", "outbox_id", "finalization_id", "formation_work_id",
    "finalization_digest", "payload_digest", "lease_fence",
  ], "invalid_lease");
  if (input["version"] !== LISTEN_FORMATION_OUTBOX_LEASE_VERSION) fail("invalid_lease");
  return Object.freeze({
    version: LISTEN_FORMATION_OUTBOX_LEASE_VERSION,
    owner_account_id: token(input["owner_account_id"], "invalid_lease"),
    outbox_id: token(input["outbox_id"], "invalid_lease"),
    finalization_id: token(input["finalization_id"], "invalid_lease"),
    formation_work_id: token(input["formation_work_id"], "invalid_lease"),
    finalization_digest: digest(input["finalization_digest"], "invalid_lease"),
    payload_digest: digest(input["payload_digest"], "invalid_lease"),
    lease_fence: leaseFence(input["lease_fence"], "invalid_lease"),
  });
};

const parsePayload = (value: unknown): Readonly<ListenFormationOutboxPayload> => {
  const input = exactRecord(value, [
    "version", "owner_account_id", "outbox_id", "finalization_id", "formation_work_id",
    "finalization_digest", "payload_digest", "finalization",
  ], "invalid_payload");
  if (input["version"] !== LISTEN_FORMATION_OUTBOX_PAYLOAD_VERSION) fail("invalid_payload");
  return Object.freeze({
    version: LISTEN_FORMATION_OUTBOX_PAYLOAD_VERSION,
    owner_account_id: token(input["owner_account_id"], "invalid_payload"),
    outbox_id: token(input["outbox_id"], "invalid_payload"),
    finalization_id: token(input["finalization_id"], "invalid_payload"),
    formation_work_id: token(input["formation_work_id"], "invalid_payload"),
    finalization_digest: digest(input["finalization_digest"], "invalid_payload"),
    payload_digest: digest(input["payload_digest"], "invalid_payload"),
    finalization: input["finalization"] as ListenFormationFinalization,
  });
};

const stopped = (
  stop_code: ListenFormationOutboxConsumerStopCode,
  leased: 0 | 1,
  formation_calls: 0 | 1 = 0,
): Extract<ListenFormationOutboxConsumerOutcome, { kind: "stopped" }> => Object.freeze({
  kind: "stopped" as const, stop_code, leased, formation_calls,
});

const mapRepositoryStop = (
  outcome: { readonly kind: string },
  leased: 0 | 1,
): Extract<ListenFormationOutboxConsumerOutcome, { kind: "stopped" }> | null => {
  if (outcome.kind === "serialization_retryable") return stopped("storage_retryable", leased);
  if (outcome.kind === "stale_context" || outcome.kind === "authorization_denied") {
    return stopped("authorization_or_context", leased);
  }
  if (outcome.kind === "stale_lease") return stopped("stale_lease", leased);
  if (outcome.kind === "idempotency_conflict") return stopped("idempotency_conflict", leased);
  if (outcome.kind === "not_found" || outcome.kind === "ineligible_state") {
    return stopped("ineligible_state", leased);
  }
  return null;
};

const recordFailure = async (
  recordFailureFn: ListenFormationOutboxRepository["recordFailure"],
  repository: ListenFormationOutboxRepository,
  context: AuthorizedLedgerWriteContext,
  lease: Readonly<ListenFormationOutboxLease>,
  code: ListenFormationOutboxFailureCode,
  formationCalls: 0 | 1,
): Promise<ListenFormationOutboxConsumerOutcome> => {
  try {
    const recorded = await recordFailureFn.call(repository, context, lease, { code });
    const stop = mapRepositoryStop(recorded, 1);
    if (stop) return stopped(stop.stop_code, 1, formationCalls);
    if (recorded.kind === "recorded" || recorded.kind === "replayed") {
      return Object.freeze({
        kind: "failed" as const,
        leased: 1 as const,
        formation_calls: formationCalls,
      });
    }
    return stopped("storage_retryable", 1, formationCalls);
  } catch {
    return stopped("storage_retryable", 1, formationCalls);
  }
};

export interface ListenFormationOutboxConsumerDependencies {
  readonly repository: ListenFormationOutboxRepository;
  readonly load_ingestion_request: ListenFormationIngestionRequestLoader;
  readonly formation: ListenFormationIngestionPort;
}

/**
 * One bounded outbox delivery attempt. Construction starts no timer/poller,
 * chooses no model/policy/default, and does not mint authority. A lease is an
 * operational duplicate bound; exact formation acceptance remains the replay
 * arbiter after a crash between acceptance and acknowledgement.
 */
export const defineListenFormationOutboxConsumer = (
  dependencies: ListenFormationOutboxConsumerDependencies,
): ListenFormationOutboxConsumer => {
  if (dependencies === null || typeof dependencies !== "object" || Array.isArray(dependencies)
    || isProxy(dependencies) || Object.getPrototypeOf(dependencies) !== Object.prototype) {
    fail("invalid_dependencies");
  }
  const keys = ["repository", "load_ingestion_request", "formation"];
  const actual = Reflect.ownKeys(dependencies);
  if (actual.length !== keys.length || actual.some((key) => typeof key !== "string")
    || (actual as string[]).sort().some((key, index) => key !== [...keys].sort()[index])) {
    fail("invalid_dependencies");
  }
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(dependencies, key);
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail("invalid_dependencies");
  }
  if (dependencies.repository === null || typeof dependencies.repository !== "object"
    || isProxy(dependencies.repository)) fail("invalid_repository");
  for (const key of ["claimNext", "load", "markAccepted", "recordFailure"]) {
    const descriptor = Object.getOwnPropertyDescriptor(dependencies.repository, key);
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)
      || typeof descriptor.value !== "function" || isProxy(descriptor.value)) {
      fail("invalid_repository");
    }
  }
  const loaderDescriptor = Object.getOwnPropertyDescriptor(dependencies, "load_ingestion_request");
  if (!loaderDescriptor || !("value" in loaderDescriptor)
    || typeof loaderDescriptor.value !== "function" || isProxy(loaderDescriptor.value)) fail("invalid_loader");
  if (dependencies.formation === null || typeof dependencies.formation !== "object"
    || isProxy(dependencies.formation)) {
    fail("invalid_formation");
  }
  const acceptDescriptor = Object.getOwnPropertyDescriptor(dependencies.formation, "accept");
  if (!acceptDescriptor || !("value" in acceptDescriptor)
    || typeof acceptDescriptor.value !== "function" || isProxy(acceptDescriptor.value)) fail("invalid_formation");
  const claimNext = Object.getOwnPropertyDescriptor(dependencies.repository, "claimNext")!.value as ListenFormationOutboxRepository["claimNext"];
  const load = Object.getOwnPropertyDescriptor(dependencies.repository, "load")!.value as ListenFormationOutboxRepository["load"];
  const markAccepted = Object.getOwnPropertyDescriptor(dependencies.repository, "markAccepted")!.value as ListenFormationOutboxRepository["markAccepted"];
  const recordFailureFn = Object.getOwnPropertyDescriptor(dependencies.repository, "recordFailure")!.value as ListenFormationOutboxRepository["recordFailure"];
  const loadIngestionRequest = loaderDescriptor!.value as ListenFormationIngestionRequestLoader;
  const acceptFormation = acceptDescriptor!.value as ListenFormationIngestionPort["accept"];
  return Object.freeze({
    [CONSUMER_PORT]: true as const,
    async runNext(contextValue: AuthorizedLedgerWriteContext): Promise<ListenFormationOutboxConsumerOutcome> {
      let context: AuthorizedLedgerWriteContext;
      try { context = assertAuthorizedLedgerWriteContext(contextValue); }
      catch { return stopped("authorization_or_context", 0); }
      if (context.capability !== "memories.work.accept") return stopped("authorization_or_context", 0);

      let claim: ListenFormationOutboxClaimOutcome;
      try { claim = await claimNext.call(dependencies.repository, context); }
      catch { return stopped("storage_retryable", 0); }
      const claimStop = mapRepositoryStop(claim, 0);
      if (claimStop) return claimStop;
      if (claim.kind === "none_available") {
        return Object.freeze({ kind: "idle" as const, leased: 0 as const, formation_calls: 0 as const });
      }
      if (claim.kind !== "claimed") return stopped("invalid_lease", 0);

      let lease: Readonly<ListenFormationOutboxLease>;
      try {
        lease = parseLease(claim.lease);
        if (lease.owner_account_id !== context.account_id) fail("invalid_lease");
      } catch { return stopped("invalid_lease", 1); }

      let loaded: ListenFormationOutboxLoadOutcome;
      try { loaded = await load.call(dependencies.repository, context, lease); }
      catch { return stopped("storage_retryable", 1); }
      const loadStop = mapRepositoryStop(loaded, 1);
      if (loadStop) return loadStop;
      if (loaded.kind !== "found") return stopped("invalid_payload", 1);

      let payload: Readonly<ListenFormationOutboxPayload>;
      try {
        payload = parsePayload(loaded.payload);
        if (payload.owner_account_id !== lease.owner_account_id
          || payload.outbox_id !== lease.outbox_id
          || payload.finalization_id !== lease.finalization_id
          || payload.formation_work_id !== lease.formation_work_id
          || payload.finalization_digest !== lease.finalization_digest
          || payload.payload_digest !== lease.payload_digest) fail("invalid_payload");
      } catch {
        return recordFailure(recordFailureFn, dependencies.repository, context, lease, "payload_invalid", 0);
      }

      let ingestionRequest: Readonly<ListenFormationIngestionRequest>;
      try {
        const request = await loadIngestionRequest(context, payload);
        const values = exactRecord(request, [
          "finalization", "graph_snapshot", "source_language", "account_timezone",
          "reference_clock_query_at", "policy_version", "predicate_alias_generation",
          "authorization_generation", "stm_generation", "strategy_assignment",
          "execution_policy", "accepted_at_event_time",
        ], "invalid_ingestion_request");
        const requestFinalization = values["finalization"];
        const graph = values["graph_snapshot"];
        if (ownDataValue(requestFinalization, "finalization_id", "invalid_ingestion_request")
            !== payload.finalization_id
          || ownDataValue(requestFinalization, "formation_work_id", "invalid_ingestion_request")
            !== payload.formation_work_id
          || ownDataValue(requestFinalization, "finalization_digest", "invalid_ingestion_request")
            !== payload.finalization_digest
          || ownDataValue(graph, "owner_account_id", "invalid_ingestion_request")
            !== context.account_id) fail("invalid_ingestion_request");
        ingestionRequest = request;
      } catch {
        return recordFailure(recordFailureFn, dependencies.repository, context, lease, "dependency_unavailable", 0);
      }

      let accepted: ListenFormationIngestionOutcome;
      try {
        accepted = await acceptFormation.call(dependencies.formation, context, ingestionRequest);
      } catch {
        return recordFailure(recordFailureFn, dependencies.repository, context, lease, "dependency_unavailable", 1);
      }
      if (accepted.kind === "ineligible") {
        return recordFailure(recordFailureFn, dependencies.repository, context, lease, "formation_ineligible", 1);
      }
      if (accepted.kind === "idempotency_conflict") {
        return recordFailure(recordFailureFn, dependencies.repository, context, lease, "acceptance_conflict", 1);
      }
      if (accepted.kind === "serialization_retryable") {
        return recordFailure(recordFailureFn, dependencies.repository, context, lease, "serialization_retryable", 1);
      }
      if (accepted.kind === "stale_context" || accepted.kind === "authorization_denied") {
        return stopped("authorization_or_context", 1, 1);
      }
      if (accepted.kind !== "accepted" && accepted.kind !== "replayed") {
        return recordFailure(recordFailureFn, dependencies.repository, context, lease, "dependency_unavailable", 1);
      }

      let acceptedWorkDigest: string;
      try {
        const acceptedWork = accepted as Extract<ListenFormationIngestionOutcome, { kind: "accepted" | "replayed" }>;
        const acceptedJob = ownDataValue(acceptedWork, "job", "invalid_acceptance");
        acceptedWorkDigest = digest(
          ownDataValue(acceptedJob, "accepted_work_digest", "invalid_acceptance"),
          "invalid_acceptance",
        );
      } catch {
        return recordFailure(recordFailureFn, dependencies.repository, context, lease, "acceptance_conflict", 1);
      }
      let ack: ListenFormationOutboxAckOutcome;
      try {
        ack = await markAccepted.call(dependencies.repository, context, lease, {
          accepted_work_digest: acceptedWorkDigest,
        });
      } catch { return stopped("storage_retryable", 1, 1); }
      const ackStop = mapRepositoryStop(ack, 1);
      if (ackStop) return stopped(ackStop.stop_code, 1, 1);
      if (ack.kind !== "accepted" && ack.kind !== "replayed") {
        if (ack.kind === "idempotency_conflict") return stopped("idempotency_conflict", 1, 1);
        return stopped("storage_retryable", 1, 1);
      }
      return Object.freeze({
        kind: "accepted" as const,
        result: accepted.kind,
        leased: 1 as const,
        formation_calls: 1 as const,
      });
    },
  });
};
