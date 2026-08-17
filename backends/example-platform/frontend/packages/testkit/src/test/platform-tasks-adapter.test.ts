/**
 * The client half of the ratified TASKS READ seam, executed against the SAME
 * corpus of record the backend runs — rule 15's declared consumer for the
 * `ratified-tasks-read` seam.
 *
 * Two layers, and the second is the one that matters:
 *
 *  1. CORPUS CONFORMANCE — every row of `tasks-read-conformance.json`, driven
 *     through the adapter's real parse path. These prove the adapter agrees
 *     with the contract about what is honest. Exhaustive by construction (a new
 *     corpus row is automatically executed) and asserted non-empty, so a loader
 *     regression cannot make the suite vacuously green.
 *
 *  2. INVARIANT TESTS — the data-loss laws, each with an applied red-proof
 *     (hard rule 14). The corpus cannot express these: it describes single
 *     pages, and the data-loss path is a MULTI-PAGE walk that ends on an honest
 *     page.
 *
 * Hermetic: scripted responses only, no network, no clock, no randomness.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import type { HttpClient, HttpResponse } from "@omi-core/contracts";
import {
  PLATFORM_TASKS_MAX_LIMIT,
  PLATFORM_TASKS_READ_PATH,
  fetchPlatformTaskIdSnapshot,
  parsePlatformTaskPageResponse,
  platformTaskCoverageFromPage,
  platformTaskItemsFromPage,
  walkPlatformTaskPages,
} from "@omi-core/adapters-platform";
import { readRatifiedCorpus, readRatifiedTasksReadShape } from "../ratified-fixtures.js";

interface TasksCorpusRow {
  readonly wireCase: string;
  readonly label: string;
  readonly safe: boolean;
  readonly page: unknown;
}

const corpus = (): readonly TasksCorpusRow[] =>
  readRatifiedCorpus("tasks-read-conformance") as readonly TasksCorpusRow[];

/** Answers each request from a queue; extra requests are a test failure. */
class ScriptedPages implements HttpClient {
  readonly paths: string[] = [];
  constructor(private readonly queue: HttpResponse[]) {}
  async request(_method: string, path: string): Promise<HttpResponse> {
    this.paths.push(path);
    const next = this.queue.shift();
    if (!next) throw new Error(`unscripted request: ${path}`);
    return next;
  }
}

/** Answers every request with the same body — the non-terminating server. */
class RepeatingPage implements HttpClient {
  requests = 0;
  constructor(private readonly body: unknown) {}
  async request(): Promise<HttpResponse> {
    this.requests += 1;
    return okPage(this.body);
  }
}

const okPage = (page: unknown): HttpResponse => ({
  status: 200,
  json: page,
  text: JSON.stringify(page),
});

const rowFor = (wireCase: string): TasksCorpusRow => {
  const found = corpus().find((row) => row.wireCase === wireCase);
  assert.ok(found, `corpus row ${wireCase} is missing — the corpus changed shape`);
  return found;
};

const pageFor = (wireCase: string): Record<string, unknown> =>
  structuredClone(rowFor(wireCase).page) as Record<string, unknown>;

// ── 1. corpus conformance ───────────────────────────────────────────────────

test("every tasks corpus row is judged identically by the client adapter", () => {
  const rows = corpus();
  assert.ok(rows.length >= 30, "the tasks corpus is empty or truncated — that must never read as a pass");
  for (const row of rows) {
    // The authoritative boundary: the contract is defined over the BYTES.
    const overText = parsePlatformTaskPageResponse(okPage(row.page));
    assert.equal(overText.kind === "page", row.safe, `${row.wireCase} over raw text`);
    if (overText.kind === "page") assert.equal(overText.boundary, "canonical-json-text");

    // And the weaker one, which is what a transport that exposes no raw body
    // leaves us. Both must reach the same verdict on every row, or a client's
    // safety would depend on which transport happened to be bound.
    const overJson = parsePlatformTaskPageResponse({ status: 200, json: structuredClone(row.page) });
    assert.equal(overJson.kind === "page", row.safe, `${row.wireCase} over parsed json`);
    if (overJson.kind === "page") assert.equal(overJson.boundary, "trusted-parsed-json");
  }
});

test("the corpus covers every case and every refusal law the schema of record declares", () => {
  const shape = readRatifiedTasksReadShape();
  const covered = new Set(corpus().map((row) => row.wireCase));
  assert.ok(shape.cases.length > 0 && shape.refusalLaws.length > 0, "an empty schema of record proves nothing");
  for (const { case: declared } of [...shape.cases, ...shape.refusalLaws]) {
    assert.ok(covered.has(declared), `${declared} is declared but has no corpus row`);
  }
  assert.equal(shape.route, PLATFORM_TASKS_READ_PATH, "the adapter and the schema of record disagree about the route");
});

