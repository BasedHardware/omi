/**
 * Chat codec invariants: payload-hash determinism (ADR-005 / INV-CHAT-006),
 * keyed patch (hard rule 7), and 409 identity-conflict folding onto
 * WriteFailure (hard rule 6). Hermetic — ManualEnv only; no network, no wall clock.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import type { ChatMessage, ChatMessageOp } from "@omi-core/contracts";
import {
  buildCreateChatMessage,
  buildPatchChatMessage,
  chatMessagePayloadHash,
  chatMessagesCodec,
  foldChatIdentityConflict,
  isChatIdentityConflictFailure,
} from "@omi-core/domain";
import { createHash } from "node:crypto";
import { ManualEnv } from "../fakes.js";

const BASE_HASH_PAYLOAD = {
  text: "hi",
  sender: "human",
  appId: null as string | null,
  sessionId: null as string | null,
  metadata: null as string | null,
  messageSource: "desktop_chat",
};

test("payload-hash is deterministic and matches the desktop write-path digest", () => {
  // red-proof: change chatMessagePayloadHash to append String(Math.random())
  // to the canonical string before hashing — the two calls diverge
  // (`identical payloads must hash identically`).
  const a = chatMessagePayloadHash(BASE_HASH_PAYLOAD);
  const b = chatMessagePayloadHash({ ...BASE_HASH_PAYLOAD });
  assert.equal(a, b, "identical payloads must hash identically");
  assert.equal(
    a,
    "sha256:1ebd1f3fef3a402694dfcee66f345768a37a15f0c22c9470f07ab57b2761d18b",
    "digest must match backend _message_idempotency_payload_hash for this fixture",
  );
  const altered = chatMessagePayloadHash({ ...BASE_HASH_PAYLOAD, text: "hi!" });
  assert.notEqual(altered, a, "text is part of the identity payload");
});

/**
 * The digest test above pins a value the implementation itself produced, which
 * on its own proves only that the code is deterministic — a WRONG hash would
 * pass it just as happily and then silently disagree with the server, breaking
 * idempotency exactly when a retry matters. `chatMessagePayloadHash` cannot use
 * `node:crypto` (it runs in the browser bundle too) so it carries a hand-rolled
 * SHA-256, and a hand-rolled SHA-256 is precisely the thing you do not accept on
 * inspection.
 *
 * So: cross-check the pure implementation against `node:crypto` over the cases
 * that break a wrong one — the 55/56/64-byte message-padding block boundaries,
 * multi-byte UTF-8, astral-plane surrogate pairs, and JSON escape sequences.
 *
 * // red-proof: in chat-codec.ts `sha256Hex`, change the padding line
 * // `buf[data.length] = 0x80` to `0x00`.
 * // APPLIED 2026-08-08: observed BOTH this test and the fixture-digest test go
 * // red. Recorded honestly rather than as predicted: the prediction was that
 * // only this one would fail, and that was wrong because the fixture payload
 * // happens to be 118 bytes and so also crosses a padding block. The fixture
 * // test is still not a substitute — it pins ONE input, so any wrong hash that
 * // happens to agree on that single 118-byte string passes it, and only the
 * // cross-check below covers the 55/56/64-byte boundaries and the astral-plane
 * // and escape cases at all.
 */
test("the hand-rolled SHA-256 agrees with node:crypto, including at block boundaries", () => {
  const cases: readonly { text: string; sender: "human" | "ai"; appId: string | null; sessionId: string | null; metadata: string | null; messageSource: string }[] = [
    { text: "hi", sender: "human", appId: null, sessionId: null, metadata: null, messageSource: "desktop_chat" },
    { text: "", sender: "ai", appId: "app-1", sessionId: "s-1", metadata: "{}", messageSource: "desktop_chat" },
    // Multi-byte and astral-plane: UTF-8 length differs from UTF-16 length.
    { text: "é中文 emoji 🚀", sender: "human", appId: null, sessionId: null, metadata: null, messageSource: "x" },
    // The message-padding block boundaries, where a wrong implementation breaks.
    { text: "a".repeat(55), sender: "human", appId: null, sessionId: null, metadata: null, messageSource: "d" },
    { text: "a".repeat(56), sender: "human", appId: null, sessionId: null, metadata: null, messageSource: "d" },
    { text: "a".repeat(64), sender: "human", appId: null, sessionId: null, metadata: null, messageSource: "d" },
    { text: "a".repeat(5000), sender: "human", appId: null, sessionId: null, metadata: null, messageSource: "d" },
    { text: 'quote " back\\slash \n newline \t tab', sender: "human", appId: null, sessionId: null, metadata: null, messageSource: "d" },
  ];

  const mismatches: string[] = [];
  for (const c of cases) {
    // The exact canonical encoding the backend uses:
    // json.dumps(..., ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    const wire = {
      app_id: c.appId,
      message_source: c.messageSource,
      metadata: c.metadata,
      sender: c.sender,
      session_id: c.sessionId,
      text: c.text,
    };
    const canonical = JSON.stringify(wire, Object.keys(wire).sort());
    const expected = `sha256:${createHash("sha256").update(canonical, "utf8").digest("hex")}`;
    const actual = chatMessagePayloadHash(c);
    if (actual !== expected) mismatches.push(`${JSON.stringify(c.text).slice(0, 24)}: ${actual} != ${expected}`);
  }
  assert.deepEqual(mismatches, []);
});

