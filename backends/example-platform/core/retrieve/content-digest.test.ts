import { expect, test } from "bun:test";
import { sha256CanonicalContent } from "./content-digest";
import { normalizePlainJson } from "./plain-json";

test("content digest rejects every non-JSON value instead of collapsing it", () => {
  class RecordClass { value = "x"; }
  const cyclic: Record<string, unknown> = {};
  cyclic.self = cyclic;
  let getterCalls = 0;
  const accessor = Object.defineProperty({}, "value", { enumerable: true, get: () => { getterCalls++; return "x"; } });
  const unsupported: unknown[] = [
    new Date("2026-01-01T00:00:00Z"),
    new Map([["x", 1]]),
    new RecordClass(),
    { value: undefined },
    { value: () => null },
    { value: Symbol("x") },
    { value: 1n },
    cyclic,
    accessor,
  ];
  for (const value of unsupported) expect(() => sha256CanonicalContent(value)).toThrow();
  expect(getterCalls).toBe(0);
});

test("content digest permits acyclic shared values and hashes them by JSON value", () => {
  const shared = { value: "x" };
  expect(sha256CanonicalContent({ left: shared, right: shared }))
    .toBe(sha256CanonicalContent({ left: { value: "x" }, right: { value: "x" } }));
  const normalized = normalizePlainJson({ right: shared, left: shared, negative_zero: -0 });
  expect(normalized.left).not.toBe(normalized.right);
  expect(Object.keys(normalized)).toEqual(["left", "negative_zero", "right"]);
  expect(Object.is(normalized.negative_zero, -0)).toBe(false);
});

test("plain arrays accept only length and every own in-range index", () => {
  const nonIndex: unknown[] = ["x"];
  Object.defineProperty(nonIndex, "4294967295", { value: "smuggled", enumerable: true });
  const hole = new Array(2);
  hole[1] = "x";
  const nonEnumerable: unknown[] = ["x"];
  Object.defineProperty(nonEnumerable, "hidden", { value: "smuggled", enumerable: false });
  const symbol: unknown[] = ["x"];
  Object.defineProperty(symbol, Symbol("hidden"), { value: "smuggled", enumerable: true });
  for (const value of [nonIndex, hole, nonEnumerable, symbol]) {
    expect(() => normalizePlainJson(value)).toThrow();
    expect(() => sha256CanonicalContent(value)).toThrow();
  }
});
