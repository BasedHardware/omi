/**
 * Concurrent-insert pagination, against a live server.
 *
 * Offset pagination permanently SKIPS rows when a row is inserted ahead of the
 * read cursor between page fetches: page 2 starts at offset N, but everything
 * shifted right by one, so the row that was at N-1 is never returned. This has
 * already caused real data loss in this codebase, so the proof must actually
 * insert during pagination rather than reason about it.
 *
 * Note the assertion style: this deliberately does NOT assert a row count.
 * A count assertion passes for the wrong reason the moment inserts change the
 * total. It asserts the exact SET of originally-present ids was returned, each
 * exactly once — content only a correct keyset implementation can produce.
 */

import { afterAll, beforeAll, describe, expect, test } from "bun:test";

import { callTool, control, pageTextOf, startLiveServer, type LiveServer } from "./live-server";

let server: LiveServer;

beforeAll(async () => {
  server = await startLiveServer();
});

afterAll(async () => {
  await server?.stop();
});

describe("concurrent insert during pagination", () => {
  /**
   * red-proof: in qa-store.ts `read()`, replace the keyset resolution with an
   * offset — store the page index in the vk1 index and use
   * `startIndex = anchor.offset + 1` instead of `findIndex(compareTuple > 0)`.
   *
   * APPLIED, and the observed symptom corrected this comment: inserting rows
   * *behind* the cursor shifts later rows RIGHT, so `anchor.offset + 1` lands
   * back on a row already returned and `seed-0002` comes back TWICE
   * (occurrences: 2). Inserting *ahead* of the cursor produces the mirror-image
   * skip. Both are the same offset defect and both are data corruption; the
   * exactly-once assertion below catches either direction, which a
   * "no row is missing" assertion would not.
   */
  test("no originally-present row is skipped when rows are inserted mid-pagination", async () => {
    await control(server.baseUrl, "/qa/reset?seed=6");

    const originalIds = [
      "retrieval-node-v1:seed-0000",
      "retrieval-node-v1:seed-0001",
      "retrieval-node-v1:seed-0002",
      "retrieval-node-v1:seed-0003",
      "retrieval-node-v1:seed-0004",
      "retrieval-node-v1:seed-0005",
    ];

    const seen: string[] = [];
    let cursor: string | null = null;
    let pageNumber = 0;

    for (let guard = 0; guard < 20; guard += 1) {
      const response: { status: number; text: string } = await callTool(server.baseUrl, {
        cursor,
        limit: 2,
      });
      const pageText = pageTextOf(response.text);
      expect(pageText).not.toBeNull();

      const page = JSON.parse(pageText as string) as {
        items: readonly { id: string }[];
        window: { nextCursor: string | null };
      };
      for (const item of page.items) {
        seen.push(item.id);
      }
      pageNumber += 1;

      // Insert BELOW the current read position — the exact move that breaks
      // offset pagination. sortKey s00000005 sorts between seed-0000 (s0) and
      // seed-0001 (s10), i.e. behind a cursor that has already passed it.
      if (pageNumber === 1) {
        await control(
          server.baseUrl,
          "/qa/insert?id=retrieval-node-v1:injected-a&sortKey=s00000005",
        );
        await control(
          server.baseUrl,
          "/qa/insert?id=retrieval-node-v1:injected-b&sortKey=s00000006",
        );
      }

      cursor = page.window.nextCursor;
      if (cursor === null) {
        break;
      }
    }

    // Every originally-present row appears exactly once.
    for (const id of originalIds) {
      const occurrences = seen.filter((candidate) => candidate === id).length;
      expect({ id, occurrences }).toEqual({ id, occurrences: 1 });
    }

    // And the rows inserted behind the cursor were correctly NOT resurrected
    // into a page the reader had already passed.
    expect(seen).not.toContain("retrieval-node-v1:injected-a");
    expect(seen).not.toContain("retrieval-node-v1:injected-b");
  });

  /**
   * red-proof: in compose.ts `buildPage`, emit the terminal window
   * unconditionally (drop the `result.hasMore` branch). The final page then
   * claims `complete: true` while a continuation was still owed, and this
   * fails on the first page.
   *
   * Snapshot honesty: a wrong `complete: true` is user data loss via
   * reconcile, so a non-terminal page must never claim completeness.
   */
  test("a page with a continuation never claims window completeness", async () => {
    await control(server.baseUrl, "/qa/reset?seed=6");

    const response = await callTool(server.baseUrl, { limit: 2 });
    const page = JSON.parse(pageTextOf(response.text) as string) as {
      window: { status: string; complete: boolean; hasMore: boolean; nextCursor: string | null };
    };

    expect(page.window.hasMore).toBe(true);
    expect(page.window.complete).toBe(false);
    expect(page.window.status).toBe("more");
    expect(typeof page.window.nextCursor).toBe("string");
  });
});
