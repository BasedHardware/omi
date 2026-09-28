// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
import { describe, expect, test } from "bun:test";

import { normalizePlainJson } from "./plain-json";
import { buildContentSafeRecallTrace } from "./recall-integrity";

/**
 * THE PLAIN-DATA PROTOTYPE RULE — one rule for all of core.
 *
 *   A plain-data record may carry `Object.prototype` OR a null prototype.
 *   An array must carry `Array.prototype`.
 *
 * Why this test exists rather than a comment: core previously disagreed with
 * itself. `plain-json.ts` (and therefore `authorization-boundary.ts`) accepted a
 * null prototype, while `application-read.ts` and `recall-integrity.ts` accepted
 * only `Object.prototype`. Drivers emit null-prototype records **deliberately**
 * — `drivers/sqlite/application-recall-read.ts` builds its detached output with
 * `Object.create(null)` — so the authorization layer admitted a record the read
 * layer then refused, and the failure surfaced at the read looking like a read
 * fault instead of the contract mismatch it was.
 *
 * That is exactly the class of assumption a future Postgres or Cloud SQL adapter
 * would rediscover the hard way, so it is stated once, here.
 *
 * red-proof: revert either boundary to `!== Object.prototype` and the matching
 * case below fails.
 */

const nullProtoRecord = (entries: Record<string, unknown>): Record<string, unknown> => {
  const output = Object.create(null) as Record<string, unknown>;
  for (const [key, value] of Object.entries(entries)) output[key] = value;
  return output;
};

describe("plain-data prototype rule", () => {
  test("normalizePlainJson accepts a null-prototype record", () => {
    const value = nullProtoRecord({ a: 1, b: "two" });
    expect(normalizePlainJson(value)).toEqual({ a: 1, b: "two" });
  });

  test("normalizePlainJson accepts a null-prototype record nested in a plain one", () => {
    const value = { outer: nullProtoRecord({ inner: nullProtoRecord({ deep: true }) }) };
    expect(normalizePlainJson(value)).toEqual({ outer: { inner: { deep: true } } });
  });

  test("recall-integrity accepts null-prototype stage records", () => {
    // Exercises recall-integrity's detach boundary through its public builder.
    const traceRef = `tr1_${"a".repeat(64)}` as const;
    const stages = nullProtoRecord({
      eligible: [traceRef],
      selected: [traceRef],
      hydrated: [traceRef],
      policyEligible: [traceRef],
      cited: [traceRef],
      grounded: [traceRef],
    });
    const trace = buildContentSafeRecallTrace(nullProtoRecord({
      version: "recall-trace-v1",
      traceRef,
      strategyVersion: "prototype-rule-test",
      projectionFreshness: "fresh",
      outcome: "grounded",
      latencyMs: 0,
      tokenCounts: nullProtoRecord({ input: 0, output: 0 }),
      stages,
    }) as never);
    expect(trace.traceRef).toBe(traceRef);
  });

  test("an array must still carry Array.prototype", () => {
    const exotic = Object.create(null) as { length: number };
    exotic.length = 0;
    // A null-prototype object is a record, not an array, and is accepted as one.
    expect(normalizePlainJson(exotic)).toEqual({ length: 0 });

    // But a real array with a mangled prototype is rejected.
    const mangled: unknown[] = [];
    Object.setPrototypeOf(mangled, null);
    expect(() => normalizePlainJson(mangled)).toThrow(TypeError);
  });

  test("`__proto__` as an own key does not pollute the copy", () => {
    // The reason accepting null prototypes is safe: `__proto__` becomes an
    // ordinary own key, and the copy is written with Object.defineProperty
    // rather than assignment, so no setter runs and no prototype is mutated.
    const hostile = nullProtoRecord({ ["__proto__"]: { polluted: true }, safe: 1 });
    const copied = normalizePlainJson(hostile) as Record<string, unknown>;
    expect(Object.getPrototypeOf(copied)).not.toBe(null);
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
    expect(Object.prototype.hasOwnProperty.call(copied, "__proto__")).toBe(true);
    expect(copied.safe).toBe(1);
  });
});
