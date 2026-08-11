import { describe, expect, test } from "bun:test";

import { DEFAULT_INTEGRATION_PORT, parseIntegrationPort } from "./port";

describe("parseIntegrationPort", () => {
  test("keeps the direct service default at 4851", () => {
    expect(parseIntegrationPort(undefined)).toBe(DEFAULT_INTEGRATION_PORT);
  });

  test("accepts zero for an explicitly OS-assigned loopback port", () => {
    expect(parseIntegrationPort("0")).toBe(0);
  });

  test.each(["1", "-1", "1023", "4851.5", "65536", "abc", ""]) (
    "rejects invalid integration port %j",
    (raw) => {
      expect(() => parseIntegrationPort(raw)).toThrow(Error);
    },
  );

  test("accepts bounded integer overrides", () => {
    expect(parseIntegrationPort("1024")).toBe(1024);
    expect(parseIntegrationPort("65535")).toBe(65535);
  });
});