test("all thirteen fields survive the projection onto the surface type", () => {
  // D2's parity, checked at the CLIENT boundary. The adapter copies field by
  // field rather than spreading, so this is where a dropped copy shows up.
  //
  // RED-PROOF, and the first attempt failed in an informative way. Deleting
  // `revision: item.revision,` alone does NOT reach this test — TypeScript
  // refuses it at compile time, because `PlatformTaskItem` declares all
  // thirteen as required. That is a stronger guard than an assertion and it is
  // worth saying so rather than claiming a red this test never showed.
  //
  // What this test independently pins is the half the compiler has never seen:
  // that the surface type agrees with the SCHEMA OF RECORD shipped in the
  // tarball. The mutation that reaches it is the realistic regression — someone
  // narrows the surface — so `revision` was dropped from `PlatformTaskItem` AND
  // from the projection together. APPLIED AS A PAIR AND OBSERVED RED (this test
  // and the nullable-fields test below).
  const shape = readRatifiedTasksReadShape();
  const outcome = parsePlatformTaskPageResponse(okPage(pageFor("item:full_field_parity")));
  assert.equal(outcome.kind, "page");
  if (outcome.kind !== "page") return;
  const [task] = platformTaskItemsFromPage(outcome.page);
  assert.ok(task);
  assert.deepEqual(Object.keys(task).sort(), [...shape.itemFields].sort());
  for (const field of shape.itemFields) {
    assert.ok(field in task, `the surface item lost \`${field}\` — D2 requires full parity`);
  }
});

test("nullable fields stay present and null, never absent", () => {
  // "Absent" and "null" are different values under exactOptionalPropertyTypes,
  // and only one of them is a claim. A surface must not be able to tell "the
  // server sent no due date" from "the key was dropped in transit".
  const outcome = parsePlatformTaskPageResponse(okPage(pageFor("item:nullable_fields_null")));
  assert.equal(outcome.kind, "page");
  if (outcome.kind !== "page") return;
  const [task] = platformTaskItemsFromPage(outcome.page);
  assert.ok(task);
  for (const field of ["completedAt", "dueAt", "owner", "revision"] as const) {
    assert.ok(field in task, `${field} must be present`);
    assert.equal(task[field], null);
  }
});

// ── 2. invariant tests, each with an applied red-proof ──────────────────────

test("coverage is CARRIED from the server, never derived from the page", () => {
  // The expensive mistake would be inferring completeness from `items.length`
  // or from the window. The window describes THIS PAGE's pagination; coverage
  // describes how much of the account's task set the server actually served.
  //
  // red-proof: make platformTaskCoverageFromPage return
  // `complete: page.window.complete` -> red here. APPLIED AND OBSERVED RED.
  const outcome = parsePlatformTaskPageResponse(okPage(pageFor("completeness:incomplete")));
  assert.equal(outcome.kind, "page");
  if (outcome.kind !== "page") return;
  const coverage = platformTaskCoverageFromPage(outcome.page);
  assert.equal(coverage.kind, "known");
  if (coverage.kind !== "known") return;
  // A TERMINAL window whose coverage is incomplete: the pair the inference gets
  // wrong. `hasMore` is false and `complete` must still be false.
  assert.equal(coverage.hasMore, false);
  assert.equal(coverage.complete, false);
  assert.equal(coverage.status, "incomplete");
  assert.deepEqual([...coverage.reasons], ["pending_writes"]);
});

test("a walk that ends complete-terminal but passed through a lagging page is NOT the whole set", () => {
  // This is the data-loss law, and it is worse for tasks than for memories:
  // `wholeSet` is what licenses deleting local rows, and `pending_writes` means
  // an op the user just made and the SERVER ALREADY ACCEPTED is missing from
  // the projection. ANDing only the windows would delete it.
  //
  // red-proof: change `wholeSet` to `window.status === "complete"` (dropping
  // everyPageComplete) -> red here. APPLIED AND OBSERVED RED.
  const laggingFirst = pageFor("window:incomplete_continuation");
  const honestLast = pageFor("window:complete_terminal");
  // Distinct ids, or the duplicate-id law fires first and this test would pass
  // for the wrong reason.
  setFirstItemId(honestLast, `task1_${"d".repeat(64)}`);
  const http = new ScriptedPages([okPage(laggingFirst), okPage(honestLast)]);
  return walkPlatformTaskPages(http).then((walk) => {
    assert.ok(walk, "both pages are individually honest, so the walk must complete");
    assert.equal(walk.pages, 2);
    assert.equal(walk.wholeSet, false, "one lagging page anywhere means the union is not the set");
    // And the last page's own coverage is still reported honestly as complete —
    // the two claims are separate, which is the point.
    assert.equal(walk.coverage.kind === "known" && walk.coverage.complete, true);
  });
});

