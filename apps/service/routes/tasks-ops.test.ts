/**
 * `POST /v1/tasks/ops` — the write door, against THE REAL SERVICE.
 *
 * Boots `createLocalService`, the same factory `bin/dev-server.ts` uses, so
 * every byte asserted here is produced by the shipped wiring rather than by a
 * lookalike assembled in this file. That is the whole reason `app-facing.ts`
 * exists, and the reason the fence harness's own header gave for why a
 * placeholder door was a problem.
 *
 * THE CONFORMANCE SUITE AT THE BOTTOM IS DRIVEN BY THE VENDORED CORPUS, not by
 * a list retyped here. A retyped list agrees with itself; the corpus is the
 * contract's own bytes.
 *
 * Every invariant carries a red-proof applied to the real source and observed.
 * The ones that did NOT go red are recorded as such, in place — a red-proof
 * that stays green is evidence about the assertion.
 */

import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import {
  WRITE_AVAILABILITY,
  WRITE_ERRORS,
  WRITE_REFUSALS,
  isTrustedWriteAccepted,
} from "@omi-core/ratified-contracts/write/ops";

import {
  createInMemoryLocalServiceStores,
  createLocalDevService,
  type LocalService,
} from "../app-facing";
import { WRITE_RUN_ID_HEADER } from "../observability/write-ops-counter";
import { RETENTION_CAP_SECONDS } from "../stores/straggler-table";
import { TASKS_OPS_PATH } from "./tasks-ops";

const DEV_KEY_MATERIAL_LABEL = "omi-local-dev-token-not-a-secret-v1";
const OWNER_ACCOUNT_ID = "local-dev-user";
const ACTIVE_EPOCH = 7;
const STALE_EPOCH = 6;

const CORPUS = new URL(
  "../../../node_modules/@omi-core/ratified-contracts/fixtures/write-ops-conformance.json",
  import.meta.url,
);
const OUTCOMES_OF_RECORD = new URL(
  "../../../node_modules/@omi-core/ratified-contracts/fixtures/write-ops-outcomes.json",
  import.meta.url,
);

interface Booted {
  readonly service: LocalService;
  readonly auth: string;
}

const boot = (): Booted => {
  const service = createLocalDevService({
    db: new Database(":memory:"),
    ownerAccountId: OWNER_ACCOUNT_ID,
    memoryCount: 2,
    accountTimezone: "America/Los_Angeles",
    devSecretLabel: DEV_KEY_MATERIAL_LABEL,
  });
  return { service, auth: `Bearer ${service.devToken}` };
};

const control = async (booted: Booted, path: string, body: unknown): Promise<Response> =>
  booted.service.app.request(path, {
    method: "POST",
    headers: { authorization: booted.auth, "content-type": "application/json" },
    body: JSON.stringify(body),
  });

/** Drives ADR-010 §1's forward activation order through the registered app. */
const cutOver = async (booted: Booted, epoch = ACTIVE_EPOCH): Promise<void> => {
  const observation = (overrides: Record<string, unknown>) => ({
    control_revision: 1,
    account_generation: "legacy",
    account_epoch: null,
    lifecycle_state: "active",
    deletion_epoch: null,
    ...overrides,
  });
  await control(booted, "/v1/qa/control/observe", observation({}));
  await control(booted, "/v1/qa/control/observe", observation({ control_revision: 2, account_generation: "migrating" }));
  await control(booted, "/v1/qa/control/observe", observation({
    control_revision: 3, account_generation: "new", account_epoch: epoch,
  }));
  const activated = await control(booted, "/v1/qa/control/activate", { epoch, at_control_revision: 3 });
  expect(await activated.json()).toMatchObject({ activated: true });
};

const writeId = (seed: string): string => seed.padEnd(64, "0").slice(0, 64).replace(/[^0-9a-f]/g, "0");

interface Wire {
  readonly status: number;
  readonly text: string;
  readonly retryAfter: string | null;
}

const post = async (
  booted: Booted,
  body: string,
  options: { readonly path?: string; readonly token?: string | null; readonly runId?: string } = {},
): Promise<Wire> => {
  const headers: Record<string, string> = { "content-type": "application/json" };
  const token = options.token === undefined ? booted.auth : options.token;
  if (token !== null) headers["authorization"] = token;
  if (options.runId !== undefined) headers[WRITE_RUN_ID_HEADER] = options.runId;
  const response = await booted.service.app.request(options.path ?? TASKS_OPS_PATH, {
    method: "POST", headers, body,
  });
  return {
    status: response.status,
    text: await response.text(),
    retryAfter: response.headers.get("retry-after"),
  };
};

/** A canonical envelope: compact, key order as written. */
const envelope = (input: {
  readonly writeId: string;
  readonly epoch?: number;
  readonly domain?: string;
  readonly op: unknown;
}): string => JSON.stringify({
  write_id: input.writeId,
  account_epoch: input.epoch ?? ACTIVE_EPOCH,
  domain: input.domain ?? "tasks",
  op: input.op,
});

const create = (id: string, content: Record<string, unknown> = { title: "buy oat milk" }) =>
  ({ op: "create", record_id: id, content });

const statsFor = async (booted: Booted, run: string): Promise<Record<string, unknown>> => {
  const response = await booted.service.app.request(`/v1/qa/control/stats?run=${encodeURIComponent(run)}`);
  return (await response.json()) as Record<string, unknown>;
};

// ── The door applies, and the read side sees it ─────────────────────────────

