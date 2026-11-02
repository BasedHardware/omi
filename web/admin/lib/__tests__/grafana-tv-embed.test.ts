// @vitest-environment node
import {
  createHash,
  generateKeyPairSync,
  createPublicKey,
  verify,
} from "node:crypto";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("google-auth-library", () => ({
  GoogleAuth: class {
    async getAccessToken() {
      return "metadata-access";
    }
  },
}));
const resolveActiveTvToken = vi.fn();
vi.mock("@/lib/tv-links", () => ({ resolveActiveTvToken }));

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
  resolveActiveTvToken.mockReset();
  resolveActiveTvToken.mockResolvedValue({ id: "abc123", label: "Office TV" });
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (url: string, init: RequestInit) => {
    const headers = init.headers as Record<string, string>;
    if (url.startsWith("https://secretmanager.googleapis.com/")) {
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

async function callRoute(body: unknown) {
  const { POST } = await import("@/app/api/grafana/tv-embed/route");
  return POST(
    new NextRequest("https://admin.omi.me/api/grafana/tv-embed", {
      method: "POST",
      body: typeof body === "string" ? body : JSON.stringify(body),
    })
  );
}

it("mints a namespaced kiosk embed for a validated TV link", async () => {
  const response = await callRoute({ token: "a".repeat(43) });
  expect(response.status).toBe(200);
  const data = await response.json();
  expect(data.enabled).toBe(true);
  const url = new URL(data.url);
  expect(url.origin + url.pathname).toBe("https://monitor.omi.me/d/omi-tv-v2");
  expect(url.searchParams.get("orgId")).toBe("2");
  const [, payload] = url.searchParams.get("auth_token")!.split(".");
  const claims = JSON.parse(Buffer.from(payload, "base64url").toString());
  expect(claims.sub).toMatch(/^omi-business:[0-9a-f]{64}$/);
  const digest = claims.sub.slice("omi-business:".length);
  // tv: namespace keeps kiosk identities distinct from admin embeds.
  expect(digest).toBe(createHash("sha256").update("tv:abc123").digest("hex"));
  // The kiosk embed carries the same verifiable Business signature.
  const [jose, josePayload, joseSignature] = url.searchParams
    .get("auth_token")!
    .split(".");
  expect(
    verify(
      "RSA-SHA256",
      Buffer.from(`${jose}.${josePayload}`),
      createPublicKey(privateKey),
      Buffer.from(joseSignature, "base64url")
    )
  ).toBe(true);
  expect(response.headers.get("Cache-Control")).toBe("no-store");
});

it("rejects an invalid or revoked TV token before any minting", async () => {
  resolveActiveTvToken.mockResolvedValue(null);
  const response = await callRoute({ token: "b".repeat(43) });
  expect(response.status).toBe(403);
  expect(
    fetchMock.mock.calls.some(([url]) => url.includes("secretmanager"))
  ).toBe(false);
});

it("rejects malformed bodies without touching Firestore", async () => {
  const response = await callRoute("not-json");
  expect(response.status).toBe(400);
  expect(resolveActiveTvToken).not.toHaveBeenCalled();
});

it("flag-off disables the kiosk without probing or framing legacy Grafana", async () => {
  vi.stubEnv("GRAFANA_EMBED_ENABLED", "");
  const response = await callRoute({ token: "c".repeat(43) });
  expect(await response.json()).toEqual({ enabled: false });
  expect(fetchMock).not.toHaveBeenCalled();
});

it("returns 503 when enrollment fails after validation", async () => {
  fetchMock.mockImplementation(async (url: string) => {
    if (url.startsWith("https://secretmanager.googleapis.com/"))
      return new Response(null, { status: 500 });
    throw new Error("Unexpected test URL");
  });
  const response = await callRoute({ token: "e".repeat(43) });
  expect(response.status).toBe(503);
});
