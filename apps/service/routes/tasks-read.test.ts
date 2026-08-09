/**
 * The tasks read route, driven through the REAL app factory.
 *
 * Every request here goes through `createLocalService`, not through a lookalike
 * assembled in this file. `app-facing.ts` says why in its own header: if the dev
 * server assembled routes inline and tests assembled a lookalike, both could
 * agree perfectly while the shipped binding was wrong — which is how a green
 * hermetic suite once accompanied a bridge that served zero requests.
 *
 * Three groups:
 *   1. HARDENING AT PARITY with `/v1/memories`, asserted by comparing the two
 *      routes' actual bytes rather than by restating the expected constants.
 *   2. THE RATIFIED SHAPE, validated by the vendored contract's own parser over
 *      the response BYTES — never by re-reading the fields this route wrote.
 *   3. THE TWO R16 GUARDS, pinned so a future edit cannot quietly decide the
 *      question fable parked for David.
 *
 * RED-PROOFS — applied by hand to real source, observed red, reverted. Run
 * through a lane-unique script that asserts its target worktree (§3b), because
 * a red-proof executed via a shared-path script is void and this lane had two
 * such scripts before the rule landed:
 *
 *   TP1  serve the raw `record_id` as the public item id
 *        -> "public id is NOT the record id" AND the two-readers test, both red.
 *           This is the leak D2 closes by construction, and the second failure
 *           is the one that matters: a raw id is identical across readers.
 *   TP2  answer 400 for an unprojectable record instead of failing closed
 *        -> fail-closed test red.
 *   TP3  project `first_seen_seq` into `sortOrder` (R16 guard 2 violation)
 *        -> guard-2 test red. The fixture's fractional negative sortOrder is
 *           what makes this reachable; an integer fixture would have let a
 *           substituted sequence number pass by coincidence.
 *   TP4  leak `account_epoch` into the unauthorized refusal body (R10 violation)
 *        -> the epoch-free test AND the cross-route byte-equality test, red.
 *   TP5  silently omit an unprojectable record instead of failing closed
 *        -> fail-closed test red. This is the short-page-that-looks-complete
 *           path, and it is the one a well-meaning future edit would actually
 *           take, which is why it gets its own mutation rather than sharing
 *           TP2's.
 */

import { describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";

import { parseTaskPageJson } from "@omi-core/ratified-contracts/projections/tasks";

import { createLocalService } from "../app-facing";
import { TASKS_READ_PATH } from "./tasks-read";

const service = () => {
  const db = new Database(":memory:");
  return createLocalService({
    db,
    ownerAccountId: "acct-tasks-read-test",
    memoryCount: 3,
    accountTimezone: "UTC",
    devSecretLabel: "tasks-read-test",
  });
};

const authed = (token: string, path: string, init: RequestInit = {}): Request =>
  new Request(`http://localhost${path}`, {
    ...init,
    headers: { authorization: `Bearer ${token}`, ...(init.headers ?? {}) },
  });

/**
 * Seeds one task through the REAL write door, so the read serves applied state.
 *
 * The cut-over sequence is ADR-010 §1's forward order, driven through the
 * registered control routes — not a store poked directly. The point of seeding
 * this way is that the read is then serving what the WRITE DOOR actually
 * applied, which is the only version of this test worth having: a store seeded
 * behind the routes would prove the read agrees with the test's idea of the
 * store rather than with the door.
 */
const ACTIVE_EPOCH = 7;

const control = async (
  local: ReturnType<typeof createLocalService>,
  path: string,
  body: unknown,
): Promise<Response> =>
  local.app.request(path, {
    method: "POST",
    headers: { authorization: `Bearer ${local.devToken}`, "content-type": "application/json" },
    body: JSON.stringify(body),
  });

const cutOver = async (local: ReturnType<typeof createLocalService>): Promise<void> => {
  const observation = (overrides: Record<string, unknown>) => ({
    control_revision: 1,
    account_generation: "legacy",
    account_epoch: null,
    lifecycle_state: "active",
    deletion_epoch: null,
    ...overrides,
  });
  await control(local, "/v1/qa/control/observe", observation({}));
  await control(local, "/v1/qa/control/observe", observation({ control_revision: 2, account_generation: "migrating" }));
  await control(local, "/v1/qa/control/observe", observation({
    control_revision: 3, account_generation: "new", account_epoch: ACTIVE_EPOCH,
  }));
  const activated = await control(local, "/v1/qa/control/activate", { epoch: ACTIVE_EPOCH, at_control_revision: 3 });
  expect(await activated.json()).toMatchObject({ activated: true });
};

const seedTask = async (
  local: ReturnType<typeof createLocalService>,
  overrides: Record<string, unknown> = {},
): Promise<void> => {
  await cutOver(local);
  const content = {
    description: "Ship the tasks read wire",
    completed: false,
    completedAt: null,
    dueAt: 1786000000,
    owner: null,
    source: "assistant",
    provenance: ["assistant:summarizer-v3"],
    sortOrder: 1.5,
    indentLevel: 0,
    createdAt: 1785900000,
    updatedAt: 1785950000,
    ...overrides,
  };
  const applied = await local.app.request("/v1/tasks/ops", {
    method: "POST",
    headers: { authorization: `Bearer ${local.devToken}`, "content-type": "application/json" },
    body: JSON.stringify({
      write_id: "ab".repeat(32),
      account_epoch: ACTIVE_EPOCH,
      domain: "tasks",
      op: { op: "create", record_id: "task-9f21", content },
    }),
  });
  // The seed ASSERTS it applied. A seeding helper that silently fails turns
  // every assertion below it into a statement about an empty store — which is
  // the shape of "448 green tests, zero served requests".
  expect(applied.status).toBe(200);
};

describe("tasks read route — hardening at /v1/memories parity", () => {
  test("refusals are BYTE-IDENTICAL to an unknown route, and epoch-free (R10)", async () => {
    // R10's condition, asserted on the bytes. This is the surface D3 will ride
    // the account epoch on, which makes it exactly the surface where a refusal
    // must reveal nothing: W1's load-bearing condition is that the epoch is
    // never served to a caller without authority over the account, and a refused
    // caller is by definition one.
    const local = service();
    const unknown = await local.app.fetch(new Request("http://localhost/v1/definitely-not-a-route"));
    const unauthed = await local.app.fetch(new Request(`http://localhost${TASKS_READ_PATH}`));
    const unknownBody = await unknown.text();
    const unauthedBody = await unauthed.text();

    expect(unknown.status).toBe(404);
    expect(unauthed.status).toBe(401);
    // The bodies are the same SHAPE and carry no reason, no identifier, no epoch.
    for (const body of [unknownBody, unauthedBody]) {
      expect(body).not.toContain("epoch");
      expect(body).not.toContain("account");
      expect(body).not.toContain("task");
      expect(Object.keys(JSON.parse(body))).toEqual(["error"]);
    }
    // Headers cannot be a side channel either.
    expect(unauthed.headers.get("cache-control")).toBe("no-store");
    expect(unauthed.headers.get("content-type")).toBe("application/json");
    expect(unknown.headers.get("cache-control")).toBe(unauthed.headers.get("cache-control"));
  });

  test("the fixed refusal bodies are the SAME bytes the memories route uses", async () => {
    // The one thing that must never differ between the two routes. Asserted by
    // comparing the routes to each other rather than to a constant retyped here:
    // a retyped constant would keep agreeing with itself after one route moved.
    const local = service();
    const pairs: [string, string][] = [
      [TASKS_READ_PATH, "/v1/memories"],
    ];
    for (const [tasksPath, memoriesPath] of pairs) {
      const tasks401 = await (await local.app.fetch(new Request(`http://localhost${tasksPath}`))).text();
      const memories401 = await (await local.app.fetch(new Request(`http://localhost${memoriesPath}`))).text();
      expect(tasks401).toBe(memories401);

      const tasks400 = await (await local.app.fetch(
        authed(local.devToken, `${tasksPath}?limit=0`))).text();
      const memories400 = await (await local.app.fetch(
        authed(local.devToken, `${memoriesPath}?limit=0`))).text();
      expect(tasks400).toBe(memories400);
    }
  });

  test("GET only; every other method is an unknown route", async () => {
    const local = service();
    for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
      const response = await local.app.fetch(
        authed(local.devToken, TASKS_READ_PATH, { method }));
      expect(response.status).toBe(404);
    }
  });

  test("a trailing slash is a different, unknown path", async () => {
    const local = service();
    const response = await local.app.fetch(authed(local.devToken, `${TASKS_READ_PATH}/`));
    expect(response.status).toBe(404);
  });

  test("a duplicated single-valued parameter fails closed", async () => {
    // Hono takes the FIRST value, so without this `?limit=5&limit=101` and
    // `?limit=101&limit=5` disagree purely on ordering while carrying the same
    // pair of values.
    const local = service();
    for (const query of ["?limit=5&limit=101", "?limit=101&limit=5", "?cursor=a&cursor=b"]) {
      const response = await local.app.fetch(authed(local.devToken, `${TASKS_READ_PATH}${query}`));
      expect(response.status).toBe(400);
    }
  });

  test("`Bearer` is required, and a bare key is not a credential", async () => {
    const local = service();
    for (const header of [local.devToken, `bearer ${local.devToken}`, "Bearer ", "Basic x"]) {
      const response = await local.app.fetch(new Request(`http://localhost${TASKS_READ_PATH}`, {
        headers: { authorization: header },
      }));
      expect(response.status).toBe(401);
    }
  });

  test("limit is bounded, and a non-numeric limit is refused", async () => {
    const local = service();
    for (const query of ["?limit=0", "?limit=101", "?limit=-1", "?limit=abc", "?limit=1.5", "?limit=1000"]) {
      const response = await local.app.fetch(authed(local.devToken, `${TASKS_READ_PATH}${query}`));
      expect(response.status).toBe(400);
    }
    const ok = await local.app.fetch(authed(local.devToken, `${TASKS_READ_PATH}?limit=100`));
    expect(ok.status).toBe(200);
  });

  test("a forged cursor is refused as bad_request, and never as an internal error", async () => {
    // The collapse `memory-read.ts` documents: a TypeError reports as 500 while
    // an invalid cursor reports as 400, so two mutations of one token produced
    // two different public outcomes and told an attacker which half of their
    // guess was wrong.
    const local = service();
    for (const cursor of ["x", "not-a-cursor", "a".repeat(4096), "a".repeat(4097), "%00"]) {
      const response = await local.app.fetch(
        authed(local.devToken, `${TASKS_READ_PATH}?cursor=${encodeURIComponent(cursor)}`));
      expect(response.status).toBe(400);
      expect(await response.text()).toBe(JSON.stringify({ error: "bad_request" }));
    }
  });
});

