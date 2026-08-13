import type { GraphSnapshot } from "../../core/retrieve";
import {
  projectApplicationDefaultReadTreeInputFromAuthorizationEvidence,
  type ApplicationGrantProjectedTreeInputSnapshot,
} from "../../core/retrieve/authorization-boundary";
import { sha256CanonicalRedacted } from "../../core/ledger";
import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
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
      db_now_epoch_seconds: number;
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

const loadedAuthorities = new WeakMap<object, AuthorizedLedgerWriteContext>();

export interface FirebaseAuthorizedApplicationProjection {
  readonly projected: ApplicationGrantProjectedTreeInputSnapshot;
  readonly owner_identity_digest: string;
  readonly application_identity_digest: string;
  readonly credential_identity_digest: string;
  readonly authorization_generation_digest: string;
  readonly grant_state_digest: string;
  readonly account_generation_digest: string;
  readonly db_now_epoch_seconds: number;
}

/**
 * Turns one successfully locked graph load into the application-default policy
 * projection.  The load's sealed context is retained in a private WeakMap, so
 * a structural lookalike cannot use this seam and no legacy MCP grant is
 * fabricated.
 */
export const projectFirebaseAuthorizedGraphSnapshotLoad = (
  loaded: Extract<FirebaseAuthorizedGraphSnapshotOutcome, { readonly kind: "loaded" }>,
  accountTimezone: string,
): FirebaseAuthorizedApplicationProjection => {
  const authority = loadedAuthorities.get(loaded);
  if (!authority || typeof accountTimezone !== "string" || accountTimezone.length < 1
    || accountTimezone.length > 256 || accountTimezone.includes("\0")) {
    throw new TypeError("invalid Firebase-authorized graph projection input");
  }
  const principalDigest = sha256CanonicalRedacted({
    version: "firebase-application-reader-v1",
    owner_account_id: authority.account_id,
    principal_id: authority.principal_id,
    application_id: authority.application_id,
  });
  const authorizationGenerationDigest = sha256CanonicalRedacted({
    version: "firebase-application-read-authorization-v1",
    authorization_state_digest: authority.authorization_state_digest,
    capability: authority.capability,
    account_epoch: authority.account_epoch,
    destination_activation_revision: authority.destination_activation_revision,
    credential_generation: authority.credential_generation,
    grant_version: authority.grant_version,
    lifecycle_state: authority.lifecycle_state,
    deletion_epoch: authority.deletion_epoch,
  });
  const grantStateDigest = sha256CanonicalRedacted({
    version: "firebase-application-read-grant-v1",
    owner_account_id: authority.account_id,
    application_id: authority.application_id,
    credential_id: authority.credential_id,
    credential_generation: authority.credential_generation,
    grant_id: authority.grant_id,
    grant_version: authority.grant_version,
    capability: authority.capability,
  });
  const projected = projectApplicationDefaultReadTreeInputFromAuthorizationEvidence(
    loaded.snapshot,
    { account_timezone: accountTimezone },
    {
      owner_account_id: authority.account_id,
      app_id: authority.application_id,
      key_id: authority.credential_id,
      principal_digest: principalDigest,
      authorization_digest: authorizationGenerationDigest,
      persisted_grant_state_digest: grantStateDigest,
    },
  );
  return Object.freeze({
    projected,
    owner_identity_digest: sha256CanonicalRedacted({
      version: "firebase-application-owner-identity-v1",
      owner_account_id: authority.account_id,
      account_epoch: authority.account_epoch,
    }),
    application_identity_digest: sha256CanonicalRedacted({
      version: "firebase-application-identity-v1",
      application_id: authority.application_id,
    }),
    credential_identity_digest: sha256CanonicalRedacted({
      version: "firebase-application-credential-identity-v1",
      credential_id: authority.credential_id,
      credential_generation: authority.credential_generation,
    }),
    authorization_generation_digest: authorizationGenerationDigest,
    grant_state_digest: grantStateDigest,
    account_generation_digest: sha256CanonicalRedacted({
      version: "firebase-application-account-generation-v1",
      account_epoch: authority.account_epoch,
      destination_activation_revision: authority.destination_activation_revision,
    }),
    db_now_epoch_seconds: loaded.db_now_epoch_seconds,
  });
};

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
    async load(idToken: string, nowEpochSeconds: number) {
      const authorization = await authorizer.authorize(idToken, nowEpochSeconds);
      if (!authorization.authorized) {
        return Object.freeze({ kind: "denied" as const, outcome: authorization.outcome });
      }
      try {
        const loaded = await graphs.loadWithAttestation(authorization.context);
        const outcome = Object.freeze({
          kind: "loaded" as const,
          authorization_generation_digest: authorization.context.authorization_state_digest,
          db_now_epoch_seconds: loaded.db_now_epoch_seconds,
          snapshot: loaded.snapshot,
        });
        loadedAuthorities.set(outcome, authorization.context);
        return outcome;
      } catch (error) {
        if (error instanceof PostgresRepositoryError && AUTHORITY_FAILURES.has(error.code)) {
          return Object.freeze({ kind: "denied" as const, outcome: "authorization" as const });
        }
        return Object.freeze({ kind: "unavailable" as const });
      }
    },
  });
};
