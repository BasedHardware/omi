import { describe, expect, it } from "vitest";

import { canonicalInputHash } from "../src/runtime/tool-invocation-ledger.js";

describe("Swift/Node authorized tool input hash contract", () => {
  it("canonicalizes nested objects, arrays, unicode, nulls, and escaped text identically", () => {
    const input = {
      z: [3, { "é": "<tag>", a: true }, null],
      a: { two: 2, one: "line\nbreak" },
    };

    expect(canonicalInputHash(input)).toBe(
      "sha256:6f6a5fc2f37f5512e07808cd81aafc5b868c5573cff37ac67205713dd079f870",
    );
  });
});
