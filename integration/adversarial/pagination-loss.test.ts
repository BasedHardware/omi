/**
 * Pagination under a corpus that changes mid-walk, against a live server.
 *
 * THE DEFECT THIS EXISTS FOR, unchanged: offset pagination silently loses rows
 * when the corpus changes between page fetches — page 2 starts at offset N, but
 * everything shifted, so a row is either skipped or returned twice. That has
 * already caused real data loss in this codebase, so the proof must actually
 * change the corpus during pagination rather than reason about it.
 *
 * WHAT CHANGED WITH THE W4 REBUILD, AND WHY THE ASSERTION MOVED
 * ------------------------------------------------------------
 * This used to run against the harness's own keyset store, whose answer to a
 * mid-walk insert was "resolve the continuation by sort tuple and carry on".
 * The REGISTERED composition — the shipped one — answers differently and more
 * strictly: the cursor binds a generation receipt derived from the authorized
 * projection, so a corpus that moved invalidates the continuation and the read
 * FAILS CLOSED with the route's fixed `bad_request` body.
 *
 * Fail-closed dominates resume-correctly on the axis that matters here. Both
 * refuse to lose a row; only fail-closed also refuses to serve a page stitched
 * across two different snapshots. So the proof asserts the stronger property
 * the shipped code actually has, rather than pinning the retired store's
 * weaker one — and it still asserts exactly-once coverage, which is what
 * catches an offset regression.
 *
 * Note the assertion style: this deliberately does NOT assert a row count as
 * the primary check. A count assertion passes for the wrong reason the moment
 * the corpus changes. It asserts the exact SET of ids was returned, each
 * exactly once — content only a correct keyset implementation can produce.
 */

import { afterAll, beforeAll, describe, expect, test } from "bun:test";

import { callTool, control, pageTextOf, recall, startLiveServer, type LiveServer } from "./live-server";

const SEED = 6;

let server: LiveServer;

beforeAll(async () => {
  server = await startLiveServer();
});

afterAll(async () => {
  await server?.stop();
});

interface Walk {
  readonly ids: readonly string[];
  readonly pages: number;
  readonly terminated: boolean;
}

async function walk(baseUrl: string, limit: number): Promise<Walk> {
  const ids: string[] = [];
  let cursor: string | null = null;
  let pages = 0;
  for (let guard = 0; guard < 30; guard += 1) {
    const response: { status: number; text: string } = await callTool(baseUrl, { cursor, limit });
    const pageText = pageTextOf(response.text);
    if (pageText === null) throw new Error(`no page in response: ${response.text}`);
    const page = JSON.parse(pageText) as {
      items: readonly { id: string }[];
      window: { nextCursor: string | null };
    };
    for (const item of page.items) ids.push(item.id);
    pages += 1;
    cursor = page.window.nextCursor;
    if (cursor === null) return { ids, pages, terminated: true };
  }
  return { ids, pages, terminated: false };
}

describe("paginating a stable corpus", () => {
  /**
   * red-proof: in `apps/service/composition/memory-read.ts`'s `prepareMemoryRead`,
   * drop the `.sort((left, right) => compareStrings(left.node_id, right.node_id))`
   * from `servedRenders`. APPLIED: the walk's page boundaries stop lining up
   * with the keyset order, ids repeat across pages, and the exactly-once
   * assertion fails naming the duplicated id.
   */
  test("a full walk returns every memory exactly once and terminates", async () => {
    await control(server.baseUrl, `/qa/reset?seed=${SEED}`);

    const walked = await walk(server.baseUrl, 2);

    expect(walked.terminated).toBe(true);
    expect(walked.pages).toBeGreaterThan(1);
    expect(walked.ids).toHaveLength(SEED);
    for (const id of walked.ids) {
      const occurrences = walked.ids.filter((candidate) => candidate === id).length;
      expect({ id, occurrences }).toEqual({ id, occurrences: 1 });
    }
  });

  /**
   * red-proof: in `apps/service/composition/memory-read.ts`, force the terminal
   * window by making `buildCoverage` claim completeness unconditionally — or
   * more directly, in `core/retrieve/application-read.ts` emit
   * `hasMore: false` whenever a cursor was issued. The first page then claims
   * `complete: true` while a continuation is still owed and this fails.
   *
   * Snapshot honesty: a wrong `complete: true` is user data loss via
   * reconcile, so a non-terminal page must never claim completeness.
   */
  test("a page with a continuation never claims window completeness", async () => {
    await control(server.baseUrl, `/qa/reset?seed=${SEED}`);

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

describe("the corpus changes mid-pagination", () => {
  /**
   * The arbiter is the route's OWN refusal for a syntactically invalid cursor,
   * obtained from this same live process — not a status code typed here. "Not
   * 200" is satisfied by a crash or a 500; what must happen is the ordinary
   * invalid-cursor refusal, byte for byte, so a stale continuation is
   * indistinguishable from any other unredeemable one.
   *
   * red-proof: in `apps/service/composition/memory-read.ts`'s
   * `buildGenerations`, drop `authorized_graph_generation` from
   * `declared_generation_digest` (leave only the frontier and granularity).
   * APPLIED: the stale cursor then verifies against the grown corpus, page two
   * is served 200 across two different snapshots, and this fails on the status
   * and the body.
   */
  test("a continuation issued before the change is refused, byte-identically to any invalid cursor", async () => {
    await control(server.baseUrl, `/qa/reset?seed=${SEED}`);

    const first = await recall(server.baseUrl, { limit: 2 });
    expect(first.status).toBe(200);
    const staleCursor = (JSON.parse(first.text) as {
      window: { nextCursor: string | null };
    }).window.nextCursor;
    expect(typeof staleCursor).toBe("string");

    await control(server.baseUrl, "/qa/grow?by=2");

    const stale = await recall(server.baseUrl, { limit: 2, cursor: staleCursor });
    const garbage = await recall(server.baseUrl, { limit: 2, cursor: "not-a-cursor" });

    expect(stale.status).toBe(garbage.status);
    expect(stale.text).toBe(garbage.text);
    // It really is a refusal, not an accidental empty success on both sides.
    expect(stale.status).toBe(400);
  });

  /**
   * The pair. Without it, a server that refused EVERY continuation would
   * satisfy the assertion above — and a walk that cannot resume at all is not
   * a working pagination.
   *
   * red-proof: make `/qa/grow` a no-op in `integration/server/serve.ts`. The
   * grown walk then returns SEED ids instead of SEED + 2 and this fails on the
   * length, while the refusal test above still passes.
   */
  test("a fresh walk after the change again covers the whole corpus exactly once", async () => {
    await control(server.baseUrl, `/qa/reset?seed=${SEED}`);
    await control(server.baseUrl, "/qa/grow?by=2");

    const walked = await walk(server.baseUrl, 2);

    expect(walked.terminated).toBe(true);
    expect(walked.ids).toHaveLength(SEED + 2);
    for (const id of walked.ids) {
      const occurrences = walked.ids.filter((candidate) => candidate === id).length;
      expect({ id, occurrences }).toEqual({ id, occurrences: 1 });
    }
  });
});
