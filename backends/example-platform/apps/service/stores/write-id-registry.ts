/**
 * THE `write_id` REGISTRY — ruling B1's idempotency, server-side.
 *
 * The client has had a durable offline write queue for a long time, and its
 * durability argument ended in a sentence about the server: "opId idempotency on
 * the server absorbs the replay". No server ever did that. This is the module
 * where that sentence becomes true.
 *
 * ── WHAT A REPLAY IS, AND WHY IT IS A SUCCESS ────────────────────────────────
 *
 * An op that APPLIED, then crashed before its client-side tombstone, then saw an
 * interleaved write from another device, replays. Answering `conflict` there
 * tells the user a saved edit failed — a false failure, and the demonstrated
 * defect the ratified contract cites for why `base_revision` cannot be the
 * idempotency mechanism. So a replay is answered from the RECORDED OUTCOME, with
 * `idempotent: true`, and applies nothing.
 *
 * ── WHY THE FINGERPRINT IS NOT THE REQUEST BYTES ─────────────────────────────
 *
 * `write_id_reuse` means "the same key, laundering DIFFERENT content" — a buggy
 * adapter, not a retry. Detecting it by comparing the raw request bytes would be
 * wrong in a way that costs a user their edit: the ratified canonical-JSON
 * definition (`parseCanonicalJson`) preserves key order rather than fixing it, so
 * two serializations of the SAME op with different key order are both canonical
 * and both legitimate. A byte comparison would call the second one reuse, answer
 * 409, and the client would dead-letter an op that is identical to one that
 * already succeeded.
 *
 * So the fingerprint is taken over a KEY-SORTED normalization of the semantic
 * content of the envelope — domain, epoch and op — which is stable across any
 * legitimate re-serialization and still differs the instant any value differs.
 *
 * ── GC IS KEYED TO EPOCH ADVANCE, NOT A TIMER (RULING B5) ────────────────────
 *
 * A row is needed only while a replay of that `write_id` could still arrive AND
 * BE ACCEPTED. The fence runs before this registry, so once an account's epoch
 * advances past an op's epoch, every replay of that op is refused `stale_epoch`
 * and its row can never be consulted again. `collectBelowEpoch` is that rule,
 * expressed as the only thing that removes a row. There is deliberately no
 * clock here: a timer would be a guess about when a replay stops arriving,
 * where the epoch is a fact about when one stops being accepted.
 */

import { createHash } from "node:crypto";

/** What was answered the first time this `write_id` was seen and accepted. */
export interface RecordedWriteOutcome {
  readonly record_id: string;
  readonly revision: string | null;
}

export type WriteIdLookup =
  /** Never seen for this account. Apply it. */
  | { readonly kind: "fresh" }
  /** Seen, with the same content. Answer from the record; apply nothing. */
  | { readonly kind: "replay"; readonly outcome: RecordedWriteOutcome }
  /** Seen, with DIFFERENT content. Ruling B1's `write_id_reuse`. */
  | { readonly kind: "reuse" };

export interface WriteIdRegistry {
  /**
   * Both the account id and the `write_id` are part of the key. Scoping to the
   * account is not tidiness: a global key would let one caller learn whether
   * ANOTHER account had used a given `write_id`, by observing `write_id_reuse`
   * instead of an apply — an existence oracle over somebody else's traffic.
   */
  lookup(accountId: string, writeId: string, fingerprintOf: unknown): WriteIdLookup;
  /** Records the outcome of an applied op so its replay can be answered. */
  record(input: {
    readonly accountId: string;
    readonly writeId: string;
    readonly fingerprintOf: unknown;
    readonly accountEpoch: number;
    readonly outcome: RecordedWriteOutcome;
  }): void;
  /**
   * Ruling B5. Drops every row for this account whose op was created under an
   * epoch STRICTLY BELOW the now-active one. Returns how many rows went, so a
   * caller can assert that GC did something rather than assuming it.
   */
  collectBelowEpoch(accountId: string, activeEpoch: number): number;
  /** Rows currently held for an account. Test and QA observability only. */
  size(accountId: string): number;
  reset(): void;
}

interface RegistryRow {
  readonly fingerprint: string;
  readonly accountEpoch: number;
  readonly outcome: RecordedWriteOutcome;
}

