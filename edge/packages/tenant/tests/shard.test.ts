import { describe, expect, it } from "vitest";
import { defaultTenantRecord, shardIdForUid } from "../src/index.js";

describe("shardIdForUid", () => {
  it("stable for same uid", () => {
    expect(shardIdForUid("abc", 64)).toBe(shardIdForUid("abc", 64));
  });

  it("in range", () => {
    for (const uid of ["a", "user_1", "zzz", "uid-long-name-here"]) {
      const s = shardIdForUid(uid, 16);
      expect(s).toMatch(/^shard_\d{4}$/);
      const n = Number(s.slice(6));
      expect(n).toBeGreaterThanOrEqual(0);
      expect(n).toBeLessThan(16);
    }
  });

  it("defaultTenantRecord fills indexes", () => {
    const t = defaultTenantRecord("u1", { shardCount: 8 });
    expect(t.uid).toBe("u1");
    expect(t.d1DatabaseId).toMatch(/^shard_/);
    expect(t.vectorizeIndex).toContain(t.d1DatabaseId);
    expect(t.status).toBe("active");
  });
});
