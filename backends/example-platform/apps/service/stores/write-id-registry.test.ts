/**
 * Ruling B1's idempotency registry.
 *
 * The properties here are the ones that decide whether a user's saved edit is
 * reported as saved, so each carries a red-proof applied to the real source.
 */

import { describe, expect, test } from "bun:test";

import { createInMemoryWriteIdRegistry, stableSerialize } from "./write-id-registry";

const ACCOUNT = "acct-registry-fixture";
const OTHER_ACCOUNT = "acct-registry-other";
const WRITE_ID = "f".repeat(64);
const OUTCOME = { record_id: "task-1", revision: "a".repeat(64) };

const envelopeContent = (epoch: number, title: string): unknown => ({
  account_epoch: epoch,
  domain: "tasks",
  op: { op: "create", record_id: "task-1", content: { title, done: false } },
});

describe("replay, reuse, and the difference between them", () => {
  test("an unseen write_id is fresh", () => {
    const registry = createInMemoryWriteIdRegistry();
    expect(registry.lookup(ACCOUNT, WRITE_ID, envelopeContent(7, "a"))).toEqual({ kind: "fresh" });
  });

  /**
   * The crash-replay case the ratified contract names: applied, crashed before
   * the tombstone, interleaved write, replay. Answering `conflict` would tell
   * the user a saved edit failed.
   *
   * red-proof: make `lookup` answer `reuse` whenever a row exists, without
   * comparing fingerprints. APPLIED AND OBSERVED RED.
   */
  test("the same write_id with the same content replays the recorded outcome", () => {
    const registry = createInMemoryWriteIdRegistry();
    const content = envelopeContent(7, "a");
    registry.record({ accountId: ACCOUNT, writeId: WRITE_ID, fingerprintOf: content, accountEpoch: 7, outcome: OUTCOME });
    expect(registry.lookup(ACCOUNT, WRITE_ID, content)).toEqual({ kind: "replay", outcome: OUTCOME });
  });

  /**
   * red-proof: make `lookup` answer `replay` without comparing fingerprints —
   * two different ops then launder through one key and the second is answered
   * with the first one's outcome. APPLIED AND OBSERVED RED.
   */
  test("the same write_id with different content is reuse", () => {
    const registry = createInMemoryWriteIdRegistry();
    registry.record({
      accountId: ACCOUNT, writeId: WRITE_ID, fingerprintOf: envelopeContent(7, "a"),
      accountEpoch: 7, outcome: OUTCOME,
    });
    expect(registry.lookup(ACCOUNT, WRITE_ID, envelopeContent(7, "DIFFERENT"))).toEqual({ kind: "reuse" });
  });

  /**
   * THE ONE THAT COSTS A USER THEIR EDIT IF IT IS WRONG.
   *
   * The ratified canonical-JSON definition preserves key order rather than
   * fixing it, so two serializations of the same op with different key order
   * are both canonical and both legitimate. A byte-comparing registry would
   * call the second one reuse, answer 409, and the client would dead-letter an
   * op identical to one that already succeeded.
   *
   * red-proof: replace `stableSerialize` with `JSON.stringify` inside
   * `fingerprint`. APPLIED AND OBSERVED RED.
   */
  test("the same op re-serialized with a different key order is a REPLAY, not reuse", () => {
    const registry = createInMemoryWriteIdRegistry();
    const first = { account_epoch: 7, domain: "tasks", op: { op: "create", record_id: "t", content: { a: 1, b: 2 } } };
    const reordered = { op: { content: { b: 2, a: 1 }, record_id: "t", op: "create" }, domain: "tasks", account_epoch: 7 };
    expect(JSON.stringify(first)).not.toBe(JSON.stringify(reordered));

    registry.record({ accountId: ACCOUNT, writeId: WRITE_ID, fingerprintOf: first, accountEpoch: 7, outcome: OUTCOME });
    expect(registry.lookup(ACCOUNT, WRITE_ID, reordered)).toEqual({ kind: "replay", outcome: OUTCOME });
  });

  /**
   * Array order IS meaning, unlike object key order. A serializer that sorted
   * both would call two genuinely different ops the same op.
   */
  test("array order still distinguishes two ops", () => {
    expect(stableSerialize({ v: [1, 2] })).not.toBe(stableSerialize({ v: [2, 1] }));
  });

  /**
   * A global key would let one caller learn whether ANOTHER account had used a
   * given write_id, by observing `write_id_reuse` instead of an apply.
   *
   * red-proof: drop the account from `keyOf`. APPLIED AND OBSERVED RED.
   */
  test("a write_id recorded for one account is fresh for another", () => {
    const registry = createInMemoryWriteIdRegistry();
    registry.record({
      accountId: ACCOUNT, writeId: WRITE_ID, fingerprintOf: envelopeContent(7, "a"),
      accountEpoch: 7, outcome: OUTCOME,
    });
    expect(registry.lookup(OTHER_ACCOUNT, WRITE_ID, envelopeContent(7, "DIFFERENT"))).toEqual({ kind: "fresh" });
  });

  /**
   * The key is (account, write_id) and it is built length-prefixed, so no pair
   * of account ids can collide by concatenation.
   *
   * red-proof: build the key as `${accountId}:${writeId}` — account "a" with
   * write id "b:c" then collides with account "a:b" and id "c".
   * APPLIED AND OBSERVED RED.
   */
  test("account ids containing the separator cannot collide", () => {
    const registry = createInMemoryWriteIdRegistry();
    registry.record({ accountId: "a", writeId: "b:c", fingerprintOf: { v: 1 }, accountEpoch: 1, outcome: OUTCOME });
    expect(registry.lookup("a:b", "c", { v: 2 })).toEqual({ kind: "fresh" });
  });
});

