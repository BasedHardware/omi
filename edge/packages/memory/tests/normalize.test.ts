import { describe, expect, it } from "vitest";
import { originMemoryStore } from "../src/types.js";

describe("originMemoryStore normalize", () => {
  it("lists from array body", async () => {
    const prev = globalThis.fetch;
    globalThis.fetch = async () =>
      new Response(
        JSON.stringify([{ id: "m1", content: "likes coffee", category: "interesting" }]),
        { status: 200 },
      );
    try {
      const store = originMemoryStore("https://api.example", "Bearer t");
      const rows = await store.list({ uid: "u1" });
      expect(rows).toHaveLength(1);
      expect(rows[0]!.content).toBe("likes coffee");
      expect(rows[0]!.uid).toBe("u1");
    } finally {
      globalThis.fetch = prev;
    }
  });
});
