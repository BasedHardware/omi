/**
 * CROSS-SIDE WIRE AGREEMENT
 * =========================
 *
 * The bug class this exists to catch, in the coordinator's words: FE-SURFACES
 * built entitlement UI against a RESERVED frame nobody emits, while the server
 * emits a different one. Each side is individually correct. Each side's suite
 * is green. The feature never fires against a real server, and no hermetic
 * test on either side can see it — because each side tests against its own
 * locally-authored idea of the other side's wire.
 *
 * It is the same shape as "448 green tests, zero served requests".
 *
 * The only structural cure is a test that consumes the REAL wire shape of the
 * other side rather than a re-typed copy of it. So this test:
 *
 *   - imports the REAL client, `@omi-core/adapters-platform`, the exact module
 *     the surfaces call, with no re-implementation of its request building or
 *     its parsing; and
 *   - drives it over REAL HTTP against the REAL backend process
 *     (`platform/integration/server/serve.ts`), booted as a child.
 *
 * Neither side is mocked, so a disagreement about a route, a query parameter,
 * an auth header, a status code, a field name, or an encoding fails HERE — in
 * the one place that is looking at both ends at once.
 *
 * This is deliberately outside `core/`: core isolation rule 3 forbids `fetch`
 * against backend endpoint shapes anywhere but `adapters-legacy/` and
 * `shells/`, and an end-to-end driver must do exactly that.
 */

import { spawn } from "node:child_process";
import { once } from "node:events";
import assert from "node:assert/strict";
import { after, before, describe, test } from "node:test";

// Imported from the BUILT dist by path, not by package name: this file lives
// outside the pnpm workspace on purpose (see the isolation note above), and
// resolving the real module from its own directory is what lets pnpm's
// symlinks satisfy its dependencies. It is still the exact module the
// surfaces import - not a copy.
const { fetchSynthesizedMemoryPage, PLATFORM_MEMORY_RECALL_PATH } = await import(
  new URL("../../core/packages/adapters-platform/dist/index.js", import.meta.url).href
);

const PLATFORM_REPO = new URL("../../../platform/", import.meta.url).pathname;
const TOKEN = "omi-integration-qa-key-v1";
const BOOT_TIMEOUT_MS = 20_000;

let child;
let baseUrl;

/**
 * A real HTTP binding, shaped like the one a shell provides: it supplies the
 * base URL and the bearer token, and hands the adapter the RAW body text so
 * the adapter can use its strong `canonical-json-text` boundary. ADR-008 §3 —
 * auth lives in the transport binding, never in the adapter package.
 */
function realHttpClient(base, token = TOKEN) {
  return {
    async request(method, path, body) {
      const response = await fetch(`${base}${path}`, {
        method,
        headers: {
          ...(token === null ? {} : { authorization: `Bearer ${token}` }),
          ...(body === undefined ? {} : { "content-type": "application/json" }),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      const text = await response.text();
      let json;
      try {
        json = JSON.parse(text);
      } catch {
        json = null;
      }
      return { status: response.status, json, text };
    },
  };
}

before(async () => {
  const port = 4853; // harness-local; avoids the registry's fixed allocations
  child = spawn("bun", ["run", "integration/server/serve.ts"], {
    cwd: PLATFORM_REPO,
    env: { ...process.env, TZ: "UTC", OMI_INTEGRATION_PORT: String(port) },
    stdio: ["ignore", "pipe", "pipe"],
  });
  baseUrl = `http://127.0.0.1:${port}`;

  const deadline = Date.now() + BOOT_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`backend exited before readiness (status ${child.exitCode})`);
    }
    try {
      const probe = await fetch(`${baseUrl}/health`);
      if (probe.ok) return;
    } catch {
      // not up yet
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error("backend did not become ready");
});

after(async () => {
  if (child && child.exitCode === null) {
    child.kill();
    await once(child, "exit");
  }
});

describe("the real platform client against the real platform server", () => {
  // red-proof: change PLATFORM_RECALL_PATH in platform/integration/server/serve.ts
  // from "/v1/memories" to "/v1/memory". The client keeps requesting the
  // settled path, the server 404s, and this fails with kind:"http-error"
  // status 404 — which is precisely the entitlement-frame collision detected
  // one layer down. APPLIED and observed, not reasoned about.
  test("the settled route agrees end to end", async () => {
    await fetch(`${baseUrl}/qa/reset?seed=7`);
    const http = realHttpClient(baseUrl);

    const outcome = await fetchSynthesizedMemoryPage(http, { limit: 3 });

    assert.equal(
      outcome.kind,
      "page",
      `real client could not read the real server: ${JSON.stringify(outcome)}`,
    );

    // The STRONG boundary. If the server re-serialized the page, or the
    // binding dropped the raw text, the adapter silently falls back to the
    // weaker object predicate — which cannot see duplicate keys or a
    // noncanonical encoding. Asserting the boundary is what keeps that
    // degradation from passing as success.
    assert.equal(outcome.boundary, "canonical-json-text");

    // Content only a working mechanism produces, not a row count.
    assert.equal(outcome.page.contractVersion, "1.0.0");
    assert.equal(outcome.page.items[0].id, "retrieval-node-v1:seed-0000");
    assert.equal(outcome.page.window.status, "more");
    assert.equal(typeof outcome.page.window.nextCursor, "string");
  });

  // red-proof: make the server ignore the `cursor` query parameter. Page two
  // then repeats page one, the walk never advances, and the exactly-once
  // assertion below fails naming the duplicated id.
  test("cursor round-trips through the real client without losing rows", async () => {
    await fetch(`${baseUrl}/qa/reset?seed=7`);
    const http = realHttpClient(baseUrl);

    const seen = [];
    let cursor;
    for (let guard = 0; guard < 20; guard += 1) {
      const outcome = await fetchSynthesizedMemoryPage(http, { limit: 2, cursor });
      assert.equal(outcome.kind, "page", JSON.stringify(outcome));
      for (const item of outcome.page.items) seen.push(item.id);
      cursor = outcome.page.window.nextCursor;
      if (cursor === null) break;
    }

    assert.equal(cursor, null, "walk did not terminate");
    for (const id of seen) {
      assert.equal(
        seen.filter((candidate) => candidate === id).length,
        1,
        `row ${id} was returned more than once across the real-client walk`,
      );
    }
    assert.ok(seen.includes("retrieval-node-v1:seed-0006"), "last row never reached");
  });

  // red-proof: return 200 with an empty body for an unauthenticated request.
  // The adapter then reports kind:"unreadable" instead of "http-error" and
  // this fails — an unreadable body must never be mistaken for an empty set.
  test("an unauthenticated caller gets a transport error, never an empty page", async () => {
    const http = realHttpClient(baseUrl, null);
    const outcome = await fetchSynthesizedMemoryPage(http, { limit: 3 });

    assert.equal(outcome.kind, "http-error");
    assert.equal(outcome.status, 401);
    // The distinction that matters: this is the ABSENCE OF KNOWLEDGE, not a
    // complete empty snapshot. A wrong `complete:true` here is data loss via
    // Projection.reconcile.
    assert.equal(outcome.page, undefined);
  });

  test("the client and server agree on the route constant itself", () => {
    // Cheap, but it is the literal the client will request; if someone edits
    // the adapter's constant, the route test above is what catches the drift.
    assert.equal(PLATFORM_MEMORY_RECALL_PATH, "/v1/memories");
  });
});
