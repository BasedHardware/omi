/**
 * CROSS-SIDE WIRE AGREEMENT — THE TASKS READ SEAM
 * ===============================================
 *
 * The sibling of `wire-agreement.test.mjs`, for the wire
 * `DAVID-tasks-read-epoch-and-ci` D1/D2 ratified and this run built. Same
 * structural cure, same reason: each side's hermetic suite tests against its own
 * locally-authored idea of the other side's wire, so a disagreement about a
 * route, a parameter, an auth header, a status code, a field name or an encoding
 * is invisible to both. This test:
 *
 *   - imports the REAL client, `@omi-core/adapters-platform`, the exact module a
 *     surface calls, with no re-implementation of its request building or its
 *     parsing; and
 *   - drives it over REAL HTTP against the REAL registered app in a REAL
 *     separate process (`platform/integration/control/live-service.ts`, OPS's
 *     socket bind around `createLocalService`), booted as a child; and
 *   - seeds through the REAL write door, `POST /v1/tasks/ops`, after the REAL
 *     cut-over — never by poking a store.
 *
 * THE LAST POINT IS THE ONE THAT MAKES THIS WORTH RUNNING. The read serves out
 * of the same store the write door applies into. Seeding behind the routes would
 * prove the read agrees with this file's idea of the store; seeding through the
 * door proves the two doors agree with each other, which is the only question a
 * cross-side test is entitled to answer.
 *
 * ARBITERS (§5). Every claim below names a PRODUCER-SIDE counter and a
 * CONSUMER-SIDE observation, joined by the backend's own seed identity so the
 * two numbers are provably about the same process rather than merely correlated.
 * The producer-side number is `served.domainReadsServed` — the REGISTERED
 * route's own counter, which moves only after a domain response body exists.
 * Counting earlier is the wave-9 bug, where a served count moved while the
 * backend served nothing; no dispatch-side number appears in any verdict here.
 *
 * RED-PROOFS — applied by hand to real platform source, observed red, reverted,
 * through a lane-unique script that asserts both target worktrees (§3b):
 *
 *   XP1  serve the raw `record_id` as the public item id
 *        -> red. The storage-vocabulary sweep over the whole body catches it,
 *           not just the id-shape assertion.
 *   XP2  count the read as served BEFORE the response body exists
 *        -> BOTH arbiter tests red. This is the one worth having: it proves the
 *           producer/consumer pair is actually joined rather than decorative. A
 *           test that only read the consumer side would not have noticed the
 *           producer double-counting, and "servedCount=4 status=PASS while the
 *           backend served zero" is the incident this rule comes from.
 *
 * NOT YET RUN BY L2. `integration/lanes.mjs` names its cross-side step by
 * filename, and that file is STACK's under the charter's churn-magnet table, so
 * this lane did not edit it to add a second name. Until that one-line change
 * lands this file runs by hand only — stated here rather than left for someone
 * to discover, because a test nobody runs looks exactly like coverage. See
 * `data/run-2026-08-09/blocked/READ-l2-does-not-run-the-tasks-cross-side-test.md`.
 */

import { spawn } from "node:child_process";
import { once } from "node:events";
import assert from "node:assert/strict";
import { after, before, describe, test } from "node:test";

const { fetchPlatformTaskPage, walkPlatformTaskPages, PLATFORM_TASKS_READ_PATH } = await import(
  new URL("../../core/packages/adapters-platform/dist/index.js", import.meta.url).href
);
const { REPO_PATHS } = await import(new URL("../lib/provenance.mjs", import.meta.url).href);
const PLATFORM_REPO = REPO_PATHS.platform;
const BOOT_TIMEOUT_MS = 20_000;
const ACTIVE_EPOCH = 7;

let child;
let baseUrl;
let TOKEN;

/** A real HTTP binding, shaped like a shell's: base URL, bearer, raw body text. */
function realHttpClient(base, token = undefined) {
  token = token === undefined ? TOKEN : token;
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
      try { json = JSON.parse(text); } catch { json = null; }
      return { status: response.status, json, text };
    },
  };
}

const post = async (path, body) => {
  const response = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return { status: response.status, text: await response.text() };
};

/**
 * PRODUCER-SIDE counters, read from the app's own QA surface.
 *
 * `servedReads` is the registered route's own counter and moves only after
 * response bytes exist. `writeOpsApplied` is the write door's. Both are the
 * numbers the process states about itself, which is what makes them arbiters
 * rather than restatements of what this test already believes.
 */