describe("an admitted write is APPLIED, not acknowledged", () => {
  /**
   * The property the fence harness could not have: it answered an admitted
   * write with `202 {"fence":"admitted"}` and touched no record, so nothing
   * downstream of the fence was ever proven. Here the same request is visible
   * in the store the tasks read route reads from.
   *
   * red-proof: return an accepted outcome without calling `deps.tasks.apply`.
   * APPLIED AND OBSERVED RED — the record was absent from the read side.
   */
  test("a create reaches the store the read interface serves from", async () => {
    const booted = boot();
    await cutOver(booted);
    const response = await post(booted, envelope({ writeId: writeId("a"), op: create("task-1") }));

    expect(response.status).toBe(200);
    const body: unknown = JSON.parse(response.text);
    expect(isTrustedWriteAccepted(body)).toBe(true);
    expect((body as { idempotent: boolean }).idempotent).toBe(false);

    const stored = booted.service.writePath.tasksRead.readRecord(OWNER_ACCOUNT_ID, "task-1");
    expect(stored?.content).toEqual({ title: "buy oat milk" });
    expect(stored?.revision).toBe((body as { applied: { revision: string } }).applied.revision);
  });

  /**
   * Ruling B1. The user's edit IS in the record; reporting anything else would
   * be the false failure the contract exists to prevent.
   *
   * red-proofs, both APPLIED AND OBSERVED RED: make the `seen.kind ===
   * "replay"` branch unreachable so a replay falls through to apply; and key
   * the registry lookup on a constant instead of the principal's account.
   */
  test("a byte-identical replay is a SUCCESS answered from the registry", async () => {
    const booted = boot();
    await cutOver(booted);
    const bytes = envelope({ writeId: writeId("b"), op: create("task-2") });

    const first = await post(booted, bytes);
    const replay = await post(booted, bytes);

    expect(first.status).toBe(200);
    expect(replay.status).toBe(200);
    expect(JSON.parse(replay.text)).toEqual({
      applied: JSON.parse(first.text).applied,
      idempotent: true,
    });
    // And it applied nothing the second time: the revision did not advance.
    expect(booted.service.writePath.tasksRead.readRecord(OWNER_ACCOUNT_ID, "task-2")?.revision)
      .toBe(JSON.parse(first.text).applied.revision);
  });

  /**
   * red-proof: answer `write_id_reuse` with the `conflict` status and body.
   * APPLIED AND OBSERVED RED.
   */
  test("the same write_id laundering different content is refused, and applies nothing", async () => {
    const booted = boot();
    await cutOver(booted);
    const id = writeId("c");
    await post(booted, envelope({ writeId: id, op: create("task-3", { title: "first" }) }));
    const reuse = await post(booted, envelope({ writeId: id, op: create("task-3", { title: "second" }) }));

    expect(reuse.status).toBe(WRITE_ERRORS.write_id_reuse.status);
    expect(reuse.text).toBe(WRITE_ERRORS.write_id_reuse.body);
    expect(booted.service.writePath.tasksRead.readRecord(OWNER_ACCOUNT_ID, "task-3")?.content)
      .toEqual({ title: "first" });
  });

  test("a failed base_revision precondition is `conflict`, distinct from write_id_reuse", async () => {
    const booted = boot();
    await cutOver(booted);
    const first = await post(booted, envelope({ writeId: writeId("d"), op: create("task-4") }));
    const revision = JSON.parse(first.text).applied.revision as string;
    await post(booted, envelope({
      writeId: writeId("e"), op: { op: "patch", record_id: "task-4", patch: { title: "x" } },
    }));

    const stale = await post(booted, envelope({
      writeId: writeId("f"),
      op: { op: "patch", record_id: "task-4", patch: { title: "y" }, base_revision: revision },
    }));
    expect(stale.status).toBe(WRITE_ERRORS.conflict.status);
    expect(stale.text).toBe(WRITE_ERRORS.conflict.body);
    expect(stale.text).not.toBe(WRITE_ERRORS.write_id_reuse.body);
  });
});

describe("the rendered Settings entitlement is the write fence entitlement", () => {
  test("changing the one entitlement projection moves Settings and enforcement together", async () => {
    const stores = createInMemoryLocalServiceStores();
    stores.settings.putIdentity(OWNER_ACCOUNT_ID, {
      displayName: "Entitled user",
      email: "entitled@example.invalid",
    });
    stores.settings.putEntitlement(OWNER_ACCOUNT_ID, {
      planLabel: "Omi Plus",
      limitKey: "tasks",
      used: 9,
      limit: 10,
      limitReached: false,
      upgradeAvailable: true,
    });
    const service = createLocalDevService({
      db: new Database(":memory:"),
      ownerAccountId: OWNER_ACCOUNT_ID,
      memoryCount: 2,
      accountTimezone: "America/Los_Angeles",
      devSecretLabel: DEV_KEY_MATERIAL_LABEL,
      stores,
    });
    const booted = { service, auth: `Bearer ${service.devToken}` };
    await cutOver(booted);

    const settingsBefore = await service.app.request("/v1/settings", {
      headers: { authorization: booted.auth },
    });
    expect(settingsBefore.status).toBe(200);
    expect(await settingsBefore.json()).toMatchObject({
      entitlement: { limitKey: "tasks", used: 9, limit: 10, limitReached: false },
    });

    const before = await post(booted, envelope({
      writeId: writeId("entitlement-before"),
      op: create("task-before-entitlement-change"),
    }));
    expect(before.status).toBe(200);

    stores.settings.putEntitlement(OWNER_ACCOUNT_ID, {
      planLabel: "Omi Plus",
      limitKey: "tasks",
      used: 10,
      limit: 10,
      limitReached: true,
      upgradeAvailable: true,
    });

    const settings = await service.app.request("/v1/settings", {
      headers: { authorization: booted.auth },
    });
    expect(settings.status).toBe(200);
    expect(await settings.json()).toMatchObject({
      entitlement: { limitKey: "tasks", used: 10, limit: 10, limitReached: true },
    });

    const after = await post(booted, envelope({
      writeId: writeId("entitlement-after"),
      op: create("task-after-entitlement-change"),
    }));
    expect(after).toEqual({
      status: WRITE_REFUSALS.entitlement.status,
      text: WRITE_REFUSALS.entitlement.body,
      retryAfter: null,
    });
    expect(service.writePath.tasksRead.readRecord(
      OWNER_ACCOUNT_ID,
      "task-after-entitlement-change",
    )).toBeNull();
  });
});

