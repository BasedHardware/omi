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

// NOT `new URL("../../../platform/", import.meta.url)`. That arithmetic is true
// of the checkout at `<workspace>/core-foundation` and false of every lane
// worktree, where it resolved to a `platform/` that does not exist — and a
// missing `cwd` makes `spawn` report ENOENT against the COMMAND, so this failed
// as `spawn bun ENOENT` and read like a broken toolchain. `provenance.mjs` owns
// repo resolution for exactly this reason; ask it.
const { REPO_PATHS } = await import(new URL("../lib/provenance.mjs", import.meta.url).href);
const PLATFORM_REPO = REPO_PATHS.platform;
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

/**
 * READINESS COMES FROM THE CHILD, NOT FROM A PORT.
 *
 * This hook used to pin port 4853 with the comment "harness-local; avoids the
 * registry's fixed allocations" and then wait for `GET /health` on that port to
 * answer 200. Both halves were wrong, and together they produced the exact
 * defect class this whole test exists to catch.
 *
 *   - 4853 is NOT unallocated. It is `platform/integration/control/
 *     fence-server.ts`'s `DEFAULT_PORT`.
 *   - The probe asked a URL, not the child. So when the spawn could not bind,
 *     the probe reached WHOEVER ELSE held 4853, got a 200, and declared "the
 *     backend is ready". Every assertion afterwards measured a foreign process.
 *
 * Observed live during the wave-3 run: an orphaned fence server (PPID 1) held
 * 4853, answered `/health` with `{"status":"ok"}` and 404'd everything else, and
 * this suite reported three failures about a diff that was green — including
 * "unauthenticated caller: expected 401, actual 404", which is a 404 from a
 * server that never had the route. That was the lucky direction. A squatter
 * that answered plausibly would have produced a false GREEN in L2, the gate the
 * entire integration loop rests on.
 * (`data/run-2026-08-09/blocked/READ-l2-cross-side-port-4853-collides-with-fence-server.md`)
 *
 * So the port is now OS-ASSIGNED (`OMI_INTEGRATION_PORT=0`) and the readiness
 * signal is the child's OWN `integration_backend_listening` line on its stdout,
 * which reports `server.port` — the port it actually bound. There is no port to
 * collide with and no way to be handed somebody else's process: the URL under
 * test is the one the process under test printed about itself.
 *
 * The failure paths are loud on purpose. A child that dies during boot fails
 * with its captured stderr instead of a bare status, because "backend exited
 * before readiness (status 1)" is what sent someone to read a toolchain.
 */
before(async () => {
  child = spawn("bun", ["run", "integration/server/serve.ts"], {
    cwd: PLATFORM_REPO,
    // Port 0 asks the OS for a free port. Nothing here may pin one: this suite
    // shares a machine with every other lane, and a pinned port is a shared
    // mutable resource with no owner.
    env: { ...process.env, TZ: "UTC", OMI_INTEGRATION_PORT: "0" },
    stdio: ["ignore", "pipe", "pipe"],
  });

  let stdout = "";
  let stderr = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });

  const readListeningUrl = () => {
    for (const line of stdout.split("\n")) {
      if (!line.includes("integration_backend_listening")) continue;
      try {
        const event = JSON.parse(line);
        if (event.event === "integration_backend_listening" && typeof event.url === "string") {
          return event.url;
        }
      } catch {
        // A partial line; the next chunk completes it.
      }
    }
    return null;
  };

  const deadline = Date.now() + BOOT_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const url = readListeningUrl();
    if (url !== null) {
      baseUrl = url;
      return;
    }
    if (child.exitCode !== null) {
      throw new Error(
        `backend exited before readiness (status ${child.exitCode})\n`
        + `stdout: ${stdout.trim() || "(empty)"}\nstderr: ${stderr.trim() || "(empty)"}`,
      );
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(
    `backend never announced a listening port within ${BOOT_TIMEOUT_MS}ms\n`
    + `stdout: ${stdout.trim() || "(empty)"}\nstderr: ${stderr.trim() || "(empty)"}`,
  );
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
    assert.equal(outcome.page.window.status, "more");
    assert.equal(typeof outcome.page.window.nextCursor, "string");

    // PUBLIC ITEM IDS ARE READER-SCOPED OPAQUE REFS, NOT FIXTURE ROW IDS.
    //
    // This used to assert `items[0].id === "retrieval-node-v1:seed-0000"` — the
    // raw fixture row id — and it PASSED, because the backend it drove was the
    // third, hand-rolled read door that minted public ids straight from storage
    // rows. That is the exact defect class the wave-1 read-door collapse was
    // built to kill, and it was live on the port `make stack` boots. The W4
    // ruling retired that door; the assertion moves with it, from a literal
    // that pinned the leak to the property that forbids it.
    //
    // red-proof: in the platform repo's apps/service/composition/memory-read.ts,
    // make `encodeItemRef` return
    // `retrieval-node-v1:${codecs.encodeItemRef(ref).slice(5, 13)}` — the
    // retired door's id grammar, wrapped around the real codec so nothing else
    // changes. APPLIED against this test driving the real backend: `# fail 2`,
    // this test on the opaque-ref match and the walk test alongside it.
    // Restored; green.
    //
    // Did NOT go red, recorded as evidence: returning `ref.node_id` from
    // `encodeItemRef`. The port receives no `node_id` field, so it fell
    // through to the codec and changed nothing — a mutation that silently
    // no-ops is not a red-proof.
    for (const item of outcome.page.items) {
      assert.match(
        item.id,
        /^mem1_[0-9a-f]{64}$/,
        `public item id is not a reader-scoped opaque ref: ${item.id}`,
      );
      // Storage vocabulary must not reach the wire under ANY spelling.
      for (const internal of ["claim:qa:", "entity:qa:", "commit:qa:", "retrieval-node-v1:"]) {
        assert.ok(
          !item.id.includes(internal),
          `public item id carries storage vocabulary "${internal}": ${item.id}`,
        );
      }
    }
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
    // The whole seeded corpus, not a named last row: with reader-scoped opaque
    // ids there is no stable public name for "the last one", and counting the
    // walk is the assertion that actually catches a truncated page chain.
    assert.equal(seen.length, 7, `walk covered ${seen.length} of 7 seeded memories`);
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
