import { describe, expect, it } from "vitest";
import { originMemoryStore } from "../src/types.js";

describe("originMemoryStore normalize", () => {
  it("forwards the GET /v3/memories query and preserves MemoryDB fields", async () => {
    const request: { url: string; authorization: string | null } = { url: "", authorization: null };
    const prev = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      request.url = String(input);
      request.authorization = new Headers(init?.headers).get("Authorization");
      return new Response(
        JSON.stringify([
          {
            id: "m1",
            uid: "u1",
            content: "likes coffee",
            category: "interesting",
            created_at: "2026-08-04T12:00:00Z",
            updated_at: "2026-08-04T12:01:00Z",
            layer: "long_term",
            memory_tier: "long_term",
            headline: "Coffee preference",
            tags: ["coffee"],
            arguments: { object: "coffee" },
            qualifiers: { scope: "personal" },
            evidence: [
              {
                evidence_id: "e1",
                independence_group: "conversation:c1",
                created_at: "2026-08-04T12:00:00Z",
                source_id: "c1",
                source_type: "conversation",
                source_signal: "transcription",
              },
            ],
          },
        ]),
        { status: 200 },
      );
    }) as unknown as typeof fetch;
    try {
      const store = originMemoryStore("https://api.example", "Bearer t");
      const rows = await store.list({
        uid: "u1",
        limit: 7,
        offset: 2,
        cursor: "next-page",
        deviceScope: "client",
        clientDeviceId: "device-1",
      });
      expect(request.url).toBe(
        "https://api.example/v3/memories?limit=7&offset=2&cursor=next-page&device_scope=client&client_device_id=device-1",
      );
      expect(request.authorization).toBe("Bearer t");
      expect(rows).toHaveLength(1);
      expect(rows[0]).toMatchObject({
        id: "m1",
        uid: "u1",
        content: "likes coffee",
        created_at: "2026-08-04T12:00:00Z",
        updated_at: "2026-08-04T12:01:00Z",
        layer: "long_term",
        memory_tier: "long_term",
        headline: "Coffee preference",
        tags: ["coffee"],
        arguments: { object: "coffee" },
        qualifiers: { scope: "personal" },
      });
      expect(rows[0]!.evidence[0]).toMatchObject({ evidence_id: "e1", independence_group: "conversation:c1" });
    } finally {
      globalThis.fetch = prev;
    }
  });

  it("lists from an OpenAPI-compatible array body", async () => {
    const prev = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify([
          {
            id: "m1",
            content: "likes coffee",
            uid: "u1",
            created_at: "2026-08-04T12:00:00Z",
            updated_at: "2026-08-04T12:00:00Z",
          },
        ]),
        { status: 200 },
      )) as unknown as typeof fetch;
    try {
      const store = originMemoryStore("https://api.example", "Bearer t");
      const rows = await store.list({ uid: "u1" });
      expect(rows).toHaveLength(1);
      expect(rows[0]!.content).toBe("likes coffee");
      expect(rows[0]!.uid).toBe("u1");
      expect(rows[0]!.layer).toBeNull();
    } finally {
      globalThis.fetch = prev;
    }
  });

});