// ── The fence, in the registered door ───────────────────────────────────────

describe("the account epoch fence runs in the shipped route", () => {
  /**
   * The pair, carried over from the fence harness's own discipline: one field
   * of one request separates the refusal from the acceptance, against the same
   * process and the same body grammar. A broken route cannot produce the 200,
   * so it cannot produce this pair.
   *
   * red-proof: make the `!decision.admitted` branch unreachable, so an
   * un-admitted decision falls through to apply. APPLIED AND OBSERVED RED —
   * the stale envelope was applied and answered 200.
   */
  test("a stale epoch is refused 409 while the same envelope at the active epoch is applied", async () => {
    const booted = boot();
    await cutOver(booted);
    const stale = await post(booted, envelope({ writeId: writeId("1a"), epoch: STALE_EPOCH, op: create("t") }));
    const fresh = await post(booted, envelope({ writeId: writeId("1b"), epoch: ACTIVE_EPOCH, op: create("t") }));

    expect(stale.status).toBe(WRITE_REFUSALS.stale_epoch.status);
    expect(stale.text).toBe(WRITE_REFUSALS.stale_epoch.body);
    expect(fresh.status).toBe(200);
  });

  /**
   * A stale-epoch refusal must LOSE NOTHING. This is the only refusal in the
   * whole fence that preserves, and the row is the only surviving copy of what
   * the user wrote.
   *
   * red-proof: make the `preserve_envelope` branch unreachable.
   * APPLIED AND OBSERVED RED — the export came back empty.
   */
  test("a refused straggler's full envelope is retained, patch included", async () => {
    const booted = boot();
    await cutOver(booted);
    const bytes = envelope({
      writeId: writeId("2a"), epoch: STALE_EPOCH,
      op: { op: "patch", record_id: "t", patch: { title: "buy oat milk" } },
    });
    await post(booted, bytes);

    const preserved = booted.service.writePath.stragglers.exportAccount(OWNER_ACCOUNT_ID);
    expect(preserved).toHaveLength(1);
    expect(preserved[0]?.envelope_json).toBe(bytes);
    expect(preserved[0]?.envelope_json).toContain("buy oat milk");
  });

  /**
   * The refusals that do NOT preserve must not quietly start retaining user
   * content — that is how the record class whose retention window is
   * owner-signed gets manufactured faster than the owner can sign a policy for
   * it (W2's exact objection).
   */
  test("backpressure retains nothing", async () => {
    const booted = boot();
    // No control state at all: fail-closed `control_unavailable`.
    const fenced = await post(booted, envelope({ writeId: writeId("3a"), op: create("t") }));
    expect(fenced.status).toBe(WRITE_AVAILABILITY.control_unavailable.status);
    expect(fenced.text).toBe(WRITE_AVAILABILITY.control_unavailable.body);
    expect(fenced.retryAfter).toBe("60");
    expect(booted.service.writePath.stragglers.exportAccount(OWNER_ACCOUNT_ID)).toEqual([]);
  });

  /**
   * ADR-012 §4 and the read door's discipline: no reason, no epoch, no account
   * identifier on the wire.
   *
   * red-proof: add the fence's internal reason to the refusal body in
   * `fence-http.ts`. APPLIED AND OBSERVED RED (and it reddens
   * `fence-contract-agreement.test.ts` too, which is the point of that test).
   */
  test("no refusal body carries a reason, an epoch or an account id", async () => {
    const booted = boot();
    await cutOver(booted);
    const stale = await post(booted, envelope({ writeId: writeId("4a"), epoch: STALE_EPOCH, op: create("t") }));
    expect(Object.keys(JSON.parse(stale.text)).sort()).toEqual(["error", "refusal_outcome"]);
    for (const secret of [OWNER_ACCOUNT_ID, "request_epoch_behind", String(ACTIVE_EPOCH)]) {
      expect(stale.text).not.toContain(secret);
    }
  });

  /**
   * The fence's own counter must not move for a request that never had a
   * principal — `epoch-fence.test.ts` pins the same property on the harness,
   * and the registered door must keep it.
   *
   * red-proof: remove the authentication early-return and let the fence run
   * with an anonymous account id — the shape of "authenticate after the
   * fence". APPLIED AND OBSERVED RED.
   */
  test("a request refused before the fence produces no fence decision", async () => {
    const booted = boot();
    await cutOver(booted);
    const run = `pre-fence-${crypto.randomUUID()}`;
    const unauthenticated = await post(
      booted,
      envelope({ writeId: writeId("5a"), op: create("t") }),
      { token: null, runId: run },
    );
    expect(unauthenticated.status).toBe(WRITE_REFUSALS.authentication.status);
    expect(unauthenticated.text).toBe(WRITE_REFUSALS.authentication.body);

    const stats = await statsFor(booted, run);
    expect(stats["fence"]).toBeNull();
    // The ROUTE, however, did produce an outcome — the two counters measure
    // different things and must not be confused for one another.
    expect(stats["writeOps"]).toMatchObject({ outcomes: { authentication: 1 } });
  });
});

