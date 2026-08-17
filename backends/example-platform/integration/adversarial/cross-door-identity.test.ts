/**
 * THE TWO DOORS OF THIS PROCESS SERVE THE SAME BYTES.
 *
 * Wave 1 measured the failure this pins: over ONE snapshot and ONE principal,
 * the REST and MCP doors returned the same memory — byte-identical text,
 * identical render hash — under DIFFERENT public item ids
 * (`mem1_eca59618fff27e10…` vs `mem1_dd73274cc9b1a9ac…`), because they keyed
 * the opaque-ref codecs differently. Every node-level cross-door assertion
 * passed the whole time; the divergence sat one layer below where anyone
 * looked. `apps/service/composition/cross-door-identity.test.ts` pins that
 * in-process.
 *
 * This is the LIVE-WIRE half, and it is not redundant with the in-process one:
 * the in-process test proves one composition can serve both doors, while this
 * proves the live adversarial server process did bind it that way. The
 * whole W4 ruling exists because a harness can be wired differently from the
 * product binding it mirrors, and no in-process assertion can
 * see that.
 *
 * It is also the standing check on the ruling itself: if anyone reintroduces a
 * parallel read path on either door, these bytes stop matching.
 */

import { afterAll, beforeAll, describe, expect, test } from "bun:test";

import { callTool, control, pageTextOf, recall, startLiveServer, type LiveServer } from "./live-server";

const SEED = 7;

let server: LiveServer;

beforeAll(async () => {
  server = await startLiveServer();
  await control(server.baseUrl, `/qa/reset?seed=${SEED}`);
});

afterAll(async () => {
  await server?.stop();
});

describe("the REST and MCP doors of one process", () => {
  /**
   * red-proof: in `integration/server/compose.ts`, give the MCP door its own
   * APPLICATION identity — make `prepareRead` read `app_id` from a mutable
   * module binding and have `readPage` set it to `"mcp-door-app"` before it
   * prepares. APPLIED, and observed red HERE and only here: both doors still
   * serve seven memories with identical text and identical provenance
   * digests, and this fails on the first byte comparison because
   * `principal_digest` — the scope of the reader-scoped codecs — covers
   * owner, app AND key. That is the wave-1 defect, reproduced on demand.
   *
   * Note what does NOT reproduce it, because it is worth knowing: changing
   * `key_id` inside `authenticate`'s `rateLimitKey` leaves every assertion
   * here green. That field is the MCP rate-limit tuple and never reaches the
   * composition; the authorization request is built from the constants in
   * `prepareRead`. Applied and observed GREEN before the mutation above was
   * found — a red-proof that does not go red is not a red-proof.
   */
  test("emit byte-identical pages for the same request", async () => {
    const rest = await recall(server.baseUrl, { limit: 3 });
    expect(rest.status).toBe(200);

    const mcp = await callTool(server.baseUrl, { limit: 3 });
    const mcpPage = pageTextOf(mcp.text);
    expect(mcpPage).not.toBeNull();

    // Byte identity of the canonical page text, not a parsed-object compare: a
    // JavaScript object compare would pass while the serializer, key order or
    // encoding differed, and the client's `canonical-json-text` boundary reads
    // the bytes.
    expect(mcpPage).toBe(rest.text);
  });

  /**
   * A cursor is a cross-door object too: it binds the reader's projection, so
   * one door's continuation must redeem on the other. If it does not, the two
   * doors are reading different snapshots even when page one happened to match.
   *
   * red-proof: `key_id: HARNESS_KEY_ID` -> `key_id: "mcp-cursor-key"` inside
   * `prepareRead`'s `resolveAuthorization`, applied only when the caller is the
   * MCP door. APPLIED via the same mutable-binding trick as above; note the
   * trick's own limit, stated because it matters: because the binding stays
   * flipped after the first MCP call, the REST redemption below also runs
   * under the mutated identity and this test stayed GREEN while the byte
   * comparison above went red. The load-bearing observation is therefore the
   * one above; this test's job is to catch a split that persists per-door.
   */
  test("a continuation minted by one door redeems on the other", async () => {
    const mcp = await callTool(server.baseUrl, { limit: 3 });
    const mcpPage = JSON.parse(pageTextOf(mcp.text) as string) as {
      window: { nextCursor: string | null };
    };
    expect(typeof mcpPage.window.nextCursor).toBe("string");

    const restContinued = await recall(server.baseUrl, {
      limit: 3,
      cursor: mcpPage.window.nextCursor,
    });
    expect(restContinued.status).toBe(200);

    const mcpContinued = await callTool(server.baseUrl, {
      limit: 3,
      cursor: mcpPage.window.nextCursor,
    });
    expect(pageTextOf(mcpContinued.text)).toBe(restContinued.text);
  });

  /**
   * The pair, and the reason the two tests above are not satisfied by a server
   * that serves one empty page to everyone: the doors must actually be serving
   * the corpus, and two DIFFERENT readers must not share an id space.
   *
   * red-proof: in `integration/server/compose.ts`, seed every owner from one
   * shared database (drop the per-owner `databases` map and give
   * `prepareRead` a single db). The two owners then read the same rows under
   * the same reader-scoped digest and this fails on the disjointness check.
   */
  test("a different reader's ids are disjoint from this reader's", async () => {
    const mine = await recall(server.baseUrl, { limit: 3 });
    const theirs = await recall(server.baseUrl, { limit: 3, key: "omi-integration-qa-key-v2" });
    expect(theirs.status).toBe(200);

    const idsOf = (text: string): readonly string[] =>
      (JSON.parse(text) as { items: readonly { id: string }[] }).items.map((item) => item.id);

    const mineIds = idsOf(mine.text);
    const theirIds = idsOf(theirs.text);

    expect(mineIds).toHaveLength(3);
    expect(theirIds).toHaveLength(3);
    for (const id of theirIds) {
      expect(mineIds).not.toContain(id);
    }
  });
});
