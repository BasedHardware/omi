import { expect, test } from "bun:test";

import {
  assertAuthorizedLedgerWriteContext,
  assertAuthorizedLedgerWriteContextCurrentAt,
  authorizedRestoreReleaseBinding,
} from "./authorized-context";
import { createAuthorizedLedgerWriteContextIssuer } from "./authorized-context-internal";

const input = () => ({
  context_version: "authorized-ledger-write-context-v1" as const,
  principal_id: "principal:alice",
  account_id: "account:alice",
  application_id: "app:desktop",
  credential_id: "credential:one",
  credential_generation: 4,
  capability: "memories.write",
  grant_id: "grant:one",
  grant_version: 9,
  account_epoch: 12,
  destination_activation_revision: 17,
  lifecycle_state: "active" as const,
  deletion_epoch: null,
  authentication_strength: "firebase-id-token",
  issued_at_epoch_seconds: 100,
  expires_at_epoch_seconds: 200,
  authorization_state_digest: "a".repeat(64),
});

test("authorized ledger context is exact, frozen, and runtime-minted only by auth composition", () => {
  const issuer = createAuthorizedLedgerWriteContextIssuer();
  const context = issuer.issue(input(), 150);
  expect(Object.isFrozen(context)).toBe(true);
  expect(assertAuthorizedLedgerWriteContext(context)).toBe(context);
  expect(() => assertAuthorizedLedgerWriteContext({ ...context })).toThrow("not issued by auth composition");
});

test("authorized ledger context rejects accessors, stale expiry, and account/lifecycle ambiguity", () => {
  const issuer = createAuthorizedLedgerWriteContextIssuer();
  const accessor = input();
  Object.defineProperty(accessor, "account_id", { enumerable: true, get: () => "account:alice" });
  expect(() => issuer.issue(accessor, 150)).toThrow("data properties");
  expect(() => issuer.issue({ ...input(), expires_at_epoch_seconds: 150 }, 150)).toThrow("expired");
  expect(() => issuer.issue({ ...input(), lifecycle_state: "deleted" } as never, 150)).toThrow("active");
  expect(() => issuer.issue({ ...input(), account_id: `account:${"x".repeat(128)}` }, 150)).toThrow("account_id");
  expect(() => assertAuthorizedLedgerWriteContextCurrentAt(issuer.issue(input(), 150), 200)).toThrow("expired at the authoritative");
});

test("restored release authority is hidden, exact, and cannot be copied with visible context fields", () => {
  const issuer = createAuthorizedLedgerWriteContextIssuer();
  const context = issuer.issueRestored(input(), {
    database_generation_digest: "b".repeat(64),
    restore_release_revision: 3,
    restore_release_content_hash: "c".repeat(64),
  }, 150);
  expect(authorizedRestoreReleaseBinding(context)).toEqual({
    database_generation_digest: "b".repeat(64),
    restore_release_revision: 3,
    restore_release_content_hash: "c".repeat(64),
  });
  expect(Object.keys(context)).not.toContain("database_generation_digest");
  expect(() => authorizedRestoreReleaseBinding({ ...context })).toThrow("not issued");
  expect(authorizedRestoreReleaseBinding(issuer.issue(input(), 150))).toBeNull();
  expect(() => issuer.issueRestored(input(), {
    database_generation_digest: "bad",
    restore_release_revision: 3,
    restore_release_content_hash: "c".repeat(64),
  }, 150)).toThrow("SHA-256");
});
