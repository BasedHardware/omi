import { expect, test } from "bun:test";
import { sha256CanonicalContent } from "./content-digest";

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
});