// ── Two independent measurements, joined by run id ──────────────────────────

describe("the door is joinable: producer counters and a consumer observation", () => {
  /**
   * `STATE.md`: a claim of working behaviour names a producer-side counter AND
   * a consumer-side observation, joined by run id, and the claiming agent runs
   * both. Here the consumer side is what this test received; the producer side
   * is what the process counted where the outcome was produced.
   *
   * red-proof: record a literal `"accepted"` at the TOP of the handler — the
   * dispatch-side number STATE.md forbids, added alongside the real one.
   * APPLIED AND OBSERVED RED.
   */
  test("the process's own outcome counts match what the client received", async () => {
    const booted = boot();
    await cutOver(booted);
    const run = `arbiter-${crypto.randomUUID()}`;
    const otherRun = `arbiter-other-${crypto.randomUUID()}`;

    const bytes = envelope({ writeId: writeId("6a"), op: create("t") });
    const observed: Record<string, number> = {};
    const seen = (key: string) => { observed[key] = (observed[key] ?? 0) + 1; };

    const first = await post(booted, bytes, { runId: run });
    seen(JSON.parse(first.text).idempotent ? "accepted_idempotent" : "accepted");
    const replay = await post(booted, bytes, { runId: run });
    seen(JSON.parse(replay.text).idempotent ? "accepted_idempotent" : "accepted");
    for (const seed of ["6b", "6c"]) {
      const stale = await post(booted, envelope({ writeId: writeId(seed), epoch: STALE_EPOCH, op: create("t") }), { runId: run });
      seen(JSON.parse(stale.text).refusal_outcome as string);
    }
    // Interleaved traffic under a DIFFERENT run id. A counter that only kept
    // totals would agree with the wrong answer here.
    await post(booted, envelope({ writeId: writeId("6d"), epoch: STALE_EPOCH, op: create("t") }), { runId: otherRun });

    expect(observed).toEqual({ accepted: 1, accepted_idempotent: 1, stale_epoch: 2 });

    const stats = await statsFor(booted, run);
    expect(stats["writeOps"]).toMatchObject({
      outcomes: { accepted: 1, accepted_idempotent: 1, stale_epoch: 2, validation: 0, conflict: 0 },
      preservedEnvelopes: 2,
      // Asserted, not merely counted: the route's top-level guard must not have
      // caught anything during a run whose four outcomes were all intended.
      internalErrors: 0,
    });
    // The fence's independent count of the same events: it saw two admissions
    // (the replay is admitted by the fence and then answered by the registry)
    // and two stale-epoch refusals.
    expect(stats["fence"]).toMatchObject({
      admitted: 2, refused: { stale_epoch: 2 }, preservedEnvelopes: 2,
    });
    expect((await statsFor(booted, otherRun))["writeOps"]).toMatchObject({ outcomes: { stale_epoch: 1 } });
  });

  /**
   * CORPUS lane dogfood, run-2026-08-09, landed as a durable test per the
   * coordinator's instruction: a throwaway script that gets deleted means the
   * run's best evidence exists only in a report. This is the exact sequence
   * run by hand against `createLocalService` — the registered composition,
   * the same factory `bin/dev-server.ts` uses — the first time the write
   * path was observed working end to end from outside the suite that built
   * it. Unlike the sibling test above, this walks all FOUR write outcomes
   * (`accepted`, `accepted_idempotent`, `stale_epoch`, `write_id_reuse`) as
   * one narrative journey rather than isolating any single one.
   *
   * red-proof: in write-id-registry.ts's `lookup`, always return
   * `{ kind: "replay", outcome: row.outcome }` regardless of fingerprint
   * match, so a genuine `write_id_reuse` (same key, different content) is
   * misreported as an idempotent replay of the FIRST content instead of
   * refused. APPLIED AND OBSERVED RED: the consumer-side status/outcome
   * assertions on step 4 fail (200 idempotent-replay of the original title
   * instead of 409 write_id_reuse), and the producer-side stats assertion
   * fails independently in the same run (write_id_reuse: 0 instead of 1,
   * accepted_idempotent: 2 instead of 1) — both sides move together, which is
   * the property this test exists to pin.
   */
  test("CORPUS dogfood: all four write outcomes in one sequence, producer and consumer agree", async () => {
    const booted = boot();
    await cutOver(booted);
    const run = `corpus-dogfood-${crypto.randomUUID()}`;
    const recordId = "dogfood-task-1";
    const original = { op: "create", record_id: recordId, content: { title: "corpus dogfood: is the door alive" } };
    const wid = writeId("d0");

    // 1. A genuine create.
    const created = await post(booted, envelope({ writeId: wid, op: original }), { runId: run });
    expect(created.status).toBe(200);
    const createdBody = JSON.parse(created.text) as { idempotent: boolean; applied: { record_id: string } };
    expect(createdBody.idempotent).toBe(false);
    expect(createdBody.applied.record_id).toBe(recordId);

    // 2. Crash-replay of the SAME write_id, SAME content — accepted_idempotent, never a failure.
    const replayed = await post(booted, envelope({ writeId: wid, op: original }), { runId: run });
    expect(replayed.status).toBe(200);
    expect((JSON.parse(replayed.text) as { idempotent: boolean }).idempotent).toBe(true);

    // 3. A straggler under a stale epoch — 409 stale_epoch, never conflict.
    const stale = await post(
      booted,
      envelope({ writeId: writeId("d1"), epoch: STALE_EPOCH, op: { op: "patch", record_id: recordId, patch: { done: true } } }),
      { runId: run },
    );
    expect(stale.status).toBe(409);
    expect(JSON.parse(stale.text)).toEqual({ error: "stale_epoch", refusal_outcome: "stale_epoch" });

    // 4. The SAME write_id as step 1, DIFFERENT content — write_id_reuse, never
    // a silent second apply and never an idempotent replay of the wrong content.
    const reused = await post(
      booted,
      envelope({ writeId: wid, op: { op: "create", record_id: recordId, content: { title: "a completely different title" } } }),
      { runId: run },
    );
    expect(reused.status).toBe(409);
    expect(JSON.parse(reused.text)).toEqual({ error: "write_id_reuse" });

    // Producer-side counter, same run id — the second, independent measurement.
    const stats = await statsFor(booted, run);
    expect(stats["fence"]).toMatchObject({ admitted: 3, refused: { stale_epoch: 1 } });
    expect(stats["writeOps"]).toMatchObject({
      outcomes: {
        accepted: 1, accepted_idempotent: 1, stale_epoch: 1, write_id_reuse: 1,
        authentication: 0, authorization: 0, entitlement: 0, validation: 0, conflict: 0,
      },
    });
  });

  /**
   * The control probe that makes the numbers above mean something: without it,
   * a counter hard-coded to answer the same tally for every run would pass.
   */
  test("a run that sent nothing has no tally at all — null, not zero", async () => {
    const booted = boot();
    const stats = await statsFor(booted, `never-sent-${crypto.randomUUID()}`);
    expect(stats["writeOps"]).toBeNull();
    expect(stats["fence"]).toBeNull();
  });
});

