import { describe, expect, it } from "vitest";
import { resolveFeatures } from "@omi/platform";
import { memoryRoutes } from "../src/routes.js";

describe("memory routes", () => {
  it("returns the bare MemoryDB array contract", async () => {
    const prev = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify([
          {
            id: "m1",
            uid: "u1",
            content: "likes coffee",
            created_at: "2026-08-04T12:00:00Z",
            updated_at: "2026-08-04T12:00:00Z",
          },
        ]),
        { status: 200 },
      )) as unknown as typeof fetch;
    try {
      const app = memoryRoutes({
        features: resolveFeatures({
          ORIGIN_API_BASE: "https://api.example",
          FIREBASE_PROJECT_ID: "based-hardware",
          ADMIN_KEY: "admin-key-123456789",
        }),
      });
      const response = await app.request("https://edge.example/?limit=3", {
        headers: { Authorization: "Bearer admin-key-123456789u1" },
      });
      expect(response.status).toBe(200);
      const body = (await response.json()) as unknown;
      expect(Array.isArray(body)).toBe(true);
      expect(body).toEqual([
        expect.objectContaining({ id: "m1", uid: "u1", content: "likes coffee", layer: null }),
      ]);
    } finally {
      globalThis.fetch = prev;
    }
  });
});
