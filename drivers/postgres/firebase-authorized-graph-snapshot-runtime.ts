import type { GraphSnapshot } from "../../core/retrieve";
import { createPostgresAuthoritativeGraphSnapshotRepository } from
  "./authoritative-graph-snapshot";
import {
  createPostgresFirebaseAuthorizationRuntime,
  type PostgresFirebaseAuthorizationRuntimeOptions,
} from "./firebase-authorized-runtime-support";
import { PostgresRepositoryError } from "./transaction";

const RUNTIME_PORT: unique symbol = Symbol("postgres-firebase-authorized-graph-snapshot-runtime");

export type PostgresFirebaseAuthorizedGraphSnapshotRuntimeOptions =
  PostgresFirebaseAuthorizationRuntimeOptions;

export type FirebaseAuthorizedGraphSnapshotOutcome =
  | Readonly<{
      kind: "denied";
      outcome: "authentication" | "authorization" | "stale_epoch" | "unavailable";
    }>
  | Readonly<{
      kind: "loaded";
      authorization_generation_digest: string;
      snapshot: GraphSnapshot;
    }>
  | Readonly<{ kind: "unavailable" }>;

export interface PostgresFirebaseAuthorizedGraphSnapshotRuntime {
  readonly [RUNTIME_PORT]: true;
  load(
    idToken: string,
    nowEpochSeconds: number,
  ): Promise<FirebaseAuthorizedGraphSnapshotOutcome>;
}

const AUTHORITY_FAILURES = new Set([
  "authorization_state_denied", "expired_context", "stale_epoch",
  "destination_inactive", "lifecycle_inactive", "credential_inactive",
  "grant_inactive", "capability_denied",
]);

/**
 * Route-free Firebase-authorized PostgreSQL graph snapshot load.
 *
 * The graph repository re-locks the exact authority context and holds those
 * locks through every awaited snapshot query, so no graph bytes can be loaded
 * under a preliminary-only authorization decision.
 */
export const createPostgresFirebaseAuthorizedGraphSnapshotRuntime = (
  optionsValue: PostgresFirebaseAuthorizedGraphSnapshotRuntimeOptions,
): PostgresFirebaseAuthorizedGraphSnapshotRuntime => {
  const { authorizer, pool } = createPostgresFirebaseAuthorizationRuntime(
    optionsValue,
    "memories.read",
  );
  const graphs = createPostgresAuthoritativeGraphSnapshotRepository({ pool });
  return Object.freeze({
    [RUNTIME_PORT]: true as const,
    async load(idToken, nowEpochSeconds) {
      const authorization = await authorizer.authorize(idToken, nowEpochSeconds);
      if (!authorization.authorized) {
        return Object.freeze({ kind: "denied" as const, outcome: authorization.outcome });
      }
      try {
        const snapshot = await graphs.load(authorization.context);
        return Object.freeze({
          kind: "loaded" as const,
          authorization_generation_digest: authorization.context.authorization_state_digest,
          snapshot,
        });
      } catch (error) {
        if (error instanceof PostgresRepositoryError && AUTHORITY_FAILURES.has(error.code)) {
          return Object.freeze({ kind: "denied" as const, outcome: "authorization" as const });
        }
        return Object.freeze({ kind: "unavailable" as const });
      }
    },
  });
};