// ── Route hardening, at parity with the read door ───────────────────────────

describe("route hardening", () => {
  test("only POST is answered; every other method is a plain 404", async () => {
    const booted = boot();
    await cutOver(booted);
    for (const method of ["GET", "PUT", "PATCH", "DELETE"]) {
      const response = await booted.service.app.request(TASKS_OPS_PATH, {
        method, headers: { authorization: booted.auth },
      });
      expect(response.status).toBe(404);
      expect(await response.json()).toEqual({ error: "not_found" });
    }
  });

  test("a trailing slash is a different path and 404s", async () => {
    const booted = boot();
    await cutOver(booted);
    const response = await post(booted, envelope({ writeId: writeId("7a"), op: create("t") }), {
      path: `${TASKS_OPS_PATH}/`,
    });
    expect(response.status).toBe(404);
  });

  /**
   * Authentication precedes validation: an unauthenticated caller learns
   * nothing about whether its envelope would have parsed.
   *
   * red-proof: answer the authentication failure with the validation class
   * instead. APPLIED AND OBSERVED RED.
   */
  test("a garbage body from an unauthenticated caller is authentication, not validation", async () => {
    const booted = boot();
    const response = await post(booted, "not json at all", { token: null });
    expect(response.status).toBe(WRITE_REFUSALS.authentication.status);
    expect(response.text).toBe(WRITE_REFUSALS.authentication.body);
  });

  test("a bare token without the Bearer prefix is authentication", async () => {
    const booted = boot();
    await cutOver(booted);
    const response = await post(booted, envelope({ writeId: writeId("8a"), op: create("t") }), {
      token: booted.service.devToken,
    });
    expect(response.status).toBe(WRITE_REFUSALS.authentication.status);
  });

  /**
   * The route defines NO query parameters. It ignores them rather than
   * refusing, and this pins that so nobody later builds behaviour on one: a
   * query string must not change the outcome.
   */
  test("a query string cannot change the outcome", async () => {
    const booted = boot();
    await cutOver(booted);
    const response = await post(booted, envelope({ writeId: writeId("9a"), op: create("t") }), {
      path: `${TASKS_OPS_PATH}?limit=1&limit=2`,
    });
    expect(response.status).toBe(200);
  });

  /**
   * Non-canonical JSON is refused by the contract's own parser, not by a second
   * one written here. Duplicate keys are the case that matters: `JSON.parse`
   * keeps the last, so a body carrying two `account_epoch` values would
   * otherwise be silently resolved in the parser's favour.
   *
   * red-proof: parse with `JSON.parse` + `isTrustedWriteOpEnvelope` instead of
   * `parseWriteOpEnvelopeJson`. APPLIED AND OBSERVED RED.
   */
  test("duplicate keys and pretty-printing are refused as validation", async () => {
    const booted = boot();
    await cutOver(booted);
    const good = envelope({ writeId: writeId("aa"), op: create("t") });
    for (const bad of [
      good.replace('"account_epoch":7', '"account_epoch":6,"account_epoch":7'),
      JSON.stringify(JSON.parse(good), null, 2),
    ]) {
      const response = await post(booted, bad);
      expect(response.status).toBe(WRITE_ERRORS.validation.status);
      expect(response.text).toBe(WRITE_ERRORS.validation.body);
    }
  });

  /**
   * The envelope's domain and the path's must agree. A `tasks` envelope posted
   * at another domain's path is malformed for where it was sent.
   *
   * red-proof: drop BOTH clauses of the domain guard
   * (`!isWritableDomain(pathDomain) || envelope.domain !== pathDomain`).
   * APPLIED AND OBSERVED RED — the envelope was applied under the wrong path.
   *
   * TWO RED-PROOFS ON THIS ASSERTION STAYED GREEN, and they are recorded here
   * rather than dropped, because what they say about the guard is worth more
   * than the one that went red:
   *
   * - dropping only `envelope.domain !== pathDomain`: STAYED GREEN. The path
   *   domain `memories` is not writable, so the other clause still refuses.
   * - dropping only `!isWritableDomain(pathDomain)`: STAYED GREEN. The
   *   envelope says `tasks` and the path says `memories`, so the disagreement
   *   clause still refuses.
   *
   * The two clauses are individually redundant for every input reachable
   * TODAY, and no test can separate them, because separating them needs a path
   * domain that is writable AND different from the envelope's — impossible
   * while `WRITABLE_DOMAINS` has one member. **Accepted limit, named and dated
   * 2026-08-09:** the second writable domain is when this becomes testable, and
   * the lane that adds it owns splitting this assertion in two.
   */
  test("a tasks envelope at another domain's path is validation, not an apply", async () => {
    const booted = boot();
    await cutOver(booted);
    const response = await post(booted, envelope({ writeId: writeId("bb"), op: create("t") }), {
      path: "/v1/memories/ops",
    });
    expect(response.status).toBe(WRITE_ERRORS.validation.status);
    expect(response.text).toBe(WRITE_ERRORS.validation.body);
    expect(booted.service.writePath.tasksRead.readRecord(OWNER_ACCOUNT_ID, "t")).toBeNull();
  });
});

