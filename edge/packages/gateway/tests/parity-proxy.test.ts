import { describe, expect, it } from "vitest";
import { createApp } from "../src/create-app.js";
import { resolveFeatures } from "@omi/platform";

describe("origin parity mounts", () => {
  it("GET /v3/memories proxies when memory module on", async () => {
    const calls: string[] = [];
    const prev = globalThis.fetch;
    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      return new Response(JSON.stringify([{ id: "1", content: "x" }]), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    };
    try {
      const app = createApp({
        features: resolveFeatures({
          EDGE_MODULES: "memory",
          EDGE_PROXY_ORIGIN: "false",
          ORIGIN_API_BASE: "https://origin.test",
          FIREBASE_PROJECT_ID: "p",
        }),
      });
      const res = await app.request("http://local/v3/memories?limit=10", {
        headers: { Authorization: "Bearer unused" },
      });
      expect(res.status).toBe(200);
      expect(calls.some((u) => u.includes("https://origin.test/v3/memories"))).toBe(true);
      expect(res.headers.get("x-omi-edge")).toBe("memory-parity");
    } finally {
      globalThis.fetch = prev;
    }
  });

  it("does not mount /v3/memories when memory off", async () => {
    const app = createApp({
      features: resolveFeatures({
        EDGE_MODULES: "health",
        EDGE_PROXY_ORIGIN: "false",
        ORIGIN_API_BASE: "https://origin.test",
      }),
    });
    const res = await app.request("http://local/v3/memories");
    expect(res.status).toBe(404);
  });
});
