// @vitest-environment node
import { generateKeyPairSync, sign } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OAuth2Client } from "google-auth-library";
import { CertificateFormat } from "google-auth-library/build/src/auth/oauth2client";
import { NextRequest, NextResponse } from "next/server";

const firebase = vi.hoisted(() => ({
  verify: vi.fn(),
  doc: vi.fn(),
  collection: vi.fn(),
}));
vi.mock("@/lib/firebase/admin", () => ({
  verifyFirebaseToken: firebase.verify,
  getDb: () => ({ collection: firebase.collection }),
}));
vi.mock("@/lib/dev-auth", () => ({ DEV_BYPASS_ENABLED: false }));
vi.mock("@/lib/payload-cache", () => ({
  getPayload: async () => ({ data: { series: [] }, freshAt: 1 }),
  setPayload: vi.fn(),
  withFreshness: (data: object) => data,
}));
vi.mock("@/lib/services/user-growth", () => ({
  getUserGrowthSeries: vi.fn(),
  sliceSeries: vi.fn(),
}));

import { requireScope } from "@/lib/auth";
import { GET } from "@/app/api/omi/stats/daily-new-users/route";
import { GET as wallGET } from "@/app/api/omi/stats/wall/route";
vi.mock("@/lib/wall-cache", () => ({
  wallPayload: async () => ({ metrics: [{ value: 1 }] }),
  wallSnapshotStore: () => undefined,
}));
vi.mock("@/lib/wall-local-fixture", () => ({
  localWallFixture: async () => null,
}));
vi.mock("@/lib/wall-presentation", () => ({
  wallPresentation: (payload: unknown) => payload,
}));

const audience = "https://admin.omi.me/api/omi/stats";
const email = "omi-stats-reader@based-hardware.iam.gserviceaccount.com";
const { privateKey, publicKey } = generateKeyPairSync("rsa", {
  modulusLength: 2048,
});
const pem = publicKey.export({ type: "spki", format: "pem" }).toString();
const encoded = (value: unknown) =>
  Buffer.from(JSON.stringify(value)).toString("base64url");
function jwt(overrides: Record<string, unknown> = {}, key = privateKey) {
  const now = Math.floor(Date.now() / 1000);
  const input = `${encoded({ alg: "RS256", kid: "test-key" })}.${encoded({
    iss: "https://accounts.google.com",
    aud: audience,
    sub: "123456789",
    email,
    email_verified: true,
    iat: now - 10,
    exp: now + 3600,
    ...overrides,
  })}`;
  return `${input}.${sign("RSA-SHA256", Buffer.from(input), key).toString(
    "base64url"
  )}`;
}
const scoped = (req: NextRequest) => requireScope(req, "analytics:read");
function request(
  token: string,
  path = "/api/omi/stats/daily-new-users",
  method = "GET"
) {
  return new NextRequest(`https://admin.omi.me${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}` },
  });
}
async function denied(
  token: string,
  reason: string,
  path?: string,
  method?: string
) {
  const response = await requireScope(
    request(token, path, method),
    "analytics:read"
  );
  expect(response).toBeInstanceOf(NextResponse);
  expect((response as NextResponse).status).toBe(401);
  expect(console.info).toHaveBeenCalledTimes(1);
  const record = JSON.parse(vi.mocked(console.info).mock.calls[0][0]);
  expect(record).toMatchObject({
    event: "admin_stats_machine_auth",
    decision: "denied",
    reason,
  });
  expect(firebase.verify).not.toHaveBeenCalled();
  expect(firebase.collection).not.toHaveBeenCalled();
  expect(JSON.stringify(vi.mocked(console.info).mock.calls)).not.toContain(
    token
  );
}

