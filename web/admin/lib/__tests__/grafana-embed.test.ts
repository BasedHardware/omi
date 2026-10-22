// @vitest-environment node
import { generateKeyPairSync, createPublicKey, verify } from "node:crypto";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { NextRequest, NextResponse } from "next/server";
import { testIdentity } from "./support/test-identity";
vi.mock("google-auth-library", () => ({
  GoogleAuth: class {
    async getAccessToken() {
      return "metadata-access";
    }
  },
}));
vi.mock("@/lib/auth", async () => {
  const { testIdentity } = await import("./support/test-identity");
  return { requireScope: vi.fn().mockResolvedValue(testIdentity()) };
});
const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
const signing = {
  kid: "test-key",
  privateKeyPem: privateKey.export({ format: "pem", type: "pkcs8" }).toString(),
};
const membership = { token: "business-service-token", orgId: 2, teamId: 8 };
const fetchMock = vi.fn();
beforeEach(() => {
  vi.resetModules();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("GRAFANA_EMBED_ENABLED", "true");
  vi.stubEnv(
    "GRAFANA_EMBED_SIGNING_SECRET",
    "projects/test/secrets/signing/versions/1"
  );
  vi.stubEnv(
    "GRAFANA_BUSINESS_TOKEN_SECRET",
    "projects/test/secrets/members/versions/1"
  );
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (url: string, init: RequestInit) => {
    const headers = init.headers as Record<string, string>;
    if (url.startsWith("https://secretmanager.googleapis.com/")) {
      expect(headers.Authorization).toBe("Bearer metadata-access");
      const payload = url.includes("/signing/") ? signing : membership;
      return Response.json({
        payload: {
          data: Buffer.from(JSON.stringify(payload)).toString("base64"),
        },
      });
    }
    if (url.endsWith("/api/org"))
      return Response.json({ id: 2, name: "Omi Business" });
    if (url.endsWith("/api/user")) {
      const claims = JSON.parse(
        Buffer.from(
          headers["X-Omi-Grafana-JWT"].split(".")[1],
          "base64url"
        ).toString()
      );
      return Response.json({
        id: 24,
        orgId: 2,
        login: claims.sub,
        isGrafanaAdmin: false,
      });
    }
    if (url.endsWith("/api/teams/8"))
      return Response.json({ name: "business-viewers" });
    if (url.endsWith("/members")) {
      expect(headers.Authorization).toBe("Bearer business-service-token");
      return Response.json(init.method === "POST" ? { message: "added" } : []);
    }
    throw new Error("Unexpected test URL");
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
it("signs bounded, namespaced Business-only JWTs and exposes only the public key", async () => {
  const { mintEmbed, embedJwks } = await import("../grafana-embed");
  const result = await mintEmbed("firebase-admin-id");
  const url = new URL(result.url);
  expect(url.origin + url.pathname).toBe("https://monitor.omi.me/d/omi-tv-v2");
  expect(url.searchParams.get("refresh")).toBe("15m");
  const [header, payload, signature] = url.searchParams
    .get("auth_token")!
    .split(".");
  const claims = JSON.parse(Buffer.from(payload, "base64url").toString());
  expect(claims).toMatchObject({
    iss: "https://admin.omi.me",
    aud: "https://monitor.omi.me",
    purpose: "omi-business-embed",
    orgs: ["business"],
  });
  expect(claims.exp - claims.iat).toBeLessThanOrEqual(300);
  expect(claims.sub).toMatch(/^omi-business:[0-9a-f]{64}$/);
  expect(claims).not.toHaveProperty("role");
  expect(
    verify(
      "RSA-SHA256",
      Buffer.from(`${header}.${payload}`),
      createPublicKey(privateKey),
      Buffer.from(signature, "base64url")
    )
  ).toBe(true);
  const jwks = await embedJwks();
  expect(jwks.keys[0]).toMatchObject({
    kid: "test-key",
    kty: "RSA",
    use: "sig",
  });
  expect(jwks.keys[0]).not.toHaveProperty("d");
  expect(
    fetchMock.mock.calls.filter(([url]) => url.includes("/secrets/"))
  ).toHaveLength(2);
  expect(
    fetchMock.mock.calls.some(
      ([url, init]) => url.endsWith("/members") && init.method === "POST"
    )
  ).toBe(true);
});
it("fails before enrollment when a service account targets the monitoring org", async () => {
  const original = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation((url, init) =>
    url.endsWith("/api/org")
      ? Response.json({ id: 1, name: "Main Org." })
      : original(url, init)
  );
  const { mintEmbed } = await import("../grafana-embed");
  await expect(mintEmbed("admin")).rejects.toThrow("unexpected organization");
  expect(fetchMock.mock.calls.some(([, init]) => init.method === "POST")).toBe(
    false
  );
});
it("checks admin membership before any token or secret access", async () => {
  const { requireScope } = await import("@/lib/auth");
  vi.mocked(requireScope).mockResolvedValue(
    NextResponse.json({ error: "Forbidden" }, { status: 403 })
  );
  const { GET } = await import("@/app/api/grafana/embed/route");
  const response = await GET(
    new NextRequest("https://admin.omi.me/api/grafana/embed")
  );
  expect(response.status).toBe(403);
  expect(fetchMock).not.toHaveBeenCalled();
});
it("leaves the existing board available while prerequisites are disabled", async () => {
  vi.stubEnv("GRAFANA_EMBED_ENABLED", "");
  const { requireScope } = await import("@/lib/auth");
  vi.mocked(requireScope).mockResolvedValue(testIdentity(undefined, "admin"));
  const { GET } = await import("@/app/api/grafana/embed/route");
  const response = await GET(
    new NextRequest("https://admin.omi.me/api/grafana/embed")
  );
  expect(await response.json()).toEqual({ enabled: false });
  expect(response.headers.get("Cache-Control")).toBe("no-store");
  expect(fetchMock).not.toHaveBeenCalled();
});

it("mints only the Business embed without probing the retired Grafana origins", async () => {
  const { mintEmbed } = await import("../grafana-embed");
  const result = await mintEmbed("admin");
  const url = new URL(result.url);
  expect(url.origin).toBe("https://monitor.omi.me");
  expect(url.searchParams.get("orgId")).toBe("2");
  expect(
    fetchMock.mock.calls.every(
      ([requestUrl]) =>
        requestUrl.startsWith("https://secretmanager.googleapis.com/") ||
        requestUrl.startsWith("https://monitor.omi.me/")
    )
  ).toBe(true);
});

it("publishes the public verification key while cutover is disabled for staged Helm startup", async () => {
  vi.stubEnv("GRAFANA_EMBED_ENABLED", "");
  const { GET } = await import("@/app/api/grafana/jwks/route");
  const response = await GET();
  expect(response.status).toBe(200);
  const data = await response.json();
  expect(data.keys[0]).toMatchObject({ kid: "test-key", kty: "RSA" });
  expect(data.keys[0]).not.toHaveProperty("d");
});