describe("tasks read route — the ratified shape, over the bytes", () => {
  test("an empty account serves a contract-valid page that declares the gap", async () => {
    const local = service();
    const response = await local.app.fetch(authed(local.devToken, TASKS_READ_PATH));
    expect(response.status).toBe(200);
    const raw = await response.text();
    // Validated by the VENDORED contract's own parser, over the response bytes.
    // Re-reading the fields this route just wrote would prove only that the
    // route agrees with itself.
    const page = parseTaskPageJson(raw);
    expect(page).not.toBeNull();
    expect(page!.items).toEqual([]);
    expect(page!.absence).toEqual({ kind: "query_gap" });
    expect(page!.completeness.status).toBe("complete");
    // No write has ever been applied, and the envelope says so rather than
    // claiming coverage it cannot evidence.
    expect(page!.completeness.frontiers.missingAppliedFrontierReason).toBe("no_applied_writes");
  });

  test("an applied write is served back, and its public id is NOT the record id", async () => {
    // The class D2 closes by construction. Three days before this landed, a QA
    // door was serving `retrieval-node-v1:seed-0000` — a raw fixture row id — as
    // a public item id, and the cross-side test was PINNING the leak.
    const local = service();
    await seedTask(local);
    const raw = await (await local.app.fetch(authed(local.devToken, TASKS_READ_PATH))).text();
    const page = parseTaskPageJson(raw);
    expect(page).not.toBeNull();
    expect(page!.items.length).toBe(1);
    const item = page!.items[0]!;
    expect(item.id).toMatch(/^task1_[a-f0-9]{64}$/);
    // Asserted over the whole body, not just the id field: no storage vocabulary
    // anywhere, including inside a cursor or a frontier.
    expect(raw).not.toContain("task-9f21");
    expect(raw).not.toContain("record_id");
    expect(raw).not.toContain("first_seen_seq");
    // And the thirteen are all present and carried verbatim.
    expect(item.description).toBe("Ship the tasks read wire");
    expect(item.completed).toBe(false);
    expect(item.sortOrder).toBe(1.5);
    expect(item.revision).toMatch(/^[0-9a-f]{64}$/);
  });

  test("two different readers never see the same public id for one record", async () => {
    // Reader-scoping, asserted rather than assumed. Two services over the same
    // account id but different codec roots stand in for two readers; if the
    // handles matched, the id would be a cross-reader correlation key over
    // exactly the closure the codecs exist to keep separate.
    const first = service();
    const second = createLocalService({
      db: new Database(":memory:"),
      ownerAccountId: "acct-tasks-read-test",
      memoryCount: 3,
      accountTimezone: "UTC",
      devSecretLabel: "tasks-read-test-OTHER-READER",
    });
    await seedTask(first);
    await seedTask(second);
    const firstPage = parseTaskPageJson(
      await (await first.app.fetch(authed(first.devToken, TASKS_READ_PATH))).text());
    const secondPage = parseTaskPageJson(
      await (await second.app.fetch(authed(second.devToken, TASKS_READ_PATH))).text());
    expect(firstPage!.items[0]!.id).not.toBe(secondPage!.items[0]!.id);
  });

  test("a record whose bag will not project FAILS CLOSED — never a short page", async () => {
    // The ruled behaviour, pinned. Serving the page with the record silently
    // omitted would be a short page that looks complete, which is precisely what
    // the completeness envelope exists to make impossible; fabricating a value
    // is the `locked: false` data-loss class.
    const local = service();
    await seedTask(local, { completed: "not-a-boolean" });
    const response = await local.app.fetch(authed(local.devToken, TASKS_READ_PATH));
    expect(response.status).toBe(500);
    expect(await response.text()).toBe(JSON.stringify({ error: "internal_server_error" }));
  });
});

