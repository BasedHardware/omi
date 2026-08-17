import { createHmac } from "node:crypto";
import { describe, expect, test } from "bun:test";

import {
  createDevTokenIssuer,
  devPrincipalToAuthorizationRequest,
  type DevTokenIssuerConfig,
  type DevTokenSigningKeyset,
} from "./dev-token";

const SECRET_A = new Uint8Array(32).fill(17);
const SECRET_B = new Uint8Array(32).fill(29);
const NOW = 1_800_000_000;
const TTL = 300;

const primaryKeyset: DevTokenSigningKeyset = {
  active_key_id: "dev-a",
  keys: [{ key_id: "dev-a", secret: SECRET_A }],
};

const rotatedKeyset: DevTokenSigningKeyset = {
  active_key_id: "dev-b",
  keys: [
    { key_id: "dev-b", secret: SECRET_B },
    { key_id: "dev-a", secret: SECRET_A },
  ],
};

const config = (keyset: DevTokenSigningKeyset = primaryKeyset, ttl_seconds = TTL): DevTokenIssuerConfig => ({
  signing_keyset: keyset,
  ttl_seconds,
});

const issuer = (keyset: DevTokenSigningKeyset = primaryKeyset) => createDevTokenIssuer(config(keyset));

const resign = (token: string, payloadText: string, secret = SECRET_A, keyId?: string): string => {
  const [prefix, originalKeyId] = token.split(".");
  const selectedKeyId = keyId ?? originalKeyId!;
  const payload = Buffer.from(payloadText, "utf8").toString("base64url");
  const signature = createHmac("sha256", secret)
    .update(`${prefix}.${selectedKeyId}.${payload}`, "ascii")
    .digest("base64url");
  return `${prefix}.${selectedKeyId}.${payload}.${signature}`;
};

const decodedPayload = (token: string): Record<string, unknown> => {
  const payload = token.split(".")[2]!;
  return JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as Record<string, unknown>;
};