/**
 * VERIFIED AGAINST THE REAL BACKEND, not against our own reimplementation.
 * `backend/database/chat.py::_message_idempotency_payload_hash` at baseline
 * was executed directly with this fixture payload:
 *
 *   canonical: {"app_id":null,"message_source":"desktop_chat","metadata":null,
 *               "sender":"human","session_id":null,"text":"hi"}
 *   sha256:1ebd1f3fef3a402694dfcee66f345768a37a15f0c22c9470f07ab57b2761d18b
 *
 * which is byte-identical to the digest asserted above. The field set, the key
 * sort, `ensure_ascii=False` and the `(',', ':')` separators all agree.
 */

test("a client can never author an unknown sender", () => {
  // red-proof: widen `ChatMessageOp`'s create arm back to `ChatMessageSender`.
  // The @ts-expect-error below becomes an unused-directive ERROR and the build
  // fails, which is the point: the narrowing is enforced by the compiler, not
  // by a comment. `"unknown"` is read tolerance for a sender we do not
  // recognize; authoring it would either be rejected by the server or, worse,
  // coerced to "human" and attribute the model's words to the user.
  // APPLIED 2026-08-08: observed
  //   error TS2578: Unused '@ts-expect-error' directive.
  const env = new ManualEnv();
  // @ts-expect-error "unknown" is a read-only tolerance, never authorable
  const bad = () => buildCreateChatMessage(env, "x", { sender: "unknown" });
  assert.equal(typeof bad, "function");

  const good = buildCreateChatMessage(env, "x", { sender: "ai" });
  assert.equal(good.op === "create" && good.sender, "ai");
});

test("keyed patch: absent keys leave the projected row untouched", () => {
  // red-proof: in chatMessagesCodec.applyOp patch branch, replace the keyed
  // `if (p.rating !== undefined)` update with setdefaults
  // `rating: op.patch.rating ?? null`, `text: ""`, `reported: false` —
  // fails with `absent rating must not clear a set thumb` (`null !== 1`).
  const env = new ManualEnv();
  const create = buildCreateChatMessage(env, "keep this text", { sender: "ai" });
  const created = chatMessagesCodec.applyOp(JSON.stringify(create), null);
  assert.ok(created);
  const seeded: ChatMessage = { ...created, rating: 1, reported: true };

  const patchOp: ChatMessageOp = {
    op: "patch",
    opId: "o-patch",
    id: seeded.id,
    at: env.now() + 1,
    patch: {}, // every field absent
  };
  const afterEmpty = chatMessagesCodec.applyOp(JSON.stringify(patchOp), seeded);
  assert.ok(afterEmpty);
  assert.equal(afterEmpty.rating, 1, "absent rating must not clear a set thumb");
  assert.equal(afterEmpty.text, "keep this text", "absent text must not reset content");
  assert.equal(afterEmpty.reported, true, "absent reported must not reset server flag");
  assert.equal(afterEmpty.sender, "ai");

  const rateOnly = buildPatchChatMessage(env, seeded.id, { rating: -1 });
  const afterRate = chatMessagesCodec.applyOp(JSON.stringify(rateOnly), seeded);
  assert.ok(afterRate);
  assert.equal(afterRate.rating, -1, "present rating key applies");
  assert.equal(afterRate.text, "keep this text", "text stays when only rating is patched");
  assert.equal(afterRate.reported, true, "reported stays when only rating is patched");
});

test("409 identity conflict folds to permanent/conflict (never retryable)", () => {
  // red-proof: change foldChatIdentityConflict to return
  // `{ kind: "retryable", detail } as any` — fails with
  // `Expected values to be strictly equal: + 'retryable' - 'permanent'`.
  const failure = foldChatIdentityConflict(
    "client_message_id already exists with a different payload",
  );
  assert.equal(failure.kind, "permanent");
  assert.equal(failure.reason, "conflict");
  assert.match(failure.detail, /different payload/);
  assert.equal(isChatIdentityConflictFailure(failure), true);
  assert.equal(
    isChatIdentityConflictFailure({ kind: "retryable", detail: "409 lookalike" }),
    false,
    "retryable must not be accepted as an identity conflict",
  );
  // Content only a working fold produces: adapters hand this to the outbox,
  // which dead-letters permanent failures (never retries them).
  assert.deepEqual(failure, {
    kind: "permanent",
    reason: "conflict",
    detail: "client_message_id already exists with a different payload",
  });
});

test("create overlay stamps journalRevision + payloadHash from the op payload", () => {
  const env = new ManualEnv();
  const op = buildCreateChatMessage(env, "ship the chat contract", {
    journalRevision: 3,
    appId: "persona-1",
    chatSessionId: "sess-9",
  });
  assert.equal(op.op, "create");
  const row = chatMessagesCodec.applyOp(JSON.stringify(op), null);
  assert.ok(row);
  assert.equal(row.journalRevision, 3);
  assert.equal(row.appId, "persona-1");
  assert.equal(row.chatSessionId, "sess-9");
  assert.equal(
    row.payloadHash,
    chatMessagePayloadHash({
      text: "ship the chat contract",
      sender: "human",
      appId: "persona-1",
      sessionId: "sess-9",
      metadata: null,
      messageSource: "desktop_chat",
    }),
  );
});
