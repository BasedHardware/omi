import { createHash } from "crypto";
import { describe, expect, it } from "vitest";

import {
  generateTvToken,
  hashTvToken,
  isTvLinkActive,
  safeEqualHex,
  tvLinkStatus,
} from "../tv-links";

describe("tv-links crypto", () => {
  it("hashes tokens with sha256 hex", () => {
    const token = "test-token-value";
    expect(hashTvToken(token)).toBe(
      createHash("sha256").update(token, "utf8").digest("hex")
    );
  });

  it("generates high-entropy tokens with matching hash/prefix", () => {
    const a = generateTvToken();
    const b = generateTvToken();
    expect(a.token).not.toEqual(b.token);
    expect(a.token.length).toBeGreaterThanOrEqual(40);
    expect(a.token).toMatch(/^[A-Za-z0-9_-]{32,64}$/);
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
    expect(tvLinkStatus({ revokedAt: null, expiresAt: null }, now)).toBe(
      "active"
    );
    expect(tvLinkStatus({ revokedAt: null, expiresAt: now + 1000 }, now)).toBe(
      "active"
    );
    expect(tvLinkStatus({ revokedAt: null, expiresAt: now - 1 }, now)).toBe(
      "expired"
    );
    expect(tvLinkStatus({ revokedAt: now, expiresAt: null }, now)).toBe(
      "revoked"
    );
    expect(isTvLinkActive({ revokedAt: null, expiresAt: now + 1 }, now)).toBe(
      true
    );
    expect(isTvLinkActive({ revokedAt: now, expiresAt: null }, now)).toBe(
      false
    );
  });
});
