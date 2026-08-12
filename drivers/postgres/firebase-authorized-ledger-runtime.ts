import { isProxy } from "node:util/types";

import {
  composeFirebaseMemoryAuthorization,
} from "../../apps/service/composition/firebase-memory-authorization";
import type { FirebaseIdentityRuntimeMode, FirebaseIdTokenVerificationAdapter } from
  "../../apps/service/auth/firebase-identity";
import type {
  AuthoritativeLedgerAppend,
  AuthoritativeLedgerAppendOutcome,
} from "../../apps/service/stores/authoritative-ledger-repository";
import { createPostgresApplicationAccountControlSource } from
  "./application-account-control-source";
import { createPostgresAuthoritativeLedgerRepository } from
  "./authoritative-ledger-repository";
import type { PostgresTransactionPool, SqlStatement } from "./connection";
import { createPostgresFirebaseApplicationAuthorizationSource } from
  "./firebase-application-authorization-source";

const RUNTIME_PORT: unique symbol = Symbol("postgres-firebase-authorized-ledger-runtime");

export interface PostgresFirebaseAuthorizedLedgerRuntimeOptions {
  readonly pool: PostgresTransactionPool;
  readonly project_id: string;
  readonly runtime_mode: FirebaseIdentityRuntimeMode;
  readonly id_token_adapter: FirebaseIdTokenVerificationAdapter;
  readonly application_id: string;
  readonly context_ttl_seconds: number;
}

export type FirebaseAuthorizedLedgerAppendOutcome =
  | Readonly<{
      kind: "denied";
      outcome: "authentication" | "authorization" | "stale_epoch" | "unavailable";
    }>
  | Readonly<{ kind: "completed"; outcome: AuthoritativeLedgerAppendOutcome }>
  | Readonly<{ kind: "unavailable" }>;

export interface PostgresFirebaseAuthorizedLedgerRuntime {
  readonly [RUNTIME_PORT]: true;
  append(
    idToken: string,
    nowEpochSeconds: number,
    request: AuthoritativeLedgerAppend,
  ): Promise<FirebaseAuthorizedLedgerAppendOutcome>;
}

const exactOptions = (
  value: unknown,
): PostgresFirebaseAuthorizedLedgerRuntimeOptions => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) {
    throw new TypeError("invalid PostgreSQL Firebase ledger runtime options");
  }
  const expected = [
    "pool", "project_id", "runtime_mode", "id_token_adapter", "application_id",
    "context_ttl_seconds",
  ].sort();
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key !== "string")) {
    throw new TypeError("invalid PostgreSQL Firebase ledger runtime options");
  }
  const actual = (keys as string[]).sort();
  if (actual.length !== expected.length
    || actual.some((key, index) => key !== expected[index])) {
    throw new TypeError("invalid PostgreSQL Firebase ledger runtime options");
  }
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) {
      throw new TypeError("invalid PostgreSQL Firebase ledger runtime options");
    }
  }
  return value as PostgresFirebaseAuthorizedLedgerRuntimeOptions;
};

/**
 * Route-free request authorization to PostgreSQL ledger append.
 *
 * Authorization reads use separate read-only transactions. The append then
 * opens its own serializable transaction and re-locks every exact authority
 * coordinate, so a revocation or control change between the checks denies the
 * effect. Construction adds no route, token source, credential, or default.
 */
export const createPostgresFirebaseAuthorizedLedgerRuntime = (
  optionsValue: PostgresFirebaseAuthorizedLedgerRuntimeOptions,
): PostgresFirebaseAuthorizedLedgerRuntime => {
  const options = exactOptions(optionsValue);
  const pool = options.pool;
  const withTransaction = pool.withTransaction;
  if (typeof withTransaction !== "function" || isProxy(withTransaction)) {
    throw new TypeError("invalid PostgreSQL Firebase ledger runtime pool");
  }
  const stablePool: PostgresTransactionPool = Object.freeze({
    withTransaction: (transactionOptions, callback) => withTransaction.call(
      pool,
      transactionOptions,
      callback,
    ),
  });
  // Keep the raw SQL capability inside this composition. Both sources receive
  // only a fixed-statement query function and cannot construct a transaction.
  const fixedQuery = Object.freeze({
    query: (statement: SqlStatement) => stablePool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      (connection) => connection.query(statement),
    ),
  });
  const authorizer = composeFirebaseMemoryAuthorization({
    project_id: options.project_id,
    runtime_mode: options.runtime_mode,
    id_token_adapter: options.id_token_adapter,
    authorization_source: createPostgresFirebaseApplicationAuthorizationSource(fixedQuery),
    control_source: createPostgresApplicationAccountControlSource(fixedQuery),
    application_id: options.application_id,
    capability: "memories.write",
    context_ttl_seconds: options.context_ttl_seconds,
  });
  const ledger = createPostgresAuthoritativeLedgerRepository({ pool: stablePool });
  return Object.freeze({
    [RUNTIME_PORT]: true as const,
    async append(idToken, nowEpochSeconds, request) {
      const authorization = await authorizer.authorize(idToken, nowEpochSeconds);
      if (!authorization.authorized) {
        return Object.freeze({ kind: "denied" as const, outcome: authorization.outcome });
      }
      try {
        const outcome = await ledger.append(authorization.context, request);
        return Object.freeze({ kind: "completed" as const, outcome });
      } catch {
        return Object.freeze({ kind: "unavailable" as const });
      }
    },
  });
};