describe("dev-mode token issuer/verifier seam", () => {
  test("issues a deterministic dev1 token and resolves the exact principal content", () => {
    const tokens = issuer();
    const first = tokens.issue("alice", NOW);
    const second = tokens.issue("alice", NOW);
    const principal = tokens.resolve(first, NOW + 120);

    expect(first).toBe(second);
    expect(first.startsWith("dev1.dev-a.")).toBeTrue();
    expect(principal).toEqual({ uid: "alice" });
    expect(Object.isFrozen(principal)).toBeTrue();
    expect(decodedPayload(first)).toEqual({
      version: 1,
      uid: "alice",
      issued_at_epoch_seconds: NOW,
      expires_at_epoch_seconds: NOW + TTL,
    });
  });

  // red-proof: change expected uid "alice" to "bob" (or drop the not.toBe check)
  test("a token issued for uid A never resolves to uid B", () => {
    const tokens = issuer();
    const tokenA = tokens.issue("alice", NOW);
    const resolved = tokens.resolve(tokenA, NOW + 1);

    expect(resolved).toEqual({ uid: "alice" });
    expect(resolved!.uid).not.toBe("bob");
    expect(tokens.resolve(tokenA, NOW + 1)).not.toEqual({ uid: "bob" });

    const tokenB = tokens.issue("bob", NOW);
    expect(tokens.resolve(tokenB, NOW + 1)).toEqual({ uid: "bob" });
    expect(tokenB).not.toBe(tokenA);
    expect(decodedPayload(tokenA).uid).toBe("alice");
    expect(decodedPayload(tokenB).uid).toBe("bob");
  });

  // red-proof: change any failure-mode expectation from null to a reason object / throw
  test("every distinct verification failure mode returns the byte-identical null result", () => {
    const tokens = issuer();
    const good = tokens.issue("alice", NOW);
    const [prefix, keyId, payload, signature] = good.split(".") as [string, string, string, string];
    const payloadBitflip = `${payload.slice(0, -1)}${payload.at(-1) === "A" ? "B" : "A"}`;
    const signatureBitflip = `${signature.slice(0, -1)}${signature.at(-1) === "A" ? "B" : "A"}`;
    const originalPayload = decodedPayload(good);

    const unknownKeyId = `${prefix}.unknown-key.${payload}.${signature}`;
    const badSignature = `${prefix}.${keyId}.${payload}.${signatureBitflip}`;
    const malformedBase64 = `${prefix}.${keyId}.${payload}.!`;
    const expired = good;
    const wrongVersion = resign(good, JSON.stringify({
      ...originalPayload,
      version: 2,
    }));
    const tamperedPayload = `${prefix}.${keyId}.${payloadBitflip}.${signature}`;
    const wrongPrefix = `mcp1.${keyId}.${payload}.${signature}`;
    const truncated = `${prefix}.${keyId}.${payload}`;

    const failures = [
      tokens.resolve(unknownKeyId, NOW + 1),
      tokens.resolve(badSignature, NOW + 1),
      tokens.resolve(malformedBase64, NOW + 1),
      tokens.resolve(expired, NOW + TTL),
      tokens.resolve(wrongVersion, NOW + 1),
      tokens.resolve(tamperedPayload, NOW + 1),
      tokens.resolve(wrongPrefix, NOW + 1),
      tokens.resolve(truncated, NOW + 1),
      tokens.resolve("", NOW + 1),
      tokens.resolve("legacy-bearer-alice", NOW + 1),
    ];

    for (const result of failures) {
      expect(result).toBeNull();
      expect(result).toBe(null);
      expect(JSON.stringify(result)).toBe("null");
    }
    expect(new Set(failures.map((result) => JSON.stringify(result)))).toEqual(new Set(["null"]));
    expect(tokens.resolve(good, NOW + 1)).toEqual({ uid: "alice" });
  });

  test("rotates signing keys without invalidating retained-key tokens", () => {
    const oldIssuer = issuer(primaryKeyset);
    const rotated = issuer(rotatedKeyset);
    const oldToken = oldIssuer.issue("alice", NOW);
    const newToken = rotated.issue("alice", NOW);

    expect(rotated.resolve(oldToken, NOW + 1)).toEqual({ uid: "alice" });
    expect(rotated.resolve(newToken, NOW + 1)).toEqual({ uid: "alice" });
    expect(newToken.startsWith("dev1.dev-b.")).toBeTrue();
    expect(issuer({
      active_key_id: "dev-b",
      keys: [{ key_id: "dev-b", secret: SECRET_B }],
    }).resolve(oldToken, NOW + 1)).toBeNull();
  });

  test("snapshots signing secrets at factory creation so later mutation cannot forge", () => {
    const mutableSecret = new Uint8Array(32).fill(17);
    const tokens = createDevTokenIssuer({
      signing_keyset: {
        active_key_id: "dev-a",
        keys: [{ key_id: "dev-a", secret: mutableSecret }],
      },
      ttl_seconds: TTL,
    });
    const token = tokens.issue("alice", NOW);
    mutableSecret.fill(0);
    expect(tokens.resolve(token, NOW + 1)).toEqual({ uid: "alice" });
    expect(issuer(primaryKeyset).resolve(token, NOW + 1)).toEqual({ uid: "alice" });
  });

  // red-proof: change credential_kind to "developer_api_key" or consumer to "developer_api"
  test("maps a DevPrincipal onto mcp_api_key / mcp authorization request content", () => {
    const request = devPrincipalToAuthorizationRequest(
      { uid: "alice" },
      { app_id: "app:dev", key_id: "key:dev" },
    );

    expect(request).toEqual({
      owner_account_id: "alice",
      credential: {
        owner_account_id: "alice",
        credential_kind: "mcp_api_key",
        app_id: "app:dev",
        key_id: "key:dev",
        scopes: ["memories.read"],
        active: true,
      },
      persisted_grant: {
        owner_account_id: "alice",
        consumer: "mcp",
        app_id: "app:dev",
        key_id: "key:dev",
        enabled: true,
        default_read: true,
        scopes: ["memories.read"],
      },
    });
    expect(request.credential.credential_kind).toBe("mcp_api_key");
    expect(request.persisted_grant!.consumer).toBe("mcp");
    expect(request.credential.scopes).toEqual(["memories.read"]);
    expect(request.persisted_grant!.scopes).toEqual(["memories.read"]);
    expect(Object.isFrozen(request)).toBeTrue();
    expect(Object.isFrozen(request.credential)).toBeTrue();
    expect(Object.isFrozen(request.persisted_grant)).toBeTrue();
  });

  test("rejects hostile issuer config and issue inputs without invoking getters", () => {
    let secretGetterCalls = 0;
    let ttlGetterCalls = 0;
    const getterKey = { key_id: "dev-a" } as Record<string, unknown>;
    Object.defineProperty(getterKey, "secret", {
      enumerable: true,
      get: () => { secretGetterCalls++; return SECRET_A; },
    });
    const getterConfig = { signing_keyset: primaryKeyset } as Record<string, unknown>;
    Object.defineProperty(getterConfig, "ttl_seconds", {
      enumerable: true,
      get: () => { ttlGetterCalls++; return TTL; },
    });

    expect(() => createDevTokenIssuer(getterConfig as unknown as DevTokenIssuerConfig)).toThrow(TypeError);
    expect(() => createDevTokenIssuer({
      signing_keyset: {
        active_key_id: "dev-a",
        keys: [getterKey as unknown as DevTokenSigningKeyset["keys"][number]],
      },
      ttl_seconds: TTL,
    })).toThrow(TypeError);
    expect(() => createDevTokenIssuer({
      signing_keyset: primaryKeyset,
      ttl_seconds: 0,
    })).toThrow(TypeError);
    expect(() => createDevTokenIssuer({
      signing_keyset: {
        active_key_id: "dev-a",
        keys: [{ key_id: "dev-a", secret: new Uint8Array(31) }],
      },
      ttl_seconds: TTL,
    })).toThrow(TypeError);
    expect(() => issuer().issue("", NOW)).toThrow(TypeError);
    expect(() => issuer().issue("alice", -1)).toThrow(TypeError);
    expect(secretGetterCalls).toBe(0);
    expect(ttlGetterCalls).toBe(0);
  });

  test("rejects non-canonical resigned payloads and pre-issuance clocks with null", () => {
    const tokens = issuer();
    const token = tokens.issue("alice", NOW);
    const payload = decodedPayload(token);
    const nonCanonical = JSON.stringify(payload, null, 2);
    const unknownField = JSON.stringify({ ...payload, role: "admin" });
    const emptyUid = JSON.stringify({ ...payload, uid: "" });

    expect(tokens.resolve(resign(token, nonCanonical), NOW + 1)).toBeNull();
    expect(tokens.resolve(resign(token, unknownField), NOW + 1)).toBeNull();
    expect(tokens.resolve(resign(token, emptyUid), NOW + 1)).toBeNull();
    expect(tokens.resolve(token, NOW - 1)).toBeNull();
  });
});