/**
 * THE DEPTH BOUND, and the defect that produced it.
 *
 * `stableSerialize` recurses, and so does the ratified contract's canonical-JSON
 * verifier. They run at different points in the call stack, so they do not
 * overflow at the same input depth — and a constructed probe found the gap:
 * a 20,000-deep array nested inside the field bag PASSED
 * `parseWriteOpEnvelopeJson` (whose own recursion is inside a `try`, so an
 * overflow there is just a rejection) and then blew the stack in here, where
 * nothing was catching it. The route answered **500** on a client-controlled
 * input.
 *
 * "Deep enough to crash" is not a property any caller can be expected to know,
 * and relying on another module's recursion limit to protect this one's is
 * relying on a stack budget — a value that changes with the call path, the
 * engine and the day. So the bound is explicit, checked before anything
 * recurses, and answered as `validation`: the envelope is beyond what this
 * server will process, which is the same class as any other envelope it will
 * not accept.
 *
 * 64 is far above anything a task field bag has a reason to contain and far
 * below any engine's limit. *Reverses as one constant* if a real payload ever
 * needs more.
 */
export const MAX_FINGERPRINT_DEPTH = 64;

/**
 * True when a value nests deeper than the bound. ITERATIVE on purpose — a
 * recursive depth-checker would overflow on exactly the input it exists to
 * reject, which is the shape of the defect it was written for.
 */
export const exceedsFingerprintDepth = (value: unknown): boolean => {
  const stack: Array<{ node: unknown; depth: number }> = [{ node: value, depth: 0 }];
  while (stack.length > 0) {
    const { node, depth } = stack.pop()!;
    if (node === null || typeof node !== "object") continue;
    if (depth >= MAX_FINGERPRINT_DEPTH) return true;
    const children = Array.isArray(node)
      ? node
      : Object.values(node as Record<string, unknown>);
    for (const child of children) stack.push({ node: child, depth: depth + 1 });
  }
  return false;
};

/**
 * A deterministic, key-ORDER-INDEPENDENT serialization. Distinct from the
 * contract's canonical JSON on purpose, and the difference is the whole point of
 * this function — see the module header.
 *
 * Arrays keep their order (order is meaning in an array); object keys are sorted
 * (order is not meaning in an object).
 *
 * Callers must have refused over-depth input already; `fingerprint` asserts it
 * rather than trusting them, because the failure mode of not asserting is a
 * stack overflow rather than a wrong answer.
 */
export const stableSerialize = (value: unknown): string => {
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  if (Array.isArray(value)) return `[${value.map(stableSerialize).join(",")}]`;
  const entries = Object.keys(value as Record<string, unknown>).sort()
    .map((key) => `${JSON.stringify(key)}:${stableSerialize((value as Record<string, unknown>)[key])}`);
  return `{${entries.join(",")}}`;
};

const fingerprint = (value: unknown): string => {
  if (exceedsFingerprintDepth(value)) {
    // Reached only if a caller skipped the check. Failing here as a value error
    // beats failing as a stack overflow: one is catchable and named, the other
    // unwinds through the write path and answers 500.
    throw new TypeError("write-id registry: value nests deeper than MAX_FINGERPRINT_DEPTH");
  }
  return createHash("sha256").update(stableSerialize(value), "utf8").digest("hex");
};

const keyOf = (accountId: string, writeId: string): string =>
  `${accountId.length}:${accountId}:${writeId}`;

export const createInMemoryWriteIdRegistry = (): WriteIdRegistry => {
  const rows = new Map<string, RegistryRow>();
  /** account id -> its keys, so GC does not scan the whole registry. */
  const byAccount = new Map<string, Set<string>>();

  return Object.freeze({
    lookup(accountId: string, writeId: string, fingerprintOf: unknown): WriteIdLookup {
      const row = rows.get(keyOf(accountId, writeId));
      if (row === undefined) return { kind: "fresh" };
      return row.fingerprint === fingerprint(fingerprintOf)
        ? { kind: "replay", outcome: row.outcome }
        : { kind: "reuse" };
    },

    record(input: Parameters<WriteIdRegistry["record"]>[0]): void {
      const key = keyOf(input.accountId, input.writeId);
      rows.set(key, {
        fingerprint: fingerprint(input.fingerprintOf),
        accountEpoch: input.accountEpoch,
        outcome: input.outcome,
      });
      const keys = byAccount.get(input.accountId) ?? new Set<string>();
      keys.add(key);
      byAccount.set(input.accountId, keys);
    },

    collectBelowEpoch(accountId: string, activeEpoch: number): number {
      const keys = byAccount.get(accountId);
      if (keys === undefined) return 0;
      let removed = 0;
      for (const key of [...keys]) {
        const row = rows.get(key);
        if (row === undefined) {
          keys.delete(key);
          continue;
        }
        // STRICTLY below. A row at the active epoch is still replayable — the
        // fence admits an op stamped with the current epoch — and collecting it
        // would turn the next legitimate replay into a second apply.
        if (row.accountEpoch >= activeEpoch) continue;
        rows.delete(key);
        keys.delete(key);
        removed += 1;
      }
      return removed;
    },

    size(accountId: string): number {
      return byAccount.get(accountId)?.size ?? 0;
    },

    reset(): void {
      rows.clear();
      byAccount.clear();
    },
  });
};
