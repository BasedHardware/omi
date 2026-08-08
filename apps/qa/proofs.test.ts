// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-006)
import { afterAll, describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";

import { readAfterApplicationAuthorization } from "../../core/retrieve/authorization-boundary";
import { selectNodesForGranularity } from "../../core/retrieve/granularity";
import { buildDeterministicAnchors } from "../../core/retrieve/tree";
import { createSqliteQaRecallLoader } from "../../drivers/sqlite/application-recall-read";
import { QA_CODEC_SECRET, qaReaderScope } from "./codec-scope";
import { createQaReferenceCodecs } from "./codecs";
import { produceQaRenders } from "./renders";
import { seedQaSnapshot } from "./seed";

import { parseSynthesizedPageJson } from "@omi-core/ratified-contracts/projections/synthesized";

import { assertLoopbackOnly } from "./loopback";
import { mcpCall, pageTextOf, rpcErrorOf, type McpCallResult } from "./mcp-client";
import { qaRequestTelemetry } from "./mcp-ports";
import { startQaServer, type QaServer } from "./server";

/**
 * The six proofs, executed against a **live loopback HTTP server** running the
 * whole flow: Hono -> Bun MCP adapter -> MCP protocol -> QA ports -> application
 * read -> SQLite QA snapshot. Not a unit fake.
 *
 * Every invariant test here carries a `// red-proof:` naming the mutation that
 * makes it fail, and those mutations were applied and observed, not assumed.
 */

const servers: QaServer[] = [];

const server = async (options: Parameters<typeof startQaServer>[0] = {}): Promise<QaServer> => {
  // Port 0: BE-FLOW owns 4801/4802, but the proofs run in parallel with other
  // test files and must not fight over a fixed port. The bind is still loopback.
  const started = await startQaServer({ port: 0, ...options });
  servers.push(started);
  return started;
};

afterAll(async () => {
  await Promise.all(servers.map((instance) => instance.stop()));
});

const page = (result: McpCallResult) => {
  const text = pageTextOf(result);
  expect(text).not.toBeNull();
  const parsed = parseSynthesizedPageJson(text!);
  expect(parsed).not.toBeNull();
  return parsed!;
};

// ─────────────────────────────────────────────────────────────────────────────

describe("PROOF 1 — page-one / page-two pagination over the real localhost flow", () => {
  test("two pages walk the whole set with no gap, no overlap, and an honest window", async () => {
    // red-proof: in core/retrieve/application-read.ts pageCandidates, change
    // `start = index + 1` to `start = index` and page two re-serves the last
    // item of page one, which the no-overlap assertion below catches.
    const instance = await server({ claim_count: 5 });

    const first = page(await mcpCall({ url: instance.url, token: instance.token, limit: 4 }));
    expect(first.items).toHaveLength(4);
    expect(first.window.status).toBe("more");
    expect(first.window.hasMore).toBe(true);
    expect(first.window.complete).toBe(false);
    expect(first.window.nextCursor).not.toBeNull();

    const collected = [...first.items.map((item) => item.id)];
    let cursor = first.window.nextCursor;
    let guard = 0;
    while (cursor !== null && guard < 20) {
      guard += 1;
      const next = page(await mcpCall({
        url: instance.url, token: instance.token, limit: 4, cursor,
      }));
      collected.push(...next.items.map((item) => item.id));
      cursor = next.window.nextCursor;
    }

    // Default granularity is temporal_leaf per decisions/COORD-item-granularity.md,
    // so 5 claims on 5 distinct local days yield exactly 5 items.
    expect(collected).toHaveLength(5);
    expect(new Set(collected).size).toBe(5);

    const whole = page(await mcpCall({ url: instance.url, token: instance.token, limit: 100 }));
    expect(whole.items).toHaveLength(5);
    expect(whole.window.hasMore).toBe(false);
    expect(whole.window.nextCursor).toBeNull();
    // Paging must not reorder: the concatenation equals the single-page order.
    expect(collected).toEqual(whole.items.map((item) => item.id));
  });

  test("the server binds loopback only and is unreachable from the LAN", async () => {
    const instance = await server({ claim_count: 2 });
    const report = await assertLoopbackOnly(instance.port);
    expect(report.loopback_only).toBe(true);
    expect(report.lan_unreachable).toBe(true);
    expect(report.listening_addresses.length).toBeGreaterThan(0);
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe("PROOF 2 — cursor tamper rejection, identical regardless of how it was mutated", () => {
  test("every mutation shape yields one indistinguishable rejection", async () => {
    // red-proof: delete the isSyntacticallyRedeemableCursor guard in
    // recall-service.readPage. The control-character and non-ASCII cases then
    // surface as -32603 "Internal error" instead of -32602 "Invalid cursor",
    // and the single-shape assertion below fails.
    //
    // Scope note, measured not assumed: the uniformity claim covers cursors that
    // are ADMISSIBLE TOOL ARGUMENTS. The tool's published input schema declares
    // `cursor` maxLength 4096, and the transport rejects a longer string as
    // "Invalid params" in parseToolCall, before the cursor layer or the
    // visibility gate ever run. That is a schema bound on the caller's own
    // input, not a cursor decision -- and the test below proves it is not an
    // oracle by showing an authorized and a revoked caller get the identical
    // response for it.
    const instance = await server({ claim_count: 5 });
    const first = page(await mcpCall({ url: instance.url, token: instance.token, limit: 2 }));
    const valid = first.window.nextCursor!;
    expect(valid).not.toBeNull();
    const parts = valid.split(".");

    const mutations: Readonly<Record<string, string>> = {
      empty_payload: "not-a-cursor",
      truncated_segments: `${parts[0]}.${parts[1]}.${parts[2]}`,
      extra_segment: `${valid}.extra`,
      flipped_signature: `${parts[0]}.${parts[1]}.${parts[2]}.${"A".repeat(43)}`,
      unknown_key_id: `${parts[0]}.unknown-key.${parts[2]}.${parts[3]}`,
      flipped_payload_byte: `${parts[0]}.${parts[1]}.${parts[2]!.slice(0, -1)}X.${parts[3]}`,
      wrong_prefix: `zzz1.${parts[1]}.${parts[2]}.${parts[3]}`,
      control_character: `${valid}`,
      // At the schema bound but still an admissible tool argument.
      at_max_length: "z".repeat(4_096),
      non_ascii: `${valid}é`,
      whitespace: `${valid} `,
    };

    const observed = new Map<string, string>();
    for (const [name, cursor] of Object.entries(mutations)) {
      const result = await mcpCall({ url: instance.url, token: instance.token, limit: 2, cursor });
      const error = rpcErrorOf(result);
      observed.set(name, `${result.status}|${error?.code}|${error?.message}`);
    }

    // One shape for all of them. If any mutation produced a different status,
    // code, or message, the map below names exactly which one leaked.
    const distinct = new Set(observed.values());
    expect({ distinct: [...distinct], observed: Object.fromEntries(observed) }).toEqual({
      distinct: ["400|-32602|Invalid cursor"],
      observed: Object.fromEntries([...observed.keys()].map((key) => [key, "400|-32602|Invalid cursor"])),
    });
  });

  test("the over-length schema bound is not an authorization oracle", async () => {
    // The one rejection that differs (-32602 "Invalid params" instead of
    // "Invalid cursor") happens in the transport's parseToolCall, above both the
    // cursor layer and the visibility gate. It is only a leak if it varies with
    // server state, so assert exactly that it does not: an authorized caller and
    // a revoked caller must receive byte-identical responses.
    // red-proof: move the parseToolCall length check below visibilityGate in
    // apps/mcp/protocol.ts and the revoked caller starts getting "Tool
    // unavailable" here instead, which does distinguish authorization state.
    const instance = await server({ claim_count: 4 });
    const overLength = "z".repeat(4_097);

    const authorized = await mcpCall({
      url: instance.url, token: instance.token, limit: 2, cursor: overLength,
    });
    instance.registry.revokeGrant(instance.principal);
    const revoked = await mcpCall({
      url: instance.url, token: instance.token, limit: 2, cursor: overLength,
    });

    expect(authorized.status).toBe(revoked.status);
    expect(authorized.rawBody).toBe(revoked.rawBody);
    expect(rpcErrorOf(authorized)).toEqual({ code: -32602, message: "Invalid params" });

    // And it must not reveal snapshot content either.
    const hidden = await server({ claim_count: 6, hidden_indices: [5] });
    const absent = await server({ claim_count: 5 });
    const fromHidden = await mcpCall({ url: hidden.url, token: hidden.token, limit: 2, cursor: overLength });
    const fromAbsent = await mcpCall({ url: absent.url, token: absent.token, limit: 2, cursor: overLength });
    expect(fromHidden.rawBody).toBe(fromAbsent.rawBody);

    instance.registry.restore(instance.principal);
  });

  test("a cursor is bound to its snapshot and its reader", async () => {
    // red-proof: drop projection_generation_digest from qaCursorBindings and a
    // cursor minted on one snapshot redeems against a different one.
    const five = await server({ claim_count: 5 });
    const four = await server({ claim_count: 4 });

    const fromFive = page(await mcpCall({ url: five.url, token: five.token, limit: 2 }));
    const foreign = await mcpCall({
      url: four.url, token: four.token, limit: 2, cursor: fromFive.window.nextCursor!,
    });
    expect(rpcErrorOf(foreign)).toEqual({ code: -32602, message: "Invalid cursor" });
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe("PROOF 3 — final revocation fencing produces zero further emission", () => {
  test("the FINAL pre-emission fence refuses a page that was already built", async () => {
    // This is the real proof-3 case, and it is not the same as the one below.
    //
    // A grant revoked *before* a request is caught by the visibility gate, which
    // returns "Tool unavailable" without ever calling readPage -- so the final
    // fence is never exercised. Measured: readPage stays at 1, reauthorize stays
    // at 1, reauthorizeDenied stays at 0. A test that only revokes up front
    // proves the first gate and says nothing about the last one.
    //
    // So revoke from inside the trace sink: that fires after the page bytes and
    // the cursor already exist, and before reauthorizeBeforeEmission runs. The
    // fence must then throw the fully-built page away.
    //
    // red-proof: make mcp-ports.reauthorizeBeforeEmission `return true`
    // unconditionally, and the built page is emitted to a caller whose
    // authorization died while it was being built.
    let revokeNow = false;
    let holder: QaServer | null = null;
    const fenced = await server({
      claim_count: 5,
      onTraceEmitted: () => {
        if (revokeNow && holder !== null) holder.registry.revokeGrant(holder.principal);
      },
    });
    holder = fenced;

    // Warm-up read while fully authorized.
    const warm = page(await mcpCall({ url: fenced.url, token: fenced.token, limit: 2 }));
    expect(warm.items.length).toBeGreaterThan(0);
    const tracesBefore = fenced.traces().length;
    const deniedBefore = fenced.counters().reauthorizeDenied;

    revokeNow = true;
    const result = await mcpCall({ url: fenced.url, token: fenced.token, limit: 2 });

    // The page was built -- readPage ran and a trace was emitted -- and then the
    // fence refused it. No bytes reach the caller.
    expect(fenced.traces().length).toBe(tracesBefore + 1);
    expect(fenced.counters().reauthorizeDenied).toBe(deniedBefore + 1);
    expect(pageTextOf(result)).toBeNull();
    expect(rpcErrorOf(result)).toEqual({ code: -32003, message: "Access no longer permitted" });
    expect(result.rawBody).not.toContain("mem1_");
    expect(result.rawBody).not.toContain("contractVersion");
    expect(result.rawBody).not.toContain("mcp1.");
    expect(result.rawBody).not.toContain("QA synthesized proposition");
  });

  test("a grant revoked before the request is refused at the visibility gate", async () => {
    // The complementary case. Here the fence never runs because the gate above
    // it already denied -- readPage is never called at all.
    // red-proof: make mcp-ports.currentlyAuthorized cache its decision instead
    // of re-resolving the registry, and the revoked read below serves a page.
    // (Applied: the read is still denied, because core's own authorization
    //  boundary independently re-derives the grant. Two fences, not one.)
    const instance = await server({ claim_count: 5 });

    const before = page(await mcpCall({ url: instance.url, token: instance.token, limit: 2 }));
    expect(before.items.length).toBeGreaterThan(0);
    const tracesBefore = instance.traces().length;
    expect(tracesBefore).toBeGreaterThan(0);

    instance.registry.revokeGrant(instance.principal);

    const after = await mcpCall({ url: instance.url, token: instance.token, limit: 2 });
    expect(pageTextOf(after)).toBeNull();
    expect(after.rawBody).not.toContain("mem1_");
    expect(after.rawBody).not.toContain("contractVersion");
    expect(after.rawBody).not.toContain("QA synthesized proposition");

    // The fence produced NO side effects: not one additional trace was emitted.
    expect(instance.traces().length).toBe(tracesBefore);

    instance.registry.restore(instance.principal);
    const restored = page(await mcpCall({ url: instance.url, token: instance.token, limit: 2 }));
    expect(restored.items.length).toBeGreaterThan(0);
  });

  test("a revoked caller cannot tell a hidden tool from an unknown one", async () => {
    const instance = await server({ claim_count: 3 });
    instance.registry.revokeGrant(instance.principal);

    const hiddenTool = await mcpCall({ url: instance.url, token: instance.token, limit: 2 });
    const unknownTool = await mcpCall({
      url: instance.url, token: instance.token, limit: 2, toolName: "definitely_not_a_tool",
    });
    expect(rpcErrorOf(hiddenTool)).toEqual(rpcErrorOf(unknownTool));
    expect(hiddenTool.status).toBe(unknownTool.status);

    // tools/list reveals nothing either.
    const listed = await mcpCall({ url: instance.url, token: instance.token, method: "tools/list" });
    expect(JSON.stringify(listed.body)).not.toContain("read_synthesized_memory");
  });

  test("an unauthenticated caller is refused before any read work happens", async () => {
    const instance = await server({ claim_count: 3 });
    const countersBefore = instance.counters();
    const anonymous = await mcpCall({ url: instance.url, limit: 2 });
    expect(anonymous.status).toBe(401);
    expect(instance.counters().readPage).toBe(countersBefore.readPage);
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe("PROOF 4 — default telemetry and traces carry opaque references only", () => {
  test("emitted trace bytes contain no raw query, memory, evidence, or source content", async () => {
    // red-proof: add `summary: candidate.synthesized_text` to the trace built in
    // application-read.finalizeApplicationPage and the synthesized-text assertion
    // below fails.
    const instance = await server({ claim_count: 4 });
    await mcpCall({ url: instance.url, token: instance.token, limit: 100 });

    const traces = instance.traces();
    expect(traces.length).toBeGreaterThan(0);
    const bytes = JSON.stringify(traces);

    const forbidden = [
      instance.principal.owner_account_id,
      instance.principal.app_id,
      instance.principal.key_id,
      instance.token,
      "qa-claim:",
      "qa-evidence:",
      "qa-event-revision:",
      "qa-session:",
      "qa-source:",
      "qa seed ",                      // evidence excerpt text
      "QA synthesized proposition",    // synthesized memory text
      "qa_seed_predicate",
      "retrieval-node-v1:",            // internal structural node identity
    ];
    const leaked = forbidden.filter((needle) => bytes.includes(needle));
    expect(leaked).toEqual([]);

    // Positively: every reference in the trace is an opaque tr1_ handle.
    const refs = bytes.match(/"tr1_[a-f0-9]{64}"/g) ?? [];
    expect(refs.length).toBeGreaterThan(0);
  });

  test("default request telemetry admits only counts, enums and status", () => {
    const event = qaRequestTelemetry({
      method: "tools/call", status: 200, outcome: "ok", item_count: 12, has_more: false,
    });
    expect(Object.keys(event).sort()).toEqual([
      "event", "has_more", "item_count", "method", "outcome", "status",
    ]);
    for (const value of Object.values(event)) {
      expect(["string", "number", "boolean"]).toContain(typeof value);
    }
  });

  test("an error response body carries no internal identifier or stack", async () => {
    const instance = await server({ claim_count: 3 });
    const bad = await mcpCall({ url: instance.url, token: instance.token, limit: 2, cursor: "garbage" });
    for (const needle of ["qa-claim:", "qa-evidence:", instance.principal.owner_account_id,
      "at ", ".ts:", "SqliteLedger", "Database"]) {
      expect(bad.rawBody).not.toContain(needle);
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe("PROOF 5 — deterministic server order", () => {
  test("same snapshot, same order — independent of host, clock, locale and insertion history", async () => {
    // red-proof: in core/retrieve/application-read.ts attachVisibleKeys, sort
    // `winners` by anything host-dependent (e.g. Math.random or Date.now) and
    // the byte-equality assertions below fail.
    const ascending = await server({ claim_count: 6 });

    // Same content, opposite physical insertion order.
    const descending = await server({ claim_count: 6, insertion_order: "descending" });

    const readOnce = async (instance: QaServer): Promise<string> => {
      const text = pageTextOf(await mcpCall({ url: instance.url, token: instance.token, limit: 100 }));
      expect(text).not.toBeNull();
      return text!;
    };

    const first = await readOnce(ascending);
    const repeat = await readOnce(ascending);
    expect(repeat).toBe(first);

    // Insertion history must not move a single byte.
    expect(await readOnce(descending)).toBe(first);

    // Neither must the process clock or locale environment.
    const originalTz = process.env.TZ;
    const originalLang = process.env.LANG;
    const originalCollate = process.env.LC_ALL;
    try {
      process.env.TZ = "Asia/Kolkata";
      process.env.LANG = "tr_TR.UTF-8";   // Turkish: the classic dotted-i collation trap
      process.env.LC_ALL = "tr_TR.UTF-8";
      expect(await readOnce(ascending)).toBe(first);
    } finally {
      if (originalTz === undefined) delete process.env.TZ; else process.env.TZ = originalTz;
      if (originalLang === undefined) delete process.env.LANG; else process.env.LANG = originalLang;
      if (originalCollate === undefined) delete process.env.LC_ALL; else process.env.LC_ALL = originalCollate;
    }

    // A fresh server over an independently built database agrees byte for byte.
    const independent = await server({ claim_count: 6 });
    expect(await readOnce(independent)).toBe(first);
  });

  test("the order IS ascending structural node identity, not merely repeatable", async () => {
    // Every assertion above compares a read against another read, so a change
    // that reorders *every* read identically slips straight through. Applied and
    // observed: reversing the merged candidate list in application-read.ts left
    // all of them green. "Repeatable" is a strictly weaker claim than "correct
    // order", and only this test tells them apart.
    //
    // This used to extract the node id from the item text, which worked only
    // because the MCP synthesizer leaked `retrieval-node-v1:<hash>` onto the
    // wire. The shared synthesizer correctly does not, so the expected order is
    // now RECOMPUTED independently: seed the same snapshot, project, produce
    // renders, sort by node id, and derive the public item id through the same
    // keyed codec the server uses. That pins the documented rule rather than a
    // fingerprint of today's output.
    //
    // red-proof: reverse the result of mergeAuthorizedRecallCandidates in
    // core/retrieve/application-read.ts -- this fails while every stability
    // assertion above still passes.
    const instance = await server({ claim_count: 6 });
    const result = page(await mcpCall({ url: instance.url, token: instance.token, limit: 100 }));

    const db = new Database(":memory:");
    seedQaSnapshot(db, {
      owner_account_id: instance.principal.owner_account_id,
      account_timezone: "UTC",
      claim_count: 6,
    });
    const load = createSqliteQaRecallLoader({
      db,
      owner_account_id: instance.principal.owner_account_id,
      account_timezone: "UTC",
      limits: { max_items: 256, max_bytes: 4_000_000 },
    })();
    const projected = readAfterApplicationAuthorization({
      owner_account_id: instance.principal.owner_account_id,
      credential: {
        owner_account_id: instance.principal.owner_account_id,
        credential_kind: "mcp_api_key",
        app_id: instance.principal.app_id,
        key_id: instance.principal.key_id,
        scopes: ["memories.read"],
        active: true,
      },
      persisted_grant: {
        owner_account_id: instance.principal.owner_account_id,
        consumer: "mcp",
        app_id: instance.principal.app_id,
        key_id: instance.principal.key_id,
        enabled: true,
        default_read: true,
        scopes: ["memories.read"],
      },
      // storage-provenance-ok(test recomputes the same authorized projection the server built)
    }, () => ({ snapshot: structuredClone(load.durable_snapshot), options: { account_timezone: "UTC" } }));

    const allRenders = await produceQaRenders(projected);
    const leafIds = new Set(
      selectNodesForGranularity(buildDeterministicAnchors(projected).nodes, "temporal_leaf")
        .map((structuralNode) => structuralNode.node_id),
    );
    const codecs = createQaReferenceCodecs({
      secret: QA_CODEC_SECRET,
      reader_scope: qaReaderScope(instance.principal),
    });
    const expectedIds = allRenders
      .filter((render) => leafIds.has(render.node_id))
      .sort((left, right) => (left.node_id < right.node_id ? -1 : left.node_id > right.node_id ? 1 : 0))
      .map((render) => codecs.encodeItemRef(`render:${render.render_hash}`));

    expect(expectedIds.length).toBe(6);
    expect(result.items.map((item) => item.id)).toEqual(expectedIds);

    // And paging at a different size yields the identical sequence.
    const ids = result.items.map((item) => item.id);
    const paged: string[] = [];
    let cursor: string | null = null;
    do {
      const next = page(await mcpCall({
        url: instance.url, token: instance.token, limit: 1, cursor,
      }));
      paged.push(...next.items.map((item) => item.id));
      cursor = next.window.nextCursor;
    } while (cursor !== null);
    expect(paged).toEqual(ids);
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe("PROOF 6 — hidden-present and physically-absent are byte-identical", () => {
  /**
   * The one where a plausible implementation leaks. A record hidden by
   * authorization and a record that never existed must be indistinguishable on
   * the wire: any difference in ordering, count, envelope, cursor, frontier, or
   * error shape is an authorization oracle.
   *
   * SCOPE, stated so this proof cannot be misread: it establishes **byte**
   * identity, and explicitly NOT **timing** identity. Measured separately, a
   * 20-visible/300-hidden snapshot answers byte-identically to a 20-visible/
   * 0-hidden one while taking 5.25x longer (p50 34.8ms vs 6.6ms), because the
   * loader materializes every owner row and filters afterwards. The brief counts
   * timing as an oracle, so that residual is real and is documented in
   * blocked/BE-FLOW-timing-oracle.md. Do not read "hidden vs absent: identical"
   * below as "the channel is closed".
   *
   * This caught a real leak in my own first implementation. The declared
   * frontier and three cursor bindings were derived from the SQLite loader's
   * `coherent_snapshot_digest` and ledger head sequence, both of which cover
   * hidden rows. Measured: digests 3ad6626b… vs 1441b306…, ledger sequence 6 vs
   * 5. The fix is the visible-derivation rule in recall-service.ts.
   */
  const HIDDEN_INDEX = 5;

  test("a full page is byte-identical whether the record is hidden or absent", async () => {
    // red-proof: in recall-service.buildMaterial, derive declaredFrontier from
    // `load.coherent_snapshot_digest` instead of `projected.graph_generation`.
    // The two pages then differ in exactly one field and this fails.
    const hidden = await server({ claim_count: 6, hidden_indices: [HIDDEN_INDEX] });
    const absent = await server({ claim_count: 5 });

    const hiddenText = pageTextOf(await mcpCall({ url: hidden.url, token: hidden.token, limit: 100 }));
    const absentText = pageTextOf(await mcpCall({ url: absent.url, token: absent.token, limit: 100 }));
    expect(hiddenText).not.toBeNull();
    expect(absentText).not.toBeNull();

    // Byte identity, not structural equivalence.
    expect(hiddenText).toBe(absentText);

    // And the hidden record really was present in storage.
    const parsed = parseSynthesizedPageJson(hiddenText!)!;
    expect(parsed.items.length).toBe(5);

    // Pins audit finding 2: the storage ledger sequence (6 vs 5) enters the
    // projection pipeline and is then OVERWRITTEN with a visible-only digest.
    // Byte identity above depends on that overwrite holding. Asserting the
    // projection digests directly fails at the layer where a regression would be
    // introduced, instead of only at the wire.
    const hiddenFrontier = parsed.completeness.frontiers.declaredFrontier;
    const absentFrontier = parseSynthesizedPageJson(absentText!)!.completeness.frontiers.declaredFrontier;
    expect(hiddenFrontier).toBe(absentFrontier);
    // The frontier is a visible-only digest, so it is a bare sha256 with no
    // storage sequence embedded. (An earlier version asserted the digit "6" was
    // absent, which is nonsense against hex -- equality with the absent-case
    // frontier is the assertion that actually carries the property.)
    expect(hiddenFrontier).toMatch(/^frontier-v1:qa:[a-f0-9]{64}$/);
    expect(hiddenText).not.toContain("qa-claim");
  });

  test("paginated reads stay byte-identical, cursor included", async () => {
    const hidden = await server({ claim_count: 6, hidden_indices: [HIDDEN_INDEX] });
    const absent = await server({ claim_count: 5 });

    const walk = async (instance: QaServer): Promise<string[]> => {
      const pages: string[] = [];
      let cursor: string | null = null;
      let guard = 0;
      do {
        const result = await mcpCall({ url: instance.url, token: instance.token, limit: 3, cursor });
        const text = pageTextOf(result);
        expect(text).not.toBeNull();
        pages.push(text!);
        cursor = parseSynthesizedPageJson(text!)!.window.nextCursor;
        guard += 1;
      } while (cursor !== null && guard < 20);
      return pages;
    };

    const hiddenPages = await walk(hidden);
    const absentPages = await walk(absent);
    // Every page, including the signed cursors embedded in them.
    expect(hiddenPages).toEqual(absentPages);
    expect(hiddenPages.length).toBeGreaterThan(1);
    expect(hiddenPages.some((text) => text.includes("nextCursor\":\"mcp1."))).toBe(true);
  });

  test("a cursor from the hidden-record snapshot redeems against the absent one", async () => {
    // The strongest form: the two snapshots are not merely rendered alike, they
    // are the same authorized read. If any hidden-row state had reached a cursor
    // binding, this cross-redemption would be refused.
    const hidden = await server({ claim_count: 6, hidden_indices: [HIDDEN_INDEX] });
    const absent = await server({ claim_count: 5 });

    const fromHidden = page(await mcpCall({ url: hidden.url, token: hidden.token, limit: 3 }));
    expect(fromHidden.window.nextCursor).not.toBeNull();

    const redeemed = await mcpCall({
      url: absent.url, token: absent.token, limit: 3, cursor: fromHidden.window.nextCursor!,
    });
    expect(rpcErrorOf(redeemed)).toBeNull();
    const continued = page(redeemed);
    expect(continued.items.length).toBeGreaterThan(0);

    const nativeSecond = page(await mcpCall({
      url: absent.url, token: absent.token, limit: 3, cursor: fromHidden.window.nextCursor!,
    }));
    expect(continued.items.map((item) => item.id)).toEqual(nativeSecond.items.map((item) => item.id));
  });

  test("error responses are identical for hidden and absent snapshots", async () => {
    const hidden = await server({ claim_count: 6, hidden_indices: [HIDDEN_INDEX] });
    const absent = await server({ claim_count: 5 });

    for (const cursor of ["garbage", "mcp1.a.b.c"]) {
      const left = await mcpCall({ url: hidden.url, token: hidden.token, limit: 2, cursor });
      const right = await mcpCall({ url: absent.url, token: absent.token, limit: 2, cursor });
      expect(left.status).toBe(right.status);
      expect(left.rawBody).toBe(right.rawBody);
    }
  });
});