beforeEach(() => {
  vi.stubEnv("ADMIN_STATS_READER_SAS", email);
  vi.stubEnv("ADMIN_STATS_READER_AUDIENCE", audience);
  vi.spyOn(console, "info").mockImplementation(() => {});
  // Only certificate retrieval is replaced; SDK signature and claim checks run.
  vi.spyOn(
    OAuth2Client.prototype,
    "getFederatedSignonCertsAsync"
  ).mockResolvedValue({
    certs: { "test-key": pem },
    format: CertificateFormat.PEM,
  });
  firebase.verify.mockReset();
  firebase.doc.mockReset().mockResolvedValue({ exists: true });
  firebase.collection
    .mockReset()
    .mockReturnValue({ doc: () => ({ get: firebase.doc }) });
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("stats-only Google machine identity", () => {
  it("reaches the merged wall GET with the same machine credential", async () => {
    expect((await wallGET(request(jwt(), "/api/omi/stats/wall"))).status).toBe(
      200
    );
    expect(firebase.verify).not.toHaveBeenCalled();
  });
  it("reaches a real stats GET without Firebase membership", async () => {
    const response = await GET(
      request(
        jwt(),
        "/api/omi/stats/daily-new-users?days=7&token=never-log-query"
      )
    );
    expect(response.status).toBe(200);
    expect(firebase.collection).not.toHaveBeenCalled();
    expect(firebase.verify).not.toHaveBeenCalled();
    expect(console.info).toHaveBeenCalledExactlyOnceWith(
      JSON.stringify({
        event: "admin_stats_machine_auth",
        decision: "allowed",
        reason: "allowed",
        route: "/api/omi/stats/daily-new-users",
      })
    );
  });
  it.each(["accounts.google.com", "https://accounts.google.com"])(
    "accepts Google's issuer %s and wall scope",
    async (iss) => {
      expect(
        await scoped(request(jwt({ iss }), "/api/omi/stats/wall"))
      ).toMatchObject({ uid: "stats-reader:123456789", kind: "stats-reader" });
    }
  );
  it.each([
    [{ aud: "https://other.example" }, "invalid_token"],
    [{ iss: "https://attacker.example" }, "invalid_token"],
    [
      { email: "other@based-hardware.iam.gserviceaccount.com" },
      "reader_not_allowed",
    ],
    [{ email_verified: false }, "email_unverified"],
    [{ email_verified: "true" }, "email_unverified"],
    [{ email: undefined }, "reader_not_allowed"],
    [{ exp: Math.floor(Date.now() / 1000) - 1 }, "expired"],
    [{ exp: Math.floor(Date.now() / 1000) - 600 }, "invalid_token"],
    [{ exp: undefined }, "invalid_token"],
  ])("rejects invalid signed claims %j", async (claims, reason) =>
    denied(jwt(claims), reason)
  );
  it("holds only the stats scopes it had before roles", async () => {
    const response = await requireScope(request(jwt()), "users:read");
    expect((response as NextResponse).status).toBe(403);
    expect(await requireScope(request(jwt()), "finance:read")).toMatchObject({
      kind: "stats-reader",
    });
  });
  it("rejects an unsigned JWT", async () => {
    const token = jwt().split(".");
    await denied(
      `${encoded({ alg: "none", kid: "test-key" })}.${token[1]}.`,
      "invalid_token"
    );
  });
  it("rejects an attacker signature", async () => {
    const attacker = generateKeyPairSync("rsa", { modulusLength: 2048 });
    await denied(jwt({}, attacker.privateKey), "invalid_token");
  });
  it("rejects malformed input without logging the SDK error", async () =>
    denied("not-a-jwt", "invalid_token"));
  it.each([
    "/api/omi/team-members",
    "/api/omi/users",
    "/api/omi/stats-admin",
    "/api/omi/stats",
  ])("rejects non-stats scope %s", async (path) =>
    denied(jwt(), "route_not_allowed", path)
  );
  it.each(["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])(
    "rejects %s on stats",
    async (method) => denied(jwt(), "method_not_allowed", undefined, method)
  );
  it.each(["ADMIN_STATS_READER_SAS", "ADMIN_STATS_READER_AUDIENCE"])(
    "fails closed without %s",
    async (key) => {
      vi.stubEnv(key, "");
      await denied(jwt(), "disabled");
    }
  );
  it("supports a comma or whitespace separated allowlist", async () => {
    vi.stubEnv(
      "ADMIN_STATS_READER_SAS",
      `other@project.iam.gserviceaccount.com, \n ${email}`
    );
    expect(await scoped(request(jwt()))).toMatchObject({
      uid: "stats-reader:123456789",
    });
  });
  it("does not allow human Google identities even when misconfigured in the allowlist", async () => {
    vi.stubEnv("ADMIN_STATS_READER_SAS", "human@example.com");
    await denied(jwt({ email: "human@example.com" }), "reader_not_allowed");
  });
  it("cannot turn forged Firebase claims into admin access", async () => {
    firebase.verify.mockResolvedValue(null);
    const response = await scoped(
      request(jwt({ iss: "https://securetoken.google.com/based-hardware" }))
    );
    expect((response as NextResponse).status).toBe(401);
    expect(firebase.collection).not.toHaveBeenCalled();
  });
});

describe("existing human Firebase admin authentication", () => {
  it.each(["GET", "POST"])(
    "retains membership checks outside stats for %s",
    async (method) => {
      firebase.verify.mockResolvedValue({ uid: "human-admin" });
      expect(
        await scoped(
          request(
            jwt({ iss: "https://securetoken.google.com/based-hardware" }),
            "/api/omi/team-members",
            method
          )
        )
      ).toMatchObject({ uid: "human-admin", kind: "human" });
      expect(firebase.collection).toHaveBeenCalledWith("adminData");
      expect(console.info).not.toHaveBeenCalled();
    }
  );
  it("retains human access to stats when machine auth is disabled", async () => {
    vi.stubEnv("ADMIN_STATS_READER_SAS", "");
    firebase.verify.mockResolvedValue({ uid: "human-admin" });
    expect(
      await scoped(
        request(jwt({ iss: "https://securetoken.google.com/based-hardware" }))
      )
    ).toMatchObject({ uid: "human-admin", kind: "human" });
  });
  it("still forbids a Firebase user without admin membership", async () => {
    firebase.verify.mockResolvedValue({ uid: "ordinary-user" });
    firebase.doc.mockResolvedValue({ exists: false });
    const response = await scoped(
      request(jwt({ iss: "https://securetoken.google.com/based-hardware" }))
    );
    expect((response as NextResponse).status).toBe(403);
  });
});

it("every stats route, including wall when merged, uses the shared auth boundary", () => {
  function visit(dir: string) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = resolve(dir, entry.name);
      if (entry.isDirectory()) visit(path);
      else if (entry.name === "route.ts") {
        expect(readFileSync(path, "utf8"), path).toMatch(
          /requireScope\(request, ['"](analytics|finance):read['"]\)|mobileOnboardingHandler\(/
        );
      }
    }
  }
  visit(resolve("app/api/omi/stats"));
});