test("a repeated item id across pages makes the whole walk unknowable", () => {
  // The cursor-reset bug: an unrecognized cursor decoding to "start from the
  // beginning". `wholeSet: false` is not a sufficient answer — once ordering is
  // violated the set semantics of the entire walk are unreliable.
  //
  // red-proof: replace `return null` in the duplicate-id branch with
  // `continue`-equivalent (drop the check) -> red here.
  // APPLIED AND OBSERVED RED.
  const first = pageFor("window:more_continuation");
  const second = pageFor("window:complete_terminal");
  const http = new ScriptedPages([okPage(first), okPage(second)]);
  return walkPlatformTaskPages(http).then((walk) => {
    assert.equal(walk, null, "a duplicate id must produce no answer at all");
  });
});

test("a server that never terminates is bounded, and never claims the set", () => {
  // NO RED-PROOF IS CLAIMED FOR THE BOUND ITSELF, deliberately: the mutation
  // that would test it (an unbounded loop) makes this test HANG rather than
  // fail, and a hang is not a red. What was measured instead: with the
  // duplicate-id law removed (CP4) this test still answered `null`, because the
  // repeated-CURSOR law catches the same server independently. Two laws, each
  // sufficient, and that is recorded here rather than presented as one
  // assertion doing the work.
  const repeating = new RepeatingPage(pageFor("window:more_continuation"));
  return walkPlatformTaskPages(repeating, { maxPages: 3 }).then((walk) => {
    // The duplicate-id law fires on page two here, which is the stronger
    // answer: we learn nothing rather than learning a bounded prefix.
    assert.equal(walk, null);
    assert.ok(repeating.requests <= 3, "the walk must not outrun its page bound");
  });
});

test("an unreadable or non-200 page anywhere aborts the walk rather than truncating it", () => {
  // A truncated walk that still terminated would look exactly like a complete
  // one. `null`, not a short answer.
  //
  // red-proof: make the `outcome.kind !== "page"` branch `break` instead of
  // `return null` -> red here. APPLIED AND OBSERVED RED.
  const http = new ScriptedPages([okPage(pageFor("window:more_continuation")), { status: 503, json: null }]);
  return walkPlatformTaskPages(http).then((walk) => {
    assert.equal(walk, null);
  });
});

test("an id snapshot is null, never empty-and-complete, when the walk is not honest", () => {
  // A `complete: true` empty snapshot would delete every local task.
  //
  // red-proof: return `{ setVersion, complete: false, ids: [] }` instead of
  // null when the walk fails -> red here. APPLIED AND OBSERVED RED.
  const http = new ScriptedPages([{ status: 500, json: null }]);
  return fetchPlatformTaskIdSnapshot(http).then((snapshot) => {
    assert.equal(snapshot, null);
  });
});

test("an honest empty account yields a complete, empty snapshot", () => {
  // The other direction, so the test above cannot be satisfied by always
  // answering null.
  const http = new ScriptedPages([okPage(pageFor("absence:query_gap"))]);
  return fetchPlatformTaskIdSnapshot(http).then((snapshot) => {
    assert.ok(snapshot);
    assert.equal(snapshot.complete, true);
    assert.deepEqual(snapshot.ids, []);
  });
});

test("the adapter asks for a limit the server will actually honor", () => {
  // Asking beyond the server's ceiling is silently CLAMPED there, which would
  // make "did the walk terminate" depend on a clamp we cannot observe.
  const http = new ScriptedPages([okPage(pageFor("window:complete_terminal"))]);
  return walkPlatformTaskPages(http, { limit: 10_000 }).then(() => {
    assert.equal(http.paths.length, 1);
    assert.match(http.paths[0]!, new RegExp(`^\\${PLATFORM_TASKS_READ_PATH}\\?limit=${PLATFORM_TASKS_MAX_LIMIT}$`));
  });
});

function setFirstItemId(page: Record<string, unknown>, id: string): void {
  const items = page["items"] as { id: string }[];
  const first = items[0];
  assert.ok(first, "corpus page has no item to renumber");
  first.id = id;
}
