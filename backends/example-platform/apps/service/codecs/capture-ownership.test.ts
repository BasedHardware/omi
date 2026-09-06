import { expect, test } from "bun:test";
import { createCaptureOwnershipCodec, CaptureOwnershipChanged } from "./capture-ownership";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";

const authority = (account = "account:alice", epoch = 12) => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1", principal_id: "principal:alice", account_id: account,
  application_id: "app:desktop", credential_id: "credential:one", credential_generation: 4,
  capability: "listen.capture.write", grant_id: "grant:one", grant_version: 9, account_epoch: epoch,
  destination_activation_revision: 17, lifecycle_state: "active", deletion_epoch: null,
  authentication_strength: "firebase-id-token", issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 200,
  authorization_state_digest: "a".repeat(64),
}, 150);

test("capture receipts constrain actual authority without replacing it, survive key rotation, and reject ownership drift", () => {
  const codec = createCaptureOwnershipCodec(new Uint8Array(32).fill(1));
  const context = authority();
  const ownership = codec.issue(context);
  expect(() => codec.verify(context, ownership.receipt)).not.toThrow();
  expect(JSON.stringify(ownership)).not.toContain("account:alice");
  expect(() => codec.issue({ ...context })).toThrow("not issued by auth composition");
  expect(() => codec.verify(authority("account:bob"), ownership.receipt)).toThrow(CaptureOwnershipChanged);
  expect(() => codec.verify(authority("account:alice", 13), ownership.receipt)).toThrow(CaptureOwnershipChanged);
  expect(() => codec.verify(context, ownership.receipt.slice(0,-1)+(ownership.receipt.endsWith("0") ? "1" : "0"))).toThrow("invalid_capture_ownership_receipt");
  expect(() => codec.verify(context, null)).toThrow("invalid_capture_ownership_receipt");
  const rotated = createCaptureOwnershipCodec(new Uint8Array(32).fill(2));
  expect(rotated.issue(context).ownerKey).toBe(ownership.ownerKey);
  expect(rotated.issue(context).receipt).not.toBe(ownership.receipt);
  expect(() => rotated.verify(context, ownership.receipt)).toThrow("invalid_capture_ownership_receipt");
  expect(() => rotated.verify(context, rotated.issue(context).receipt)).not.toThrow();
});
