import { expect, test } from "bun:test";
import { canonicalizeRedacted, prepareDerivation, sha256CanonicalRedacted } from "./index";

const versions = { strategy_version: "placement-v1", model_version: "none", prompt_version: "none", policy_version: "p1", code_version: "c1", schema_version: "s1", tokenizer_version: "none", tool_version: "none" };

test("T9 canonical hashing sorts keys, preserves array order, and redacts fixed raw fields", () => {
  expect(canonicalizeRedacted({ z: 1, a: ["first", "second"], token: "not-hashed" })).toBe('{"a":["first","second"],"token":"[REDACTED]","z":1}');
  expect(sha256CanonicalRedacted({ b: 2, a: 1 })).toBe(sha256CanonicalRedacted({ a: 1, b: 2 }));
  expect(sha256CanonicalRedacted(["first", "second"])).not.toBe(sha256CanonicalRedacted(["second", "first"]));
});

test("T9 ledger records ordered digests and a successful-empty outcome", () => {
  const prepared = prepareDerivation({ attempt_id: "attempt-empty", commit_id: "commit-empty", owner_account_id: "owner-1", parent_commit: null, idempotency_key: "empty-key", input_revisions: [{ revision_id: "p-1", content: { value: 1 } }], output_revisions: [], versions, success_kind: "successful_empty" });
  expect(prepared.commit).toMatchObject({ success_kind: "successful_empty", input_revision_ids: ["p-1"], output_revision_ids: [], sequence: null });
  expect(prepared.commit.input_version_digest).not.toBe(prepared.commit.input_digest);
});