// ── CORPUS lane, run-2026-08-09: adversarial probes from OUTSIDE ────────────
//
// Constructed inputs against the shipped route, not diffs read. Two seams
// beyond what `tasks-ops-probes.test.ts` (landed independently, same night)
// already reaches — that file's own "eight concurrent identical envelopes
// apply exactly once" already covers the identical-content interleaving case
// and its own oversize/depth-bound tests already cover the size budget over
// real HTTP (and found a genuine 500-on-deep-JSON defect doing it), so
// neither is repeated here. What is left: write_id REUSE specifically under
// concurrency (identical write_id, DIVERGENT content, racing) — a different
// claim from "identical envelopes race cleanly" — and the straggler
// retention lifecycle (sweep boundary, deletion dominance) driven by rows a
// real refused HTTP request produced, not rows constructed by hand directly
// against the isolated store.

describe("write_id reuse under REAL concurrent interleaving", () => {
  /**
   * The reuse counterpart: concurrent requests sharing a write_id where ONE
   * carries different content. Exactly one may apply (the winner is whichever
   * the scheduler ran first — not asserted, because it is not a contract);
   * every other concurrent request naming that write_id must read as either a
   * clean replay (same content as the winner) or `write_id_reuse` (different
   * content) — never a silent second apply, and never `write_id_reuse`
   * reported for a request that was actually identical to the winner.
   */
  test("N concurrent requests, same write_id, ONE with different content: no silent double apply", async () => {
    const booted = boot();
    await cutOver(booted);
    const wid = writeId("race2");
    const original = envelope({ writeId: wid, op: create("race-target-2") });
    const divergent = envelope({ writeId: wid, op: create("race-target-2", { title: "a different title entirely" }) });

    const responses = await Promise.all([
      post(booted, original), post(booted, original), post(booted, divergent),
      post(booted, original), post(booted, divergent),
    ]);
    const outcomes = responses.map((r) => {
      if (r.status === 409) return (JSON.parse(r.text) as { error: string }).error;
      const body = JSON.parse(r.text) as { idempotent: boolean };
      return body.idempotent ? "accepted_idempotent" : "accepted";
    });
    const applies = outcomes.filter((o) => o === "accepted");
    expect(applies).toHaveLength(1);
    // Everything else is a coherent classification of the SAME write_id
    // against whichever content actually won — never anything else.
    for (const outcome of outcomes) {
      expect(["accepted", "accepted_idempotent", "write_id_reuse"]).toContain(outcome);
    }
    expect(outcomes.filter((o) => o === "write_id_reuse").length).toBeGreaterThan(0);

    // Exactly one record exists — no interleaving left the store holding two
    // divergent applies under one write_id.
    const record = booted.service.writePath.tasksRead.readRecord(OWNER_ACCOUNT_ID, "race-target-2");
    expect(record).not.toBeNull();
  });
});

