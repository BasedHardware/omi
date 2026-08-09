/**
 * Ruling B3's straggler table.
 *
 * These rows hold user content retained server-side after a refusal, which is
 * the record class whose retention window fable declined to sign and David
 * personally signed at 90 days. B3 signs the STRUCTURE on one condition — that
 * the rows join the ADR-014 lifecycle *by construction*, so deletion dominates
 * them with no separate mechanism and export covers them. That condition is a
 * property of this module's shape, so it is asserted as one.
 */

import { describe, expect, test } from "bun:test";

import {
  RETENTION_CAP_DAYS,
  RETENTION_CAP_SECONDS,
  createInMemoryStragglerTable,
  type PreservedEnvelope,
} from "./straggler-table";

const ACCOUNT = "acct-straggler-fixture";
const OTHER_ACCOUNT = "acct-straggler-other";
const NOW = 1_700_000_000;

const row = (overrides: Partial<PreservedEnvelope> = {}): PreservedEnvelope => ({
  envelope_json: '{"write_id":"' + "a".repeat(64) + '","account_epoch":6,"domain":"tasks","op":{"op":"patch","record_id":"t","patch":{"title":"buy oat milk"}}}',
  write_id: "a".repeat(64),
  account_epoch: 6,
  retained_at_epoch_seconds: NOW,
  ...overrides,
});

describe("the row is the whole envelope, not a summary", () => {
  /**
   * `COORD-cross-generation-writes.md`: "A human handed that record knows an
   * edit was lost and roughly what it was, but cannot reproduce it." The patch
   * is the reproducible part and it must survive.
   *
   * red-proof: have `preserve` store `{ write_id, account_epoch }` and drop
   * `envelope_json`.
   */
  test("the exact request bytes survive, patch included", () => {
    const table = createInMemoryStragglerTable();
    const preserved = row();
    table.preserve(ACCOUNT, preserved);
    const exported = table.exportAccount(ACCOUNT);
    expect(exported).toHaveLength(1);
    expect(exported[0]?.envelope_json).toBe(preserved.envelope_json);
    expect(exported[0]?.envelope_json).toContain("buy oat milk");
  });
});

describe("B3's lifecycle join, as a property of the module's shape", () => {
  /**
   * THE STRUCTURAL CONDITION. The account id is the only key: there is no row
   * id, no global iterator, and no lookup that does not start from an account.
   * That is what makes "deletion dominates them with no separate mechanism"
   * true rather than promised — an account-scoped deletion cannot miss a row by
   * forgetting this module, because no reachable row is outside the account
   * being deleted.
   *
   * This test goes red when somebody adds a `listAll()` for convenience, which
   * is exactly when it should.
   */
  test("no reachable read path exists that is not account-scoped", () => {
    const table = createInMemoryStragglerTable();
    const accountScoped = new Set(["preserve", "exportAccount", "deleteAccount", "sweepExpired", "reset"]);
    expect(new Set(Object.keys(table))).toEqual(accountScoped);
    for (const method of ["exportAccount", "deleteAccount"] as const) {
      // Arity 1: the account, and nothing else that could widen the scope.
      expect(table[method].length).toBe(1);
    }
  });

  /**
   * red-proof: make `deleteAccount` a no-op returning 0.
   */
  test("deleting an account removes every one of its rows and nobody else's", () => {
    const table = createInMemoryStragglerTable();
    table.preserve(ACCOUNT, row());
    table.preserve(ACCOUNT, row({ write_id: "b".repeat(64) }));
    table.preserve(OTHER_ACCOUNT, row());

    expect(table.deleteAccount(ACCOUNT)).toBe(2);
    expect(table.exportAccount(ACCOUNT)).toEqual([]);
    expect(table.exportAccount(OTHER_ACCOUNT)).toHaveLength(1);
  });

  /**
   * red-proof: have `exportAccount` ignore its argument and return every row.
   */
  test("an export returns only the account it was asked about", () => {
    const table = createInMemoryStragglerTable();
    table.preserve(ACCOUNT, row());
    table.preserve(OTHER_ACCOUNT, row({ write_id: "c".repeat(64) }));
    expect(table.exportAccount(ACCOUNT).map((entry) => entry.write_id)).toEqual(["a".repeat(64)]);
  });
});

describe("the David-signed 90-day cap", () => {
  test("the constant is 90 days, in seconds", () => {
    expect(RETENTION_CAP_DAYS).toBe(90);
    expect(RETENTION_CAP_SECONDS).toBe(90 * 24 * 60 * 60);
  });

  /**
   * The mechanism exists and is callable. **Nothing schedules it**, and the
   * module header says so: until something does, the cap is a decision with an
   * implementation and no operational effect.
   *
   * FOUND A REAL BUG ON FIRST RUN: `sweepExpired` was written with `>` and
   * deleted the row exactly at the cap. A data-destructive off-by-one on a
   * David-signed retention window, caught by the assertion rather than by
   * reading the line.
   *
   * red-proof: change `>=` back to `>` in `sweepExpired`'s horizon comparison.
   */
  test("a row older than the cap is swept; a row exactly at the cap is kept", () => {
    const table = createInMemoryStragglerTable();
    table.preserve(ACCOUNT, row({ write_id: "old", retained_at_epoch_seconds: NOW - RETENTION_CAP_SECONDS - 1 }));
    table.preserve(ACCOUNT, row({ write_id: "edge", retained_at_epoch_seconds: NOW - RETENTION_CAP_SECONDS }));
    table.preserve(ACCOUNT, row({ write_id: "fresh", retained_at_epoch_seconds: NOW }));

    expect(table.sweepExpired(NOW)).toBe(1);
    expect(table.exportAccount(ACCOUNT).map((entry) => entry.write_id)).toEqual(["edge", "fresh"]);
  });
});
