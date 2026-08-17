// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-006)
import { afterAll, describe, expect, test } from "bun:test";

import { parseSynthesizedPageJson } from "@omi-core/ratified-contracts/projections/synthesized";

import { mcpCall, pageTextOf, rpcErrorOf } from "./mcp-client";
import { startQaServer, type QaServer } from "./server";

/**
 * Two-reader noninterference, over the live loopback flow.
 *
 * Hardening on top of the six proofs. Proof 4 shows a single reader's telemetry
 * carries no content; proof 6 shows one reader cannot detect a hidden record.
 * Neither says anything about **two** readers, and that is where opaque
 * identifiers usually fail: if the same internal record yields the same public
 * id for everybody, those ids become a global correlation key. Anyone holding a
 * page from reader A can then test whether reader B can see the same record.
 */

/** One account, two credentials: identical content, different readers. */
const SHARED_OWNER = "owner:shared-account";

const servers: QaServer[] = [];

const server = async (options: Parameters<typeof startQaServer>[0] = {}): Promise<QaServer> => {
  const started = await startQaServer({ port: 0, ...options });
  servers.push(started);
  return started;
};

afterAll(async () => {
  await Promise.all(servers.map((instance) => instance.stop()));
});

const readPage = async (instance: QaServer, limit = 100) => {
  const text = pageTextOf(await mcpCall({ url: instance.url, token: instance.token, limit }));
  expect(text).not.toBeNull();
  const parsed = parseSynthesizedPageJson(text!);
  expect(parsed).not.toBeNull();
  return parsed!;
};

describe("two-reader noninterference", () => {
  test("identical content under two readers yields disjoint opaque identifiers", async () => {
    // red-proof: drop `readerProjectionDigest` from `deriveReaderSubkey` in
    // apps/service/codecs/opaque-refs.ts and both readers produce the same ids,
    // making every public id a global correlation key across accounts.
    // CRITICAL: the SAME owner and the same seed, so the two readers see
    // byte-identical underlying content and identical internal candidate refs.
    // They differ only in credential.
    //
    // An earlier version of this test gave the readers different owners. It
    // passed with reader-scoping removed, because the owner id is baked into the
    // seeded claims and changes the render hashes anyway — so the test was
    // proving that different content yields different ids, which is worthless.
    // With one shared owner, only the codec's reader_scope can separate these.
    const readerA = await server({
      claim_count: 5,
      owner_account_id: SHARED_OWNER,
      app_id: "app:a",
      key_id: "key:a",
      token: "qa_token_reader_a",
    });
    const readerB = await server({
      claim_count: 5,
      owner_account_id: SHARED_OWNER,
      app_id: "app:b",
      key_id: "key:b",
      token: "qa_token_reader_b",
    });

    const pageA = await readPage(readerA);
    const pageB = await readPage(readerB);

    // The underlying content is structurally identical: same seed shape, same
    // claim count, same item count.
    expect(pageA.items.length).toBe(pageB.items.length);
    expect(pageA.items.length).toBeGreaterThan(0);

    const idsA = pageA.items.map((item) => item.id);
    const idsB = pageB.items.map((item) => item.id);
    // Same content, proven: the synthesized text is byte-identical between the
    // two readers. This is what makes the id disjointness meaningful.
    expect(pageA.items.map((item) => item.text)).toEqual(pageB.items.map((item) => item.text));

    const shared = idsA.filter((id) => idsB.includes(id));
    expect(shared).toEqual([]);

    // Citations must be reader-scoped too, not just item ids.
    const citationsA = pageA.items.flatMap((item) => item.citations ?? []);
    const citationsB = pageB.items.flatMap((item) => item.citations ?? []);
    expect(citationsA.length).toBeGreaterThan(0);
    expect(citationsA.filter((ref) => citationsB.includes(ref))).toEqual([]);
  });

  test("one reader's cursor is worthless to another reader", async () => {
    // A continuation token must not be transferable. If reader B can redeem
    // reader A's cursor, the cursor is a bearer capability for A's page state.
    const readerA = await server({
      claim_count: 6, owner_account_id: SHARED_OWNER, app_id: "app:a", key_id: "key:a",
      token: "qa_token_cur_a",
    });
    const readerB = await server({
      claim_count: 6, owner_account_id: SHARED_OWNER, app_id: "app:b", key_id: "key:b",
      token: "qa_token_cur_b",
    });

    const firstA = await readPage(readerA, 2);
    expect(firstA.window.nextCursor).not.toBeNull();

    const stolen = await mcpCall({
      url: readerB.url, token: readerB.token, limit: 2, cursor: firstA.window.nextCursor!,
    });
    expect(rpcErrorOf(stolen)).toEqual({ code: -32602, message: "Invalid cursor" });
    expect(pageTextOf(stolen)).toBeNull();
  });

  test("another reader's token is not accepted, and fails like an unknown one", async () => {
    const readerA = await server({
      claim_count: 3, owner_account_id: SHARED_OWNER, app_id: "app:a", key_id: "key:a",
      token: "qa_token_tok_a",
    });
    const readerB = await server({
      claim_count: 3, owner_account_id: SHARED_OWNER, app_id: "app:b", key_id: "key:b",
      token: "qa_token_tok_b",
    });

    const crossToken = await mcpCall({ url: readerA.url, token: readerB.token, limit: 2 });
    const unknownToken = await mcpCall({ url: readerA.url, token: "qa_not_a_real_token", limit: 2 });

    expect(crossToken.status).toBe(401);
    // Byte-identical: a valid-elsewhere token must not be distinguishable from
    // a wholly invented one.
    expect(crossToken.rawBody).toBe(unknownToken.rawBody);
  });

  test("a reader's page bytes never contain the other reader's identity", async () => {
    const readerA = await server({
      claim_count: 4, owner_account_id: "owner:iso-a", app_id: "app:a", key_id: "key:a",
      token: "qa_token_iso_a",
    });
    const readerB = await server({
      claim_count: 4, owner_account_id: "owner:iso-b", app_id: "app:b", key_id: "key:b",
      token: "qa_token_iso_b",
    });

    const rawA = await mcpCall({ url: readerA.url, token: readerA.token, limit: 100 });
    for (const needle of ["owner:iso-b", "app:b", "key:b", readerB.token,
      "owner:iso-a", "app:a", "key:a", readerA.token]) {
      expect(rawA.rawBody).not.toContain(needle);
    }
    // And the trace side, for both.
    expect(JSON.stringify(readerA.traces())).not.toContain("owner:iso-b");
    expect(JSON.stringify(readerA.traces())).not.toContain("owner:iso-a");
  });
});
