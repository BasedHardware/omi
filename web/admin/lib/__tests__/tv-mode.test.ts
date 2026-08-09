import { createHash } from "crypto";
import { describe, expect, it } from "vitest";

import {
  generateTvToken,
  hashTvToken,
  isTvLinkActive,
  safeEqualHex,
  tvLinkStatus,
} from "../tv-links";
import { daysUntilMillion, MILLION_USERS } from "../tv-snapshot";

describe("tv-links crypto", () => {
  it("hashes tokens with sha256 hex", () => {
    const token = "test-token-value";
    expect(hashTvToken(token)).toBe(
      createHash("sha256").update(token, "utf8").digest("hex"),
    );
  });

  it("generates high-entropy tokens with matching hash/prefix", () => {
    const a = generateTvToken();
    const b = generateTvToken();
    expect(a.token).not.toEqual(b.token);
    expect(a.token.length).toBeGreaterThanOrEqual(40);
    expect(a.tokenHash).toBe(hashTvToken(a.token));
    expect(a.prefix).toBe(a.token.slice(0, 8));
  });

  it("compares hex digests in constant-time style", () => {
    const h = hashTvToken("abc");
    expect(safeEqualHex(h, h)).toBe(true);
    expect(safeEqualHex(h, hashTvToken("xyz"))).toBe(false);
    expect(safeEqualHex("aa", "aabb")).toBe(false);
  });
});

describe("tv link status", () => {
  const now = 1_700_000_000_000;

  it("marks active / expired / revoked correctly", () => {
    expect(tvLinkStatus({ revokedAt: null, expiresAt: null }, now)).toBe("active");
    expect(tvLinkStatus({ revokedAt: null, expiresAt: now + 1000 }, now)).toBe(
      "active",
    );
    expect(tvLinkStatus({ revokedAt: null, expiresAt: now - 1 }, now)).toBe(
      "expired",
    );
    expect(tvLinkStatus({ revokedAt: now, expiresAt: null }, now)).toBe("revoked");
    expect(isTvLinkActive({ revokedAt: null, expiresAt: now + 1 }, now)).toBe(
      true,
    );
    expect(isTvLinkActive({ revokedAt: now, expiresAt: null }, now)).toBe(false);
  });
});

describe("daysUntilMillion", () => {
  it("returns 0 when already at/above target", () => {
    const m = daysUntilMillion(MILLION_USERS, []);
    expect(m.days).toBe(0);
    expect(m.totalUsers).toBe(MILLION_USERS);
  });

  it("projects days from recent average new users", () => {
    const daily = Array.from({ length: 10 }, (_, i) => ({
      day: `2026-01-${String(i + 1).padStart(2, "0")}`,
      newUsers: 1000,
    }));
    // asOf 2026-01-11 → completed window ends 2026-01-10
    const m = daysUntilMillion(900_000, daily, {
      rateDays: 7,
      asOf: "2026-01-11T12:00:00Z",
    });
    expect(m.perDay).toBe(1000);
    expect(m.days).toBe(100); // ceil(100000/1000)
  });

  it("averages over calendar days, zero-filling gaps", () => {
    // Only two non-zero days in a 7-day window ending 2026-01-10.
    const daily = [
      { day: "2026-01-04", newUsers: 7000 },
      { day: "2026-01-10", newUsers: 7000 },
    ];
    const m = daysUntilMillion(900_000, daily, {
      rateDays: 7,
      asOf: "2026-01-11T12:00:00Z",
    });
    // (7000 + 0*5 + 7000) / 7 = 2000
    expect(m.perDay).toBe(2000);
    expect(m.days).toBe(50); // ceil(100000/2000)
  });

  it("returns null days when rate is zero", () => {
    const m = daysUntilMillion(100, [{ day: "2026-01-01", newUsers: 0 }], {
      asOf: "2026-01-02T12:00:00Z",
    });
    expect(m.days).toBeNull();
  });
});
