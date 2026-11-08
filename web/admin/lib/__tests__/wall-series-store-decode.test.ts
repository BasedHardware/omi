import { describe, expect, it, vi } from "vitest";
import { decodeStoredPayload } from "../wall-series-store";

describe("decodeStoredPayload", () => {
  it("returns null for a missing document or an empty payload", () => {
    expect(decodeStoredPayload(undefined)).toBeNull();
    expect(decodeStoredPayload({})).toBeNull();
    expect(decodeStoredPayload({ payload: "" })).toBeNull();
  });

  it("parses a complete payload", () => {
    expect(decodeStoredPayload({ payload: '{"rows":[[1,2]]}' })).toEqual({
      rows: [[1, 2]],
    });
  });

  it("treats a truncated payload as absent instead of throwing", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(() =>
      decodeStoredPayload({ payload: '{"rows":[[1,2' })
    ).not.toThrow();
    expect(decodeStoredPayload({ payload: '{"rows":[[1,2' })).toBeNull();
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});
