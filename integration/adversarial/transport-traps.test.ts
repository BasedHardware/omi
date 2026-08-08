/**
 * The two transport-level traps a green unit suite structurally cannot catch.
 *
 * Both are authorization oracles: they leak the existence of data the caller
 * is not allowed to know exists. Neither is visible to an in-process test,
 * because both are properties of the response BYTES.
 *
 * Since the W4 rebuild these run against the REGISTERED composition rather than
 * a harness-authored one, so a leak found here is a leak in the shipped read
 * path — which is the entire reason the harness was rebound.
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

/** Visible memories in both fixture worlds. */
const VISIBLE = 7;
/**
 * Hidden-but-present memories in the "hidden" world. The seeder places each on
 * a local day it SHARES with a visible memory, so the served day-node exists in
 * both worlds and only its membership differs — the case where a leak would
 * actually show up in the synthesized text rather than only in a row count.
 */
const HIDDEN = 2;

let server: LiveServer;

beforeAll(async () => {
  server = await startLiveServer();
});

afterAll(async () => {
  await server?.stop();
});

describe("trap 1 — an authorization-hidden record is byte-identical to an absent one", () => {
  /**
   * red-proof: in `apps/service/composition/memory-read.ts`, derive the
   * declared frontier from the loader's coherent snapshot instead of the
   * authorized projection —
   *   `const declaredFrontier = encodeFrontier(`durable:${load.durable_snapshot.graph_generation}`)`
   * — i.e. from a value that counts rows this reader may not see. APPLIED: the
   * two worlds then emit different `completeness.frontiers.declaredFrontier`
   * on every page and the byte-identity assertion below fails on page 1 while
   * `itemIds` still matches, which is exactly the shape of the real leak.
   */
  test("full paginated wire transcripts are identical", async () => {
    await control(server.baseUrl, `/qa/reset?seed=${VISIBLE}&hidden=${HIDDEN}`);
    const hiddenTranscript = await paginateAll(server.baseUrl);

    await control(server.baseUrl, `/qa/absent?seed=${VISIBLE}`);
    const absentTranscript = await paginateAll(server.baseUrl);

    // The mechanism only a correct implementation produces: the caller sees the
    // visible memories and cannot tell which world it is in. Asserting the
    // COUNT (not merely "the hidden id is absent") is what makes this survive
    // opaque, reader-scoped item ids — there is no public name for a hidden
    // record to be absent from.
    expect(hiddenTranscript.pages.length).toBeGreaterThan(1);
    expect(hiddenTranscript.itemIds).toHaveLength(VISIBLE);
    expect(absentTranscript.itemIds).toHaveLength(VISIBLE);
    expect(hiddenTranscript.itemIds).toEqual(absentTranscript.itemIds);

    // Byte identity, page by page, including cursors, completeness and envelope.
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
   * red-proof: in `integration/server/compose.ts`'s `readPage`, replace the
   * `isInvalidMcpCursorError` re-throw with
   * `throw new Error("bad cursor " + input.cursor)`. The forged and
   * cross-owner cursors are then echoed back inside the error envelope and
   * this fails on the echo check as well as on `qa-cursor-key-1`.
   */
  test("invalid, forged and cross-owner cursors reveal nothing", async () => {
    await control(server.baseUrl, `/qa/reset?seed=${VISIBLE}`);

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
      // A structurally valid cursor minted for a different owner identity. The
      // reader-scoped codecs and the 15-field binding make it unredeemable
      // here; what this checks is that the REFUSAL says nothing.
      (await mintOtherOwnerCursor(server.baseUrl)) ?? "mcp1.qa-cursor-key-1.x.y",
    ];

    for (const cursor of candidates) {
      const response = await callTool(server.baseUrl, { cursor, limit: 2 });
      assertNoRawLeak(response.text, cursor);
    }
  });

  /**
   * red-proof: in `apps/service/composition/memory-read.ts`'s `readMemoryPage`,
   * delete the `isSyntacticallyRedeemableCursor` pre-check and let the core's
   * `TypeError` surface. The refusal becomes an internal-error envelope
   * carrying the core's message instead of the one invalid-cursor shape, and
   * the "Invalid cursor" assertion below fails.
   */
  test("internal store coordinates never reach the wire", async () => {
    await control(server.baseUrl, `/qa/reset?seed=${VISIBLE}`);
    const response = await callTool(server.baseUrl, { cursor: "vk1_deadbeef", limit: 2 });

    assertNoRawLeak(response.text, "vk1_deadbeef");
    // The error must still be a real, specific refusal.
    expect(response.text).toContain("Invalid cursor");
  });
});

/**
 * The forbidden substrings are the CURRENT fixture's internal spellings, not
 * the retired store's. `entity:qa:` and `claim:qa:` are the seeded corpus's
 * internal identifiers and `entity:qa:` also appears inside a served item's
 * synthesized text — so on an ERROR path, where no item may exist at all,
 * either one appearing is a leak.
 */
function assertNoRawLeak(responseText: string, offendingInput: string): void {
  const forbidden = [
    "claim:qa:", // internal claim revision ids
    "entity:qa:", // internal entity ids, and the served item text
    "evidence:qa:",
    "commit:qa:",
    "vk1_", // opaque visible-keyset handle — internal, never public
    "qa-owner-", // reader identity
    "qa-cursor-key-1", // signing key id
    "/Users/", // filesystem paths from stack traces
    "integration/server", // module paths
    "apps/service", // module paths
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
