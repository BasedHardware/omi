import { createHash } from "node:crypto";

import { createAuthorizedLedgerWriteContextIssuer } from "./authorized-context-internal";
import type { AuthorizedLedgerWriteContext } from "./authorized-context";

const CONTEXT_TTL_SECONDS = 300;
const APPLICATION_ID = "omi-local-dev-app";

export type LocalLedgerWriteCapability = "memories.work.accept" | "memories.work.execute";

export interface LocalApplicationAuthorizationInput {
  readonly account_id: string;
  readonly account_epoch: number;
  readonly capability: LocalLedgerWriteCapability;
  readonly now_epoch_seconds: number;
}

export interface LocalApplicationAuthorizer {
  issue(input: LocalApplicationAuthorizationInput): AuthorizedLedgerWriteContext;
}

const digestFor = (input: LocalApplicationAuthorizationInput): string =>
  createHash("sha256")
    .update(`local-ledger-auth-v1:${input.account_id}:${input.account_epoch}:${input.capability}`)
    .digest("hex");

/**
 * Reviewed local auth-composition seam. The issuer is constructed here and
 * nowhere else in the local service; routes receive already-issued contexts.
 */
export const createLocalApplicationAuthorizer = (): LocalApplicationAuthorizer => {
  const issuer = createAuthorizedLedgerWriteContextIssuer();
  return Object.freeze({
    issue(input: LocalApplicationAuthorizationInput): AuthorizedLedgerWriteContext {
      const now = input.now_epoch_seconds;
      const principal = input.capability === "memories.work.execute"
        ? "worker:local-memory-execute"
        : "worker:local-memory-accept";
      return issuer.issue({
        context_version: "authorized-ledger-write-context-v1",
        principal_id: principal,
        account_id: input.account_id,
        application_id: APPLICATION_ID,
        credential_id: "credential:local-memory-formation",
        credential_generation: 1,
        capability: input.capability,
        grant_id: "grant:local-memory-formation",
        grant_version: 1,
        account_epoch: input.account_epoch,
        destination_activation_revision: 1,
        lifecycle_state: "active",
        deletion_epoch: null,
        authentication_strength: "local-dev-token",
        issued_at_epoch_seconds: now,
        expires_at_epoch_seconds: now + CONTEXT_TTL_SECONDS,
        authorization_state_digest: digestFor(input),
      }, now);
    },
  });
};