const stats = async () => {
  const response = await fetch(`${baseUrl}/v1/qa/status`);
  const body = await response.json();
  return {
    // Verdict-grade: moves only after a domain response body exists.
    servedReads: body.served.domainReadsServed,
    // The seed identity doubles as the join key — it identifies the process
    // (and its fixture world) both numbers are about, so a backend that
    // restarted mid-test cannot have its counters compared across two lives.
    stamp: JSON.stringify(body.seed),
  };
};

/** ADR-010 §1's forward activation order, driven through the registered routes. */
const cutOver = async () => {
  const observation = (overrides) => ({
    control_revision: 1,
    account_generation: "legacy",
    account_epoch: null,
    lifecycle_state: "active",
    deletion_epoch: null,
    ...overrides,
  });
  await post("/v1/qa/control/observe", observation({}));
  await post("/v1/qa/control/observe", observation({ control_revision: 2, account_generation: "migrating" }));
  await post("/v1/qa/control/observe", observation({
    control_revision: 3, account_generation: "new", account_epoch: ACTIVE_EPOCH,
  }));
  const activated = await post("/v1/qa/control/activate", { epoch: ACTIVE_EPOCH, at_control_revision: 3 });
  assert.match(activated.text, /"activated":true/, `cut-over did not activate: ${activated.text}`);
};

const taskContent = (index) => ({
  description: `Cross-side task ${index}`,
  completed: index % 2 === 0,
  completedAt: index % 2 === 0 ? 1785990000 + index : null,
  dueAt: 1786000000 + index,
  owner: null,
  source: "assistant",
  provenance: ["assistant:summarizer-v3"],
  sortOrder: index + 0.5,
  indentLevel: 0,
  createdAt: 1785900000 + index,
  updatedAt: 1785950000 + index,
});

/** Applies `count` records through the real write door, asserting each landed. */
const seedTasks = async (count) => {
  await cutOver();
  for (let index = 0; index < count; index += 1) {
    const writeId = index.toString(16).padStart(64, "0");
    const applied = await post("/v1/tasks/ops", {
      write_id: writeId,
      account_epoch: ACTIVE_EPOCH,
      domain: "tasks",
      op: { op: "create", record_id: `task-cross-${index}`, content: taskContent(index) },
    });
    // A seeding helper that fails silently makes every assertion below it a
    // statement about an empty store. It asserts.
    assert.equal(applied.status, 200, `seed ${index} was not applied: ${applied.text}`);
  }
};

