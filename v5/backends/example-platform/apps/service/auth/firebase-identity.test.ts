import { describe, expect, test } from "bun:test";

import {
  createFirebaseIdentityVerifier,
  FIREBASE_ID_TOKEN_VERIFICATION_UNAVAILABLE,
  FIREBASE_IDENTITY_REFRESH_UNAVAILABLE,
  FIREBASE_REVOCATION_RECHECK_WINDOW_SECONDS,
  isFirebaseIdentityRefreshUnavailable,
  type FirebaseIdTokenVerificationAdapter,
  type FirebaseIdentityVerifierConfig,
} from "./firebase-identity";

const PROJECT = "omi-fixture-project";
const NOW = 1_800_000_000;
const SIGNED_TOKEN = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.signature";
const OTHER_SIGNED_TOKEN = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJvdGhlciJ9.signature";
const UNSIGNED_TOKEN = "eyJhbGciOiJub25lIn0.eyJzdWIiOiJ1c2VyIn0.";

const claims = (overrides: Record<string, unknown> = {}): Record<string, unknown> => ({
  aud: PROJECT,
  iss: `https://securetoken.google.com/${PROJECT}`,
  sub: "firebase-user-1",
  uid: "firebase-user-1",
  exp: NOW + 3_600,
  iat: NOW - 60,
  auth_time: NOW - 120,
  ...overrides,
});

const adapter = (
  decoded: unknown,
  calls: { value: number; checkRevoked: unknown; flags: boolean[] },
  source: FirebaseIdTokenVerificationAdapter["verification_source"] = "firebase_production",
): FirebaseIdTokenVerificationAdapter => ({
  verification_source: source,
  async verifyIdToken(_token: string, checkRevoked: boolean): Promise<unknown> {
    calls.value += 1;
    calls.checkRevoked = checkRevoked;
    calls.flags.push(checkRevoked);
    return decoded;
  },
});

const config = (
  candidate: FirebaseIdTokenVerificationAdapter,
  runtime: FirebaseIdentityVerifierConfig["runtime_mode"] = "deployed",
): FirebaseIdentityVerifierConfig => ({
  project_id: PROJECT,
  runtime_mode: runtime,
  adapter: candidate,
});

const emptyCalls = (): { value: number; checkRevoked: unknown; flags: boolean[] } => ({
  value: 0,
  checkRevoked: null,
  flags: [],
});