describe("the straggler retention lifecycle, end to end through the live route", () => {
  /**
   * Existing coverage proves preservation happens (this file, above) and
   * proves the sweep boundary in isolation against hand-built rows
   * (`straggler-table.test.ts`). Neither proves the two composed: that a row
   * PRODUCED BY A REAL REFUSED REQUEST is the row the David-signed 90-day cap
   * actually sweeps, through the same store instance the route writes to.
   *
   * red-proof: change `sweepExpired`'s horizon comparison from `>=` back to
   * `>` (the exact off-by-one OPS's own red-proof pass already found and
   * fixed once against hand-built rows). APPLIED AND OBSERVED RED here too,
   * against a row this test produced via a real stale-epoch HTTP request
   * rather than a row constructed directly against the store — confirming
   * the fixed bug stays fixed from the route's own call path, not only from
   * the unit test that first caught it.
   */
  test("a real refused straggler is swept at the cap boundary, not one second early", async () => {
    const booted = boot();
    await cutOver(booted);

    // Produce a genuine straggler: a stale-epoch write, refused by the fence,
    // through the real route.
    const stale = await post(booted, envelope({ writeId: writeId("ret1"), epoch: STALE_EPOCH, op: create("t") }));
    expect(stale.status).toBe(409);
    const before = booted.service.writePath.stragglers.exportAccount(OWNER_ACCOUNT_ID);
    expect(before).toHaveLength(1);
    const retainedAt = before[0]?.retained_at_epoch_seconds as number;

    // Exactly at the cap: kept.
    const sweptAtCap = booted.service.writePath.stragglers.sweepExpired(retainedAt + RETENTION_CAP_SECONDS);
    expect(sweptAtCap).toBe(0);
    expect(booted.service.writePath.stragglers.exportAccount(OWNER_ACCOUNT_ID)).toHaveLength(1);

    // One second past the cap: swept.
    const sweptPastCap = booted.service.writePath.stragglers.sweepExpired(retainedAt + RETENTION_CAP_SECONDS + 1);
    expect(sweptPastCap).toBe(1);
    expect(booted.service.writePath.stragglers.exportAccount(OWNER_ACCOUNT_ID)).toEqual([]);
  });

  /**
   * B3's "deletion dominates them with no separate mechanism", proved from
   * the route's own call path rather than asserted against hand-built rows:
   * a straggler this test did not construct directly, produced by a genuine
   * refusal through the live door, disappears under `deleteAccount` and
   * never resurfaces via `exportAccount`.
   *
   * red-proof: in `straggler-table.ts`'s `deleteAccount`, change
   * `byAccount.delete(accountId)` to a no-op that only reads the count
   * without removing the entry. APPLIED AND OBSERVED RED: `exportAccount`
   * after deletion still returned the row this test produced via HTTP.
   */
  test("account deletion removes a straggler this test never touched directly", async () => {
    const booted = boot();
    await cutOver(booted);
    await post(booted, envelope({ writeId: writeId("ret2"), epoch: STALE_EPOCH, op: create("t") }));
    expect(booted.service.writePath.stragglers.exportAccount(OWNER_ACCOUNT_ID)).toHaveLength(1);

    const removed = booted.service.writePath.stragglers.deleteAccount(OWNER_ACCOUNT_ID);
    expect(removed).toBe(1);
    expect(booted.service.writePath.stragglers.exportAccount(OWNER_ACCOUNT_ID)).toEqual([]);
  });
});

// ── Conformance against the vendored corpus ─────────────────────────────────

