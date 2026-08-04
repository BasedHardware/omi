import { describe, expect, it } from "vitest";
import { createApp } from "../src/create-app.js";
import { resolveFeatures } from "@omi/platform";

describe("createApp feature gates", () => {
  it("health when enabled", async () => {
    const app = createApp({
      features: resolveFeatures({
        EDGE_MODULES: "health",
        EDGE_PROXY_ORIGIN: "false",
        EDGE_PROVIDER: "test",
      }),
    });
    const res = await app.request("http://local/edge/health");
    expect(res.status).toBe(200);
    const body = (await res.json()) as { ok: boolean; modules: string[] };
    expect(body.ok).toBe(true);
    expect(body.modules).toContain("health");
  });

  it("404 whoami when module off", async () => {
    const app = createApp({
      features: resolveFeatures({
        EDGE_MODULES: "health",
        EDGE_PROXY_ORIGIN: "false",
      }),
    });
    const res = await app.request("http://local/edge/whoami");
    expect(res.status).toBe(404);
  });

  it("memory path 401 without auth when gated on", async () => {
    const app = createApp({
      features: resolveFeatures({
        EDGE_MODULES: "memory",
        EDGE_PROXY_ORIGIN: "false",
        FIREBASE_PROJECT_ID: "p",
        ORIGIN_API_BASE: "https://example.invalid",
      }),
    });
    const res = await app.request("http://local/edge/memories");
    expect(res.status).toBe(401);
  });
});