describe("GC is keyed to epoch advance, not to a timer (ruling B5)", () => {
  /**
   * red-proof: change `row.accountEpoch >= activeEpoch` to `>` in
   * `collectBelowEpoch` — the row AT the active epoch is then collected while a
   * replay of it is still admitted by the fence, so the next replay applies a
   * second time. APPLIED AND OBSERVED RED.
   */
  test("rows below the active epoch go; rows AT it stay", () => {
    const registry = createInMemoryWriteIdRegistry();
    for (const [id, epoch] of [["1", 5], ["2", 6], ["3", 7]] as const) {
      registry.record({
        accountId: ACCOUNT, writeId: id.repeat(64), fingerprintOf: { v: epoch },
        accountEpoch: epoch, outcome: OUTCOME,
      });
    }
    expect(registry.size(ACCOUNT)).toBe(3);
    expect(registry.collectBelowEpoch(ACCOUNT, 7)).toBe(2);
    expect(registry.size(ACCOUNT)).toBe(1);
    expect(registry.lookup(ACCOUNT, "3".repeat(64), { v: 7 })).toEqual({ kind: "replay", outcome: OUTCOME });
    expect(registry.lookup(ACCOUNT, "1".repeat(64), { v: 5 })).toEqual({ kind: "fresh" });
  });

  /**
   * red-proof: make `collectBelowEpoch` ignore its account argument and sweep
   * every account. APPLIED AND OBSERVED RED.
   */
  test("collecting one account does not touch another", () => {
    const registry = createInMemoryWriteIdRegistry();
    registry.record({ accountId: ACCOUNT, writeId: WRITE_ID, fingerprintOf: { v: 1 }, accountEpoch: 1, outcome: OUTCOME });
    registry.record({ accountId: OTHER_ACCOUNT, writeId: WRITE_ID, fingerprintOf: { v: 1 }, accountEpoch: 1, outcome: OUTCOME });
    expect(registry.collectBelowEpoch(ACCOUNT, 9)).toBe(1);
    expect(registry.size(OTHER_ACCOUNT)).toBe(1);
  });
});
