import type {
  AuthoritativeLedgerAppend,
  AuthoritativeLedgerAppendOutcome,
} from "../../apps/service/stores/authoritative-ledger-repository";
import { createPostgresAuthoritativeLedgerRepository } from
  "./authoritative-ledger-repository";
import {
  createPostgresFirebaseAuthorizationRuntime,
  type PostgresFirebaseAuthorizationRuntimeOptions,
} from "./firebase-authorized-runtime-support";

const RUNTIME_PORT: unique symbol = Symbol("postgres-firebase-authorized-ledger-runtime");

export type PostgresFirebaseAuthorizedLedgerRuntimeOptions =
  PostgresFirebaseAuthorizationRuntimeOptions;

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
  const { authorizer, pool } = createPostgresFirebaseAuthorizationRuntime(
    optionsValue,
    "memories.write",
  );
  const ledger = createPostgresAuthoritativeLedgerRepository({ pool });
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