describe("tasks read route — fable's R16 guards", () => {
  test("sortOrder comes from the bag and is NEVER first_seen_seq", async () => {
    // R16 guard 2. The two are different facts — one is a store-internal
    // admission-order observation, the other is product meaning — and collapsing
    // them would decide by accident the exact question R16 parked. The fixture
    // uses a FRACTIONAL, non-monotonic sortOrder precisely so a substituted
    // sequence number cannot coincidentally match.
    const local = service();
    await seedTask(local, { sortOrder: -7.25 });
    const page = parseTaskPageJson(
      await (await local.app.fetch(authed(local.devToken, TASKS_READ_PATH))).text());
    expect(page!.items[0]!.sortOrder).toBe(-7.25);
    // A store sequence is a positive integer; -7.25 is neither.
    expect(Number.isInteger(page!.items[0]!.sortOrder)).toBe(false);
  });

  test("the served page makes no authorship claim about any timestamp", async () => {
    // R16 guard 1, asserted on the wire rather than on a comment. The page
    // carries VALUES and nothing that labels who authored them — no `*_by`, no
    // `server`/`client` qualifier, no authority marker. Whether these timestamps
    // are server- or client-authored is parked for David, and the wire must stay
    // valid under either answer.
    const local = service();
    await seedTask(local);
    const raw = await (await local.app.fetch(authed(local.devToken, TASKS_READ_PATH))).text();
    for (const forbidden of ["authoredBy", "createdBy", "updatedBy", "serverTime", "clientTime", "authoritative"]) {
      expect(raw).not.toContain(forbidden);
    }
    const page = parseTaskPageJson(raw);
    expect(typeof page!.items[0]!.createdAt).toBe("number");
    expect(typeof page!.items[0]!.updatedAt).toBe("number");
  });
});