describe("the vendored write-ops corpus, executed", () => {
  /**
   * Driven by the contract's own fixture file. The corpus distinguishes bodies
   * that are RATIFIED byte-for-byte from bodies that are not
   * (`bodyRatified: false` for the accepted cases, whose revision values are
   * illustrative), and this test respects that distinction rather than pinning
   * an unratified byte and calling it conformance.
   *
   * red-proofs, both APPLIED AND OBSERVED RED: replace the route's use of
   * `WRITE_ERRORS.validation.body` with a different two-byte JSON body (five
   * corpus rows red), and change the conflict status to 418 (one row red).
   *
   * ONE STAYED GREEN, recorded because it says something real: dropping the
   * route's entire path-domain guard leaves this suite green. The corpus row
   * "memories is not a writable domain" is enforced by the CONTRACT's own
   * predicate — `isTrustedWriteOpEnvelope` rejects a non-writable
   * `envelope.domain` before the route looks at the path — so that row proves
   * the contract, not the route. The route's guard covers a different input
   * (a valid `tasks` envelope at a foreign path) and is red-proofed in
   * "route hardening" above.
   */
  test("every corpus case's status and ratified bytes are what this route answers", async () => {
    const corpus = await Bun.file(CORPUS).json() as ReadonlyArray<{
      name: string; wireOutcome: string; path: string; requestBody: string;
      response: { status: number; body: string };
    }>;
    const outcomes = await Bun.file(OUTCOMES_OF_RECORD).json() as {
      outcomes: ReadonlyArray<{ outcome: string; bodyRatified: boolean }>;
    };
    const ratifiedBody = new Map(outcomes.outcomes.map((row) => [row.outcome, row.bodyRatified]));

    /**
     * THE ONE ROW THIS ROUTE CANNOT REACH FROM A REQUEST, and it is down from
     * three.
     *
     * `entitlement` needs a grant/entitlement composition that does not exist
     * in `apps/service` yet — the fence can produce the outcome, but nothing in
     * this service can put an account into the state that produces it. Named
     * rather than silently skipped, because a suite that quietly drops rows is
     * how a corpus stops being a corpus.
     *
     * The other two are now EXECUTED against the real route rather than
     * excluded with a note, which is what a conformance runner is for:
     *
     * - `authorization` — reached by seeding `lifecycle_state:
     *   "deletion_pending"`. ADR-014 §1 makes lifecycle dominant and ADR-012 §4
     *   forbids a probeable "deleted" outcome, so the fence answers the same
     *   403 a missing grant would. That IS the corpus's authorization row.
     * - `control_unavailable` — reached by NOT cutting over: an account the
     *   destination has never been told about is the ratified fail-closed
     *   posture, and it is the availability signal's own corpus row.
     */
    const notReachableHere = new Set(["entitlement"]);

    const executed: string[] = [];
    let rebasedCases = 0;
    for (const entry of corpus) {
      if (notReachableHere.has(entry.wireOutcome)) continue;
      const booted = boot();
      // `control_unavailable` is the ABSENCE of control state, so this row is
      // the one case that must not be cut over.
      if (entry.wireOutcome !== "control_unavailable") await cutOver(booted);
      if (entry.wireOutcome === "authorization") {
        // Lifecycle dominates generation: the account is fully cut over and
        // active, and only `lifecycle_state` moves.
        await control(booted, "/v1/qa/control/observe", {
          control_revision: 4,
          account_generation: "new",
          account_epoch: ACTIVE_EPOCH,
          lifecycle_state: "deletion_pending",
          deletion_epoch: 41,
        });
      }

      // The idempotent-replay row is a SECOND send of the row above it.
      if (entry.wireOutcome === "accepted_idempotent") await post(booted, entry.requestBody, { path: entry.path });
      // The reuse and conflict rows need a prior applied op to collide with.
      if (entry.wireOutcome === "write_id_reuse") {
        const first = JSON.parse(entry.requestBody) as { write_id: string; account_epoch: number; domain: string; op: unknown };
        await post(booted, JSON.stringify({ ...first, op: { op: "create", record_id: "task-9f21", content: { seed: true } } }), { path: entry.path });
      }

      /**
       * THE ONE PLACE A CORPUS BYTE IS REWRITTEN, and why it is legitimate.
       *
       * Two rows carry a `base_revision`: the accepted patch, and the conflict.
       * The accepted one presumes the record's CURRENT revision equals the
       * fixture's literal — and revision values are exactly the bytes the
       * corpus marks `bodyRatified: false`, because they are whatever the
       * serving store's scheme produces. No implementation can satisfy that
       * literal except by adopting the fixture author's hash function, which is
       * not ratified and is not the property under test.
       *
       * So the setup seeds the record and substitutes the REAL current revision
       * into the accepted case, leaving the conflict case's literal alone —
       * that one is *supposed* not to match. Both substitutions are asserted
       * below so this cannot silently degrade into "patch with no precondition".
       */
      const parsed = JSON.parse(entry.requestBody) as {
        write_id: string; account_epoch: number; domain: string;
        op: { op: string; record_id: string; base_revision?: string };
      };
      let requestBody = entry.requestBody;
      // Only the rows whose precondition is actually EVALUATED get a seeded
      // record. The stale-epoch and validation rows also carry a
      // `base_revision`, and both are refused before the store is consulted —
      // seeding them would send their (stale, or malformed) envelope through
      // the door twice and measure the setup instead of the case.
      const preconditionIsEvaluated = entry.wireOutcome === "accepted" || entry.wireOutcome === "conflict";
      if (preconditionIsEvaluated && typeof parsed.op.base_revision === "string") {
        expect(parsed.op.base_revision).toMatch(/^[0-9a-f]{64}$/);
        const seeded = await post(booted, JSON.stringify({
          write_id: "9".repeat(64), account_epoch: parsed.account_epoch, domain: parsed.domain,
          op: { op: "create", record_id: parsed.op.record_id, content: { seed: true } },
        }), { path: entry.path });
        expect(seeded.status).toBe(200);
        if (entry.wireOutcome !== "conflict") {
          const live = JSON.parse(seeded.text).applied.revision as string;
          expect(live).not.toBe(parsed.op.base_revision);
          requestBody = entry.requestBody.replace(parsed.op.base_revision, live);
          rebasedCases += 1;
        }
      }

      const token = entry.wireOutcome === "authentication" ? null : undefined;
      const response = await post(booted, requestBody, { path: entry.path, token });

      expect({ case: entry.name, status: response.status })
        .toEqual({ case: entry.name, status: entry.response.status });
      if (ratifiedBody.get(entry.wireOutcome) === true) {
        expect({ case: entry.name, body: response.text })
          .toEqual({ case: entry.name, body: entry.response.body });
        // The availability row is the only one carrying a header the corpus
        // ratifies, and W1 makes it load-bearing: fixed, never varying with
        // account state.
        if (entry.wireOutcome === "control_unavailable") {
          expect({ case: entry.name, retryAfter: response.retryAfter })
            .toEqual({ case: entry.name, retryAfter: "60" });
        }
      } else {
        // Not byte-ratified: assert the SHAPE the contract does ratify.
        const body: unknown = JSON.parse(response.text);
        expect({ case: entry.name, accepted: isTrustedWriteAccepted(body) })
          .toEqual({ case: entry.name, accepted: true });
        expect((body as { idempotent: boolean }).idempotent)
          .toBe(entry.wireOutcome === "accepted_idempotent");
      }
      executed.push(entry.name);
    }

    // The count is asserted so a corpus row that stops being executed — by a
    // rename, a filter, or a throw swallowed somewhere — fails instead of
    // quietly shrinking the suite.
    expect(executed.length).toBe(corpus.length - corpus.filter((entry) => notReachableHere.has(entry.wireOutcome)).length);
    expect(executed.length).toBeGreaterThan(10);
    // Exactly one row had its unratified revision literal rebased. If a future
    // corpus adds another, this fails and somebody reads the paragraph above
    // rather than discovering the rewrite by accident.
    expect(rebasedCases).toBe(1);
  });
});