before(async () => {
  // Readiness comes from the CHILD, not from a port — see the sibling file's
  // hook and `blocked/READ-l2-cross-side-port-4853-...`. Port 0, and the URL
  // under test is the one the process under test printed about itself.
  // OPS's `integration/control/live-service.ts`: the REGISTERED app bound to an
  // ephemeral socket, printing one line of JSON. Reused rather than reinvented —
  // a second boot script naming these paths would be the second door rule 17
  // exists for, and this one already carries the ephemeral-port and
  // readiness-from-the-child discipline.
  child = spawn("bun", ["run", "integration/control/live-service.ts"], {
    cwd: PLATFORM_REPO,
    env: { ...process.env, TZ: "UTC" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });

  const deadline = Date.now() + BOOT_TIMEOUT_MS;
  while (Date.now() < deadline) {
    for (const line of stdout.split("\n")) {
      if (!line.includes("live_service_listening")) continue;
      try {
        const event = JSON.parse(line);
        if (event.event === "live_service_listening" && typeof event.url === "string") {
          baseUrl = event.url;
          TOKEN = event.devToken;
        }
      } catch { /* partial line */ }
    }
    if (baseUrl !== undefined) return;
    if (child.exitCode !== null) {
      throw new Error(`backend exited before readiness (status ${child.exitCode})\n`
        + `stdout: ${stdout.trim() || "(empty)"}\nstderr: ${stderr.trim() || "(empty)"}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(`backend never announced a listening port\nstderr: ${stderr.trim() || "(empty)"}`);
});

after(async () => {
  if (child && child.exitCode === null) {
    child.kill();
    await once(child, "exit");
  }
});

describe("the real tasks client against the real tasks server", () => {
  test("the ratified route agrees end to end, with both arbiters joined by process stamp", async () => {
    await seedTasks(3);
    const http = realHttpClient(baseUrl);

    // PRODUCER-SIDE, before. `stamp` is the join key: it identifies the process
    // both numbers are about, so a backend that restarted mid-test cannot have
    // its counters silently compared across two lives.
    const before = await stats();

    // CONSUMER-SIDE: the real client, parsing real bytes.
    const outcome = await fetchPlatformTaskPage(http, { limit: 10 });
    assert.equal(outcome.kind, "page", `real client could not read the real server: ${JSON.stringify(outcome)}`);

    // The STRONG boundary. If the server re-serialized, or the binding dropped
    // the raw text, the adapter silently falls back to the weaker object
    // predicate — which cannot see duplicate keys or a noncanonical encoding.
    assert.equal(outcome.boundary, "canonical-json-text");

    const after = await stats();
    assert.equal(after.stamp, before.stamp, "the backend restarted mid-test; the counters describe two processes");
    // Verdict-grade: the route's OWN counter, which moves only after response
    // bytes exist. The dispatch-side `servedRequests` is deliberately not used.
    assert.equal(after.servedReads - before.servedReads, 1,
      `producer says ${after.servedReads - before.servedReads} pages served, consumer parsed 1`);

    assert.equal(outcome.page.contractVersion, "1.0.0");
    assert.equal(outcome.page.items.length, 3);
    assert.equal(outcome.page.window.status, "complete");
    assert.equal(outcome.page.completeness.status, "complete");

    // PUBLIC ITEM IDS ARE READER-SCOPED OPAQUE REFS, NOT STORE RECORD IDS.
    // The memories sibling carries the scar: its assertion used to pin the raw
    // fixture row id and PASSED, because the door it drove minted public ids
    // straight from storage rows. This one asserts the property, never a literal.
    for (const item of outcome.page.items) {
      assert.match(item.id, /^task1_[a-f0-9]{64}$/, `public id is not an opaque tasks ref: ${item.id}`);
    }
    // And over the whole body, so a leak cannot hide in a cursor or a frontier.
    const raw = JSON.stringify(outcome.page);
    for (const storageVocabulary of ["task-cross-", "record_id", "first_seen_seq", "last_applied_seq"]) {
      assert.ok(!raw.includes(storageVocabulary), `storage vocabulary on the wire: ${storageVocabulary}`);
    }

    // ALL THIRTEEN, carried verbatim from what the write door applied (D2).
    const sorted = [...outcome.page.items].sort((left, right) => left.sortOrder - right.sortOrder);
    assert.deepEqual(
      Object.keys(sorted[0]).sort(),
      ["completed", "completedAt", "createdAt", "description", "dueAt", "id",
        "indentLevel", "owner", "provenance", "revision", "sortOrder", "source", "updatedAt"],
    );
    assert.equal(sorted[0].description, "Cross-side task 0");
    assert.equal(sorted[0].sortOrder, 0.5);
    assert.match(sorted[0].revision, /^[0-9a-f]{64}$/);
  });

  test("the keyset walk terminates and loses no row", async () => {
    await post("/v1/qa/control/reset", {});
    await seedTasks(5);
    const http = realHttpClient(baseUrl);

    const before = await stats();
    // limit=1 forces four continuations, so the cursor is exercised against the
    // real signing keyset rather than asserted about.
    const walk = await walkPlatformTaskPages(http, { limit: 1 });
    const after = await stats();

    assert.ok(walk, "the walk could not be completed honestly");
    assert.equal(after.stamp, before.stamp);
    // Producer and consumer agree on how many pages crossed the wire.
    assert.equal(after.servedReads - before.servedReads, walk.pages,
      `producer served ${after.servedReads - before.servedReads} pages, consumer walked ${walk.pages}`);
    assert.equal(walk.pages, 5);
    assert.equal(walk.items.length, 5);
    assert.equal(walk.wholeSet, true, "every page was complete and the walk ended complete-terminal");
    assert.equal(new Set(walk.items.map((task) => task.id)).size, 5, "the keyset guarantee was broken");
  });

  test("an unauthenticated caller gets a transport error, never an empty page", async () => {
    // The failure this forbids is a client concluding "you have no tasks" from a
    // refusal — which, on a reconciling client, licenses deleting local rows.
    const http = realHttpClient(baseUrl, null);
    const outcome = await fetchPlatformTaskPage(http, { limit: 3 });
    assert.equal(outcome.kind, "http-error");
    assert.equal(outcome.status, 401);
  });

  test("the client and the server agree on the route constant itself", async () => {
    // The entitlement-frame collision in its smallest form: both sides holding a
    // path string that has drifted apart. The client's constant is asserted
    // against a live probe of the server rather than against a copy of the
    // server's constant.
    assert.equal(PLATFORM_TASKS_READ_PATH, "/v1/tasks");
    const served = await fetch(`${baseUrl}${PLATFORM_TASKS_READ_PATH}`, {
      headers: { authorization: `Bearer ${TOKEN}` },
    });
    assert.equal(served.status, 200);
    const unknown = await fetch(`${baseUrl}${PLATFORM_TASKS_READ_PATH}/`, {
      headers: { authorization: `Bearer ${TOKEN}` },
    });
    assert.equal(unknown.status, 404, "trailing-slash strictness did not survive the real binding");
  });
});
