/**
 * The two transport-level traps a green unit suite structurally cannot catch.
 *
 * Both are authorization oracles: they leak the existence of data the caller
 * is not allowed to know exists. Neither is visible to an in-process test,
 * because both are properties of the response BYTES.
 */

import { afterAll, beforeAll, describe, expect, test } from "bun:test";

import {
  callTool,
  control,
  pageTextOf,
  QA_KEY,
  QA_KEY_NO_SCOPE,
  startLiveServer,
  type LiveServer,
} from "./live-server";

const HIDDEN_ID = "retrieval-node-v1:seed-0003";

let server: LiveServer;

beforeAll(async () => {
  server = await startLiveServer();
});

afterAll(async () => {
  await server?.stop();
});

describe("trap 1 — an authorization-hidden record is byte-identical to an absent one", () => {
  /**
   * red-proof: in qa-store.ts `read()`, move the authorization filter to AFTER
   * the slice — i.e. paginate over `this.#rows` and filter the resulting page.
   * The hidden variant then returns 2 items where the absent variant returns 3,
   * and the continuation cursors diverge. This test fails on the first page.
   *
   * A second, subtler mutation this also catches: computing `hasMore` from
   * `this.#rows.length` instead of `visible.length` leaves the item arrays
   * equal but flips `status`/`nextCursor` on the final page.
   */
  test("full paginated wire transcripts are identical", async () => {
    await control(server.baseUrl, `/qa/reset?seed=7&hidden=${encodeURIComponent(HIDDEN_ID)}`);
    const hiddenTranscript = await paginateAll(server.baseUrl);

    await control(server.baseUrl, `/qa/absent?seed=7&omit=${encodeURIComponent(HIDDEN_ID)}`);
    const absentTranscript = await paginateAll(server.baseUrl);

    // The mechanism only a correct implementation produces: the caller sees
    // six propositions, and cannot tell which world it is in.
    expect(hiddenTranscript.pages.length).toBeGreaterThan(1);
    expect(hiddenTranscript.itemIds).not.toContain(HIDDEN_ID);
    expect(absentTranscript.itemIds).not.toContain(HIDDEN_ID);
    expect(hiddenTranscript.itemIds).toEqual(absentTranscript.itemIds);

    // Byte identity, page by page, including cursors and envelope.
    expect(hiddenTranscript.pages).toEqual(absentTranscript.pages);
  });

  /**
   * red-proof: in protocol.ts `callTool`, return a distinct error message for
   * `call.name !== TOOL.name` instead of sharing "Tool unavailable" with the
   * denied gate. The two response bodies then differ and this fails.
   */
  test("a hidden tool and an unknown tool are byte-identical", async () => {
    const hiddenTool = await callTool(server.baseUrl, { key: QA_KEY_NO_SCOPE });
    const unknownTool = await callTool(server.baseUrl, { key: QA_KEY, name: "no_such_tool" });

    expect(hiddenTool.status).toBe(unknownTool.status);
    expect(hiddenTool.text).toBe(unknownTool.text);
    // And it must actually be a refusal, not an accidental success on both sides.
    expect(hiddenTool.text).toContain("Tool unavailable");
  });
});

describe("trap 2 — no raw data leaks through error paths", () => {
  /**
   * Error paths are where raw data leaks, because error construction is the
   * one place that tends to interpolate the offending value.
   *
   * red-proof: in compose.ts `readPage`, change the thrown error to
   * `new Error("bad cursor " + input.cursor)` and let protocol.ts surface it,
   * or have validatePage return the page object in its message. Either makes
   * a forbidden substring appear and this test fails.
   */
  test("invalid, forged and cross-owner cursors reveal nothing", async () => {
    await control(server.baseUrl, "/qa/reset?seed=7");

    const first = await callTool(server.baseUrl, { limit: 2 });
    const firstPage = pageTextOf(first.text);
    expect(firstPage).not.toBeNull();
    const realCursor = JSON.parse(firstPage as string).window.nextCursor as string;
    expect(typeof realCursor).toBe("string");

    const forged = `${realCursor.slice(0, -4)}AAAA`;
    const candidates = [
      "not-a-cursor",
      "",
      forged,
      // A structurally valid cursor minted for a different owner identity.
      (await mintOtherOwnerCursor(server.baseUrl)) ?? "mcp1.qa-cursor-key-1.x.y",
    ];

    for (const cursor of candidates) {
      const response = await callTool(server.baseUrl, { cursor, limit: 2 });
      assertNoRawLeak(response.text, cursor);
    }
  });

  /**
   * red-proof: make the QA store's UnknownVisibleKeyError message include the
   * key, and stop translating it to InvalidMcpCursorError in compose.ts, so
   * the internal `vk1_...` handle reaches the client. This fails.
   */
  test("internal store coordinates never reach the wire", async () => {
    await control(server.baseUrl, "/qa/reset?seed=7");
    const response = await callTool(server.baseUrl, { cursor: "vk1_deadbeef", limit: 2 });

    expect(response.text).not.toContain("vk1_");
    expect(response.text).not.toContain("sortKey");
    expect(response.text).not.toContain("visibleTo");
    expect(response.text).not.toContain("qa-owner-");
    // The error must still be a real, specific refusal.
    expect(response.text).toContain("Invalid cursor");
  });
});

function assertNoRawLeak(responseText: string, offendingInput: string): void {
  const forbidden = [
    "Synthesized proposition", // item text
    "retrieval-node-v1:seed-", // internal-ish row ids
    "vk1_", // opaque visible-keyset handle
    "sortKey",
    "visibleTo",
    "qa-owner-",
    "qa-cursor-key-1", // signing key id
    "/Users/", // filesystem paths from stack traces
    "integration/server", // module paths
  ];
  for (const needle of forbidden) {
    expect({ needle, responseText }).toMatchObject({
      responseText: expect.not.stringContaining(needle),
    });
  }
  // The offending input must not be echoed back either.
  if (offendingInput.length > 8) {
    expect(responseText).not.toContain(offendingInput);
  }
}

async function mintOtherOwnerCursor(baseUrl: string): Promise<string | null> {
  const response = await callTool(baseUrl, { key: "omi-integration-qa-key-v2", limit: 2 });
  const page = pageTextOf(response.text);
  if (page === null) {
    return null;
  }
  return (JSON.parse(page) as { window: { nextCursor: string | null } }).window.nextCursor;
}

async function paginateAll(baseUrl: string): Promise<{ pages: string[]; itemIds: string[] }> {
  const pages: string[] = [];
  const itemIds: string[] = [];
  let cursor: string | null = null;

  for (let guard = 0; guard < 20; guard += 1) {
    const response: { status: number; text: string } = await callTool(baseUrl, { cursor, limit: 3 });
    const pageText = pageTextOf(response.text);
    if (pageText === null) {
      throw new Error(`no page in response: ${response.text}`);
    }
    pages.push(pageText);
    const page = JSON.parse(pageText) as {
      items: readonly { id: string }[];
      window: { nextCursor: string | null };
    };
    for (const item of page.items) {
      itemIds.push(item.id);
    }
    cursor = page.window.nextCursor;
    if (cursor === null) {
      return { pages, itemIds };
    }
  }
  throw new Error("pagination did not terminate");
}
