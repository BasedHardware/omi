/**
 * `/qa/stats`: the build-provenance stamp and the per-client served-read
 * counter — against a live server.
 *
 * Both properties exist for the same reason: a claim like "the artifact I
 * measured is the artifact I edited" or "the app I launched read the backend
 * N times" is worthless unless it is JOINABLE to a specific source tree or a
 * specific caller. A global counter is satisfied by any stray client; an
 * aggregate stat proves nothing was stale. See serve.ts's header comment on
 * why the QA control plane is mounted on the SAME server as domain traffic —
 * a counter computed anywhere else would be exactly that kind of evidence.
 */

import { afterAll, beforeAll, describe, expect, test } from "bun:test";

import { callTool, control, recall, startLiveServer, stats, type LiveServer } from "./live-server";

let server: LiveServer;

beforeAll(async () => {
  server = await startLiveServer();
});

afterAll(async () => {
  await server?.stop();
});

describe("/qa/stats provenance stamp", () => {
  /**
   * red-proof: in provenance.ts `computeStamp`, hardcode `repo:
   * "core-foundation"` (or anything but the literal "platform") in the
   * success-branch return. Schema and shape stay right; only the repo name
   * changes, and this fails on that field alone.
   */
  test("carries a stamp with schema 1 and repo \"platform\"", async () => {
    const body = await stats(server.baseUrl);
    const stamp = body.stamp as Record<string, unknown> | undefined;

    expect(stamp).toBeDefined();
    expect((stamp as Record<string, unknown>).schema).toBe(1);
    expect((stamp as Record<string, unknown>).repo).toBe("platform");
    expect((stamp as Record<string, unknown>).artifact).toBe("backend-process");
  });

  /**
   * red-proof: in provenance.ts `computeStamp`'s success branch, set
   * `treeHash: "not-a-real-hash"` instead of the `git write-tree` output.
   * `unavailable` is still absent (this is not the failure path), so the
   * stamp is neither a real 40-hex tree id nor honestly unavailable — this
   * INVARIANT check fails without ever comparing to a specific hash value.
   */
  test("treeHash is 40-hex, or the stamp is honestly marked unavailable — never neither", async () => {
    const body = await stats(server.baseUrl);
    const stamp = body.stamp as Record<string, unknown>;

    if (typeof stamp.unavailable === "string") {
      // An unavailable stamp must be distinguishable from a real one: no
      // invented treeHash sitting alongside the excuse.
      expect(stamp.treeHash).toBeUndefined();
    } else {
      expect(typeof stamp.treeHash).toBe("string");
      expect(stamp.treeHash as string).toMatch(/^[0-9a-f]{40}$/);
    }
  });
});

describe("/qa/stats servedReadsByClient — a joinable per-client counter", () => {
  /**
   * red-proof: in serve.ts, delete the `clientReads.record(clientId)` call
   * from the recall-path branch of `fetch` (leave the `/mcp` one in place).
   * "run-a"/"run-b" then never appear and this fails on the first
   * `expect(byClient["run-a"])`.
   *
   * This is the load-bearing assertion: it checks the CONTENT two distinct
   * ids each land under their own key with their own count, not merely that
   * the map is non-empty (which a single shared bucket would also satisfy).
   */
  test("two distinct client ids on the recall route are counted separately; a request with no header lands under \"anonymous\"", async () => {
    await control(server.baseUrl, "/qa/reset?seed=7");

    await recall(server.baseUrl, { clientId: "run-a", limit: 2 });
    await recall(server.baseUrl, { clientId: "run-a", limit: 2 });
    await recall(server.baseUrl, { clientId: "run-b", limit: 2 });
    await recall(server.baseUrl, { limit: 2 }); // no x-omi-client-id header at all

    const body = await stats(server.baseUrl);
    const byClient = body.servedReadsByClient as Record<string, number>;

    expect(byClient["run-a"]).toBe(2);
    expect(byClient["run-b"]).toBe(1);
    expect(byClient.anonymous).toBe(1);
  });

  /**
   * red-proof: in serve.ts, delete the `clientReads.record(clientId)` call in
   * the `/mcp` branch of the top-level `fetch` handler (leave the recall
   * route's call in place). `servedReadsByClient["mcp-run"]` then stays
   * undefined and this fails.
   */
  test("the /mcp path also tags served reads by client id", async () => {
    await control(server.baseUrl, "/qa/reset?seed=7");

    await callTool(server.baseUrl, { clientId: "mcp-run", limit: 2 });
    await callTool(server.baseUrl, { clientId: "mcp-run", limit: 2 });
    await callTool(server.baseUrl, { clientId: "mcp-other", limit: 2 });

    const body = await stats(server.baseUrl);
    const byClient = body.servedReadsByClient as Record<string, number>;

    expect(byClient["mcp-run"]).toBe(2);
    expect(byClient["mcp-other"]).toBe(1);
  });

  /**
   * red-proof: in client-counter.ts `sanitizeClientId`, delete the
   * `rawClientId.length > MAX_CLIENT_ID_LENGTH` check (keep only the charset
   * regex). The 500-char id then survives sanitization verbatim and becomes
   * its own map key instead of folding into "anonymous" — this fails because
   * `byClient[oversized]` becomes defined and `byClient.anonymous` drops to 1
   * (only the off-charset id folds in) instead of 2.
   */
  test("an oversized or off-charset client id is rejected, not stored as a garbage key", async () => {
    await control(server.baseUrl, "/qa/reset?seed=7");

    const oversized = "x".repeat(500);
    const offCharset = "bad!id";

    await recall(server.baseUrl, { clientId: oversized, limit: 2 });
    await recall(server.baseUrl, { clientId: offCharset, limit: 2 });

    const body = await stats(server.baseUrl);
    const byClient = body.servedReadsByClient as Record<string, number>;

    expect(byClient[oversized]).toBeUndefined();
    expect(byClient[offCharset]).toBeUndefined();
    expect(byClient.anonymous).toBe(2);
    // Not merely "the bad keys are absent" — nothing besides anonymous exists.
    expect(Object.keys(byClient)).toEqual(["anonymous"]);
  });

  /**
   * red-proof: in client-counter.ts `record`, drop the
   * `counts.size < MAX_DISTINCT_CLIENT_KEYS` branch entirely (always use the
   * sanitized id as the key). Every one of the 70
   * distinct ids below then gets its own key, "overflow" never appears, and
   * `Object.keys(byClient).length` exceeds `MAX_DISTINCT_CLIENT_KEYS + 2`.
   */
  test("cycling client ids past the distinct-key cap collapses into \"overflow\", not unbounded growth", async () => {
    await control(server.baseUrl, "/qa/reset?seed=7");

    const distinctIds = 70; // > MAX_DISTINCT_CLIENT_KEYS (64)
    for (let index = 0; index < distinctIds; index += 1) {
      await recall(server.baseUrl, { clientId: `cycle-${index}`, limit: 2 });
    }

    const body = await stats(server.baseUrl);
    const byClient = body.servedReadsByClient as Record<string, number>;

    expect(byClient.overflow).toBeGreaterThan(0);
    // Bounded: MAX_DISTINCT_CLIENT_KEYS validated keys, plus the "overflow"
    // sentinel. ("anonymous" never appears here — every id was valid.)
    expect(Object.keys(byClient).length).toBeLessThanOrEqual(65);
  });
});
