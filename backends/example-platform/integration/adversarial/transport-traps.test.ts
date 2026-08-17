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
   * red-proof: in `apps/service/composition/memory-read.ts`, pass the loader's
   * `coherent_snapshot_digest` to `buildCoverage` in place of
   * `authorizedGraphGeneration` — i.e. derive the declared frontier from a
   * value that counts rows this reader may not see. APPLIED and observed red
   * on THIS test only: the two worlds emit different
   * `completeness.frontiers.declaredFrontier`, so the transcripts diverge
   * while `itemIds` still matches exactly. That is the real leak's shape — the
   * items are correctly filtered and the envelope republishes the hidden rows
   * anyway.
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
   * red-proof: applied to the paired test below, which is where it lands.
   *
   * WHAT THE APPLIED MUTATION ACTUALLY SHOWED, stated because it is the more
   * useful fact: replacing the `isInvalidMcpCursorError` re-throw in
   * `integration/server/compose.ts` with
   * `throw new Error("bad cursor " + input.cursor)` does NOT leak the cursor.
   * The MCP transport collapses every unmapped throw to a fixed
   * `{"code":-32603,"message":"Internal error"}` envelope, so a message-level
   * leak is unreachable from here. These needle assertions are therefore a
   * BACKSTOP against that envelope discipline being weakened, not the primary
   * fence — and the primary fence is the transport's, not this file's. Do not
   * read a green run here as evidence that composition code may interpolate
   * caller input into errors; it may not.
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
   * red-proof: in `integration/server/compose.ts`'s `readPage`, replace the
   * `isInvalidMcpCursorError` re-throw with a plain `Error`. APPLIED and
   * observed red here: the response becomes
   * `{"code":-32603,"message":"Internal error"}` and the "Invalid cursor"
   * assertion fails. The refusal must stay SPECIFIC — a cursor problem
   * reported as an internal error tells a client to retry a request that can
   * never succeed, and hides a real fault behind a client-input one.
   *
   * Did NOT go red, recorded as evidence: deleting the
   * `isSyntacticallyRedeemableCursor` pre-check from `readMemoryPage`. The
   * core's own guard still raises the invalid-cursor currency for `vk1_...`,
   * so this particular string does not distinguish the two layers. The
   * pre-check's real subject is the 4096/4097 length boundary, which
   * `apps/service/routes/route-hardening.test.ts` pins directly.
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