describe("Firebase identity-only verification", () => {
  test("pins project claims, verifies signature locally, then checks revocation before returning identity only", async () => {
    const calls = emptyCalls();
    const verifier = createFirebaseIdentityVerifier(config(adapter(claims({
      email: "private@example.invalid",
      phone_number: "+15555550100",
      admin: true,
    }), calls)));
    const identity = await verifier.resolve(SIGNED_TOKEN, NOW);

    expect(calls.flags).toEqual([false, true]);
    expect(calls.checkRevoked).toBe(true);
    expect(identity).toEqual({
      firebase_project_id: PROJECT,
      firebase_uid: "firebase-user-1",
      authentication_strength: "firebase-id-token",
      expires_at_epoch_seconds: NOW + 3_600,
    });
    expect(Object.isFrozen(identity)).toBe(true);
    expect(JSON.stringify(identity)).not.toContain("private@example.invalid");
    expect(JSON.stringify(identity)).not.toContain("phone_number");
    expect(JSON.stringify(identity)).not.toContain("admin");
    expect(JSON.stringify(identity)).not.toContain(SIGNED_TOKEN);
  });

  test("wrong project, subject, and token time claims all fail identically without a revocation round trip", async () => {
    const invalid: readonly Record<string, unknown>[] = [
      { aud: "other-project" },
      { iss: "https://securetoken.google.com/other-project" },
      { sub: "" },
      { sub: "x".repeat(129), uid: "x".repeat(129) },
      { uid: "different-user" },
      { exp: NOW },
      { exp: NOW - 1 },
      { exp: Number.MAX_SAFE_INTEGER + 1 },
      { iat: NOW + 1 },
      { auth_time: NOW + 1 },
      { auth_time: Number.NaN },
    ];
    for (const overrides of invalid) {
      const calls = emptyCalls();
      const result = await createFirebaseIdentityVerifier(config(adapter(
        claims(overrides),
        calls,
      ))).resolve(SIGNED_TOKEN, NOW);
      expect(result).toBeNull();
      expect(calls.flags).toEqual([false]);
    }
  });

  test("malformed tokens and clocks fail before the adapter", async () => {
    const malformed = [
      "",
      "one.two",
      "one.two.three.four",
      "not+base64.payload.signature",
      "header.payload.",
      `a.${"b".repeat(16_384)}.c`,
    ];
    const calls = emptyCalls();
    const verifier = createFirebaseIdentityVerifier(config(adapter(claims(), calls)));
    for (const token of malformed) expect(await verifier.resolve(token, NOW)).toBeNull();
    for (const clock of [-1, 0.5, Number.NaN, Number.MAX_SAFE_INTEGER + 1]) {
      expect(await verifier.resolve(SIGNED_TOKEN, clock)).toBeNull();
    }
    expect(calls.value).toBe(0);
  });

  test("adapter failures, hostile claims, and raw details collapse to null", async () => {
    const sentinel = "raw Firebase provider detail";
    for (const verifyIdToken of [
      () => { throw new Error(sentinel); },
      () => Promise.reject(new Error(sentinel)),
    ]) {
      const result = await createFirebaseIdentityVerifier(config({
        verification_source: "firebase_production",
        async verifyIdToken(): Promise<unknown> {
          return await verifyIdToken();
        },
      })).resolve(SIGNED_TOKEN, NOW);
      expect(result).toBeNull();
      expect(JSON.stringify(result)).not.toContain(sentinel);
    }

    let getterCalls = 0;
    const accessorClaims = Object.create(Object.prototype, {
      ...Object.fromEntries(Object.entries(claims()).map(([key, value]) => [key, {
        enumerable: true,
        value,
      }])),
      email: {
        enumerable: true,
        get: () => { getterCalls += 1; return sentinel; },
      },
    });
    class ClaimClass {
      aud = PROJECT;
    }
    for (const decoded of [
      accessorClaims,
      new Proxy(claims(), {}),
      new ClaimClass(),
      { ...claims(), exp: "later" },
      { ...claims(), sub: "bad\u0000uid", uid: "bad\u0000uid" },
    ]) {
      const calls = emptyCalls();
      expect(await createFirebaseIdentityVerifier(config(adapter(decoded, calls)))
        .resolve(SIGNED_TOKEN, NOW)).toBeNull();
      expect(calls.flags).toEqual([false]);
    }
    expect(getterCalls).toBe(0);
  });

  test("deployed mode refuses emulator construction; local emulator alone accepts unsigned shape", async () => {
    const deployedCalls = emptyCalls();
    expect(() => createFirebaseIdentityVerifier(config(adapter(
      claims(),
      deployedCalls,
      "firebase_auth_emulator",
    )))).toThrow("forbids");
    expect(deployedCalls.value).toBe(0);

    const localCalls = emptyCalls();
    const local = createFirebaseIdentityVerifier(config(adapter(
      claims(),
      localCalls,
      "firebase_auth_emulator",
    ), "local_test"));
    expect(await local.resolve(UNSIGNED_TOKEN, NOW)).toEqual({
      firebase_project_id: PROJECT,
      firebase_uid: "firebase-user-1",
      authentication_strength: "firebase-id-token",
      expires_at_epoch_seconds: NOW + 3_600,
    });
    expect(localCalls.flags).toEqual([false, true]);

    const productionLocalCalls = emptyCalls();
    const productionLocal = createFirebaseIdentityVerifier(config(adapter(
      claims(),
      productionLocalCalls,
    ), "local_test"));
    expect(await productionLocal.resolve(UNSIGNED_TOKEN, NOW)).toBeNull();
    expect(productionLocalCalls.value).toBe(0);
  });

  test("config and adapter containers are exact plain data", () => {
    const calls = emptyCalls();
    const validAdapter = adapter(claims(), calls);
    expect(() => createFirebaseIdentityVerifier({ ...config(validAdapter), extra: true } as never))
      .toThrow("unexpected fields");
    expect(() => createFirebaseIdentityVerifier({ ...config(validAdapter), project_id: "bad/project" }))
      .toThrow("invalid Firebase identity configuration");
    expect(() => createFirebaseIdentityVerifier({
      ...config(validAdapter),
      adapter: { ...validAdapter, extra: true },
    } as never)).toThrow("unexpected fields");
    expect(() => createFirebaseIdentityVerifier(new Proxy(config(validAdapter), {})))
      .toThrow("expected exact plain data");

    let getterCalls = 0;
    const accessorConfig = Object.create(Object.prototype, {
      project_id: { enumerable: true, get: () => { getterCalls += 1; return PROJECT; } },
      runtime_mode: { enumerable: true, value: "deployed" },
      adapter: { enumerable: true, value: validAdapter },
    });
    expect(() => createFirebaseIdentityVerifier(accessorConfig)).toThrow("accessors");
    expect(getterCalls).toBe(0);
    expect(calls.value).toBe(0);
  });

  test("the returned identity is detached from later decoded-claim mutation", async () => {
    const decoded = claims();
    const calls = emptyCalls();
    const identity = await createFirebaseIdentityVerifier(config(adapter(decoded, calls)))
      .resolve(SIGNED_TOKEN, NOW);
    decoded.uid = "mutated";
    decoded.exp = NOW + 99_999;
    expect(identity).toEqual({
      firebase_project_id: PROJECT,
      firebase_uid: "firebase-user-1",
      authentication_strength: "firebase-id-token",
      expires_at_epoch_seconds: NOW + 3_600,
    });
  });

  test("the revocation window is one named 15-minute constant", () => {
    expect(FIREBASE_REVOCATION_RECHECK_WINDOW_SECONDS).toBe(15 * 60);
  });

  test("a token revoked at Google is still accepted inside the 15-minute window", async () => {
    let revocationCalls = 0;
    const flags: boolean[] = [];
    const verifier = createFirebaseIdentityVerifier(config({
      verification_source: "firebase_production",
      async verifyIdToken(_token: string, checkRevoked: boolean): Promise<unknown> {
        flags.push(checkRevoked);
        if (checkRevoked) {
          revocationCalls += 1;
          if (revocationCalls > 1) throw new Error("revoked-at-google");
        }
        return claims();
      },
    }));
    expect(await verifier.resolve(SIGNED_TOKEN, NOW)).toMatchObject({
      firebase_uid: "firebase-user-1",
    });
    const insideWindow = await verifier.resolve(
      SIGNED_TOKEN,
      NOW + FIREBASE_REVOCATION_RECHECK_WINDOW_SECONDS - 1,
    );
    expect(insideWindow).toMatchObject({ firebase_uid: "firebase-user-1" });
    expect(revocationCalls).toBe(1);
    expect(flags.filter((flag) => flag)).toHaveLength(1);
    expect(flags).toEqual([false, true, false]);
  });

  test("a token revoked at Google is rejected after the window elapses", async () => {
    let revocationCalls = 0;
    const flags: boolean[] = [];
    const verifier = createFirebaseIdentityVerifier(config({
      verification_source: "firebase_production",
      async verifyIdToken(_token: string, checkRevoked: boolean): Promise<unknown> {
        flags.push(checkRevoked);
        if (checkRevoked) {
          revocationCalls += 1;
          if (revocationCalls > 1) throw new Error("revoked-at-google");
        }
        return claims();
      },
    }));
    expect(await verifier.resolve(SIGNED_TOKEN, NOW)).toMatchObject({
      firebase_uid: "firebase-user-1",
    });
    const afterWindow = await verifier.resolve(
      SIGNED_TOKEN,
      NOW + FIREBASE_REVOCATION_RECHECK_WINDOW_SECONDS,
    );
    expect(afterWindow).toBeNull();
    expect(revocationCalls).toBe(2);
    expect(flags).toEqual([false, true, false, true]);
  });

  test("offline inside the window still authenticates from the local signature check", async () => {
    let revocationCalls = 0;
    const flags: boolean[] = [];
    const verifier = createFirebaseIdentityVerifier(config({
      verification_source: "firebase_production",
      async verifyIdToken(_token: string, checkRevoked: boolean): Promise<unknown> {
        flags.push(checkRevoked);
        if (checkRevoked) {
          revocationCalls += 1;
          if (revocationCalls > 1) {
            throw new Error(FIREBASE_ID_TOKEN_VERIFICATION_UNAVAILABLE);
          }
        }
        return claims();
      },
    }));
    expect(await verifier.resolve(SIGNED_TOKEN, NOW)).toMatchObject({
      firebase_uid: "firebase-user-1",
    });
    const offlineInside = await verifier.resolve(SIGNED_TOKEN, NOW + 60);
    expect(offlineInside).toMatchObject({ firebase_uid: "firebase-user-1" });
    expect(isFirebaseIdentityRefreshUnavailable(offlineInside)).toBe(false);
    expect(revocationCalls).toBe(1);
    expect(flags).toEqual([false, true, false]);
  });

  test("offline after the window is an honest refresh failure, not a logout and not a grant", async () => {
    let revocationCalls = 0;
    const verifier = createFirebaseIdentityVerifier(config({
      verification_source: "firebase_production",
      async verifyIdToken(_token: string, checkRevoked: boolean): Promise<unknown> {
        if (checkRevoked) {
          revocationCalls += 1;
          if (revocationCalls > 1) {
            throw new Error(FIREBASE_ID_TOKEN_VERIFICATION_UNAVAILABLE);
          }
        }
        return claims();
      },
    }));
    expect(await verifier.resolve(SIGNED_TOKEN, NOW)).toMatchObject({
      firebase_uid: "firebase-user-1",
    });
    const afterWindow = await verifier.resolve(
      SIGNED_TOKEN,
      NOW + FIREBASE_REVOCATION_RECHECK_WINDOW_SECONDS,
    );
    expect(afterWindow).toBe(FIREBASE_IDENTITY_REFRESH_UNAVAILABLE);
    expect(isFirebaseIdentityRefreshUnavailable(afterWindow)).toBe(true);
    expect(afterWindow).not.toBeNull();
    expect(JSON.stringify(afterWindow)).toBe(JSON.stringify({
      kind: "firebase_identity_refresh_unavailable",
    }));
    expect(JSON.stringify(afterWindow)).not.toContain(SIGNED_TOKEN);
    expect(revocationCalls).toBe(2);
  });

  test("expiry and a different token are still checked inside the window", async () => {
    const flagsByToken = new Map<string, boolean[]>();
    const verifier = createFirebaseIdentityVerifier(config({
      verification_source: "firebase_production",
      async verifyIdToken(token: string, checkRevoked: boolean): Promise<unknown> {
        const flags = flagsByToken.get(token) ?? [];
        flags.push(checkRevoked);
        flagsByToken.set(token, flags);
        return claims();
      },
    }));
    expect(await verifier.resolve(SIGNED_TOKEN, NOW)).toMatchObject({
      firebase_uid: "firebase-user-1",
    });
    expect(await verifier.resolve(SIGNED_TOKEN, NOW + 3_600)).toBeNull();
    expect(await verifier.resolve(OTHER_SIGNED_TOKEN, NOW + 60)).toMatchObject({
      firebase_uid: "firebase-user-1",
    });
    expect(flagsByToken.get(SIGNED_TOKEN)).toEqual([false, true, false]);
    expect(flagsByToken.get(OTHER_SIGNED_TOKEN)).toEqual([false, true]);
  });

  test("the module never treats the raw token as a cache key", async () => {
    const source = await Bun.file(new URL("./firebase-identity.ts", import.meta.url)).text();
    expect(source).toContain("createHash(\"sha256\")");
    expect(source).toContain("FIREBASE_REVOCATION_RECHECK_WINDOW_SECONDS = 15 * 60");
    expect(source).not.toContain("revocationCheckedAt.set(token");
    expect(source).not.toContain("console.log");
    expect(source).not.toContain("process.env");
  });
});
