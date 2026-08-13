import { isProxy } from "node:util/types";

import {
  composeFirebaseMemoryAuthorization,
} from "../../apps/service/composition/firebase-memory-authorization";
import type { FirebaseApplicationAuthorizer } from
  "../../apps/service/auth/firebase-application-authorization";
import type { FirebaseIdentityRuntimeMode, FirebaseIdTokenVerificationAdapter } from
  "../../apps/service/auth/firebase-identity";
import { createPostgresApplicationAccountControlSource } from
  "./application-account-control-source";
import type { PostgresTransactionPool, SqlStatement } from "./connection";
import { createPostgresFirebaseApplicationAuthorizationSource } from
  "./firebase-application-authorization-source";

export interface PostgresFirebaseAuthorizationRuntimeOptions {
  readonly pool: PostgresTransactionPool;
  readonly project_id: string;
  readonly runtime_mode: FirebaseIdentityRuntimeMode;
  readonly id_token_adapter: FirebaseIdTokenVerificationAdapter;
  readonly application_id: string;
  readonly context_ttl_seconds: number;
}

interface PostgresFirebaseAuthorizationRuntimeBinding {
  readonly pool: PostgresTransactionPool;
  readonly authorizer: FirebaseApplicationAuthorizer;
}

const exactOptions = (
  value: unknown,
): PostgresFirebaseAuthorizationRuntimeOptions => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) {
    throw new TypeError("invalid PostgreSQL Firebase runtime options");
  }
  const expected = [
    "pool", "project_id", "runtime_mode", "id_token_adapter", "application_id",
    "context_ttl_seconds",
  ].sort();
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key !== "string")) {
    throw new TypeError("invalid PostgreSQL Firebase runtime options");
  }
  const actual = (keys as string[]).sort();
  if (actual.length !== expected.length
    || actual.some((key, index) => key !== expected[index])) {
    throw new TypeError("invalid PostgreSQL Firebase runtime options");
  }
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) {
      throw new TypeError("invalid PostgreSQL Firebase runtime options");
    }
  }
  return value as PostgresFirebaseAuthorizationRuntimeOptions;
};

/** @internal Shared fixed-query authorization construction for PG read/write runtimes. */
export const createPostgresFirebaseAuthorizationRuntime = (
  optionsValue: PostgresFirebaseAuthorizationRuntimeOptions,
  capability: "memories.read" | "memories.write" | "memories.export",
): PostgresFirebaseAuthorizationRuntimeBinding => {
  if (capability !== "memories.read" && capability !== "memories.write"
    && capability !== "memories.export") {
    throw new TypeError("invalid PostgreSQL Firebase runtime capability");
  }
  const options = exactOptions(optionsValue);
  const pool = options.pool;
  const withTransaction = pool?.withTransaction;
  if (typeof withTransaction !== "function" || isProxy(withTransaction)) {
    throw new TypeError("invalid PostgreSQL Firebase runtime pool");
  }
  const stablePool: PostgresTransactionPool = Object.freeze({
    withTransaction: (transactionOptions, callback) => withTransaction.call(
      pool,
      transactionOptions,
      callback,
    ),
  });
  const fixedQuery = Object.freeze({
    query: (statement: SqlStatement) => stablePool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      (connection) => connection.query(statement),
    ),
  });
  return Object.freeze({
    pool: stablePool,
    authorizer: composeFirebaseMemoryAuthorization({
      project_id: options.project_id,
      runtime_mode: options.runtime_mode,
      id_token_adapter: options.id_token_adapter,
      authorization_source: createPostgresFirebaseApplicationAuthorizationSource(fixedQuery),
      control_source: createPostgresApplicationAccountControlSource(fixedQuery),
      application_id: options.application_id,
      capability,
      context_ttl_seconds: options.context_ttl_seconds,
    }),
  });
};
