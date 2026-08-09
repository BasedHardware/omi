/**
 * ADVERSARIAL PROBES against `POST /v1/tasks/ops` — the inputs the route's own
 * stated boundaries imply are safe, constructed and run.
 *
 * Every finding this program has recorded came from building such an input and
 * running it; none came from reading a diff. These are the ones that HELD. The
 * two that did not are in `tasks-ops-known-defect.test.ts` and in
 * `data/run-2026-08-09/blocked/`.
 *
 * They are pinned here because a boundary that holds by accident is one refactor
 * from not holding, and none of these would fail loudly — an oversize body that
 * started 500-ing, a `write_id` that started matching case-insensitively, or a
 * concurrent replay that started applying twice all look like ordinary green
 * suites from every other angle.
 */

import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import {
  MAX_WRITE_ENVELOPE_JSON_CODE_UNITS,
  WRITE_ERRORS,
  WRITE_REFUSALS,
} from "@omi-core/ratified-contracts/write/ops";

import { createLocalService, type LocalService } from "../app-facing";

const OWNER_ACCOUNT_ID = "local-dev-user";
const EPOCH = 7;

interface Booted { readonly service: LocalService; readonly auth: string }

const boot = (): Booted => {
  const service = createLocalService({
    db: new Database(":memory:"),
    ownerAccountId: OWNER_ACCOUNT_ID,
    memoryCount: 2,
    accountTimezone: "America/Los_Angeles",
    devSecretLabel: "omi-local-dev-token-not-a-secret-v1",
  });
  return { service, auth: `Bearer ${service.devToken}` };
};

const control = async (booted: Booted, path: string, body: unknown): Promise<Record<string, unknown>> =>
  (await (await booted.service.app.request(path, {
    method: "POST",
    headers: { authorization: booted.auth, "content-type": "application/json" },
    body: JSON.stringify(body),
  })).json()) as Record<string, unknown>;

const observation = (overrides: Record<string, unknown>) => ({
  control_revision: 1, account_generation: "legacy", account_epoch: null,
  lifecycle_state: "active", deletion_epoch: null, ...overrides,
});

const cutOver = async (booted: Booted): Promise<void> => {
  await control(booted, "/v1/qa/control/observe", observation({}));
  await control(booted, "/v1/qa/control/observe", observation({ control_revision: 2, account_generation: "migrating" }));
  await control(booted, "/v1/qa/control/observe", observation({ control_revision: 3, account_generation: "new", account_epoch: EPOCH }));
  expect(await control(booted, "/v1/qa/control/activate", { epoch: EPOCH, at_control_revision: 3 }))
    .toMatchObject({ activated: true });
};

const post = async (
  booted: Booted, body: string, path = "/v1/tasks/ops", token: string | null = null,
): Promise<{ status: number; text: string }> => {
  const headers: Record<string, string> = { "content-type": "application/json" };
  const bearer = token ?? booted.auth;
  if (bearer !== "") headers["authorization"] = bearer;
  const response = await booted.service.app.request(path, { method: "POST", headers, body });
  return { status: response.status, text: await response.text() };
};

const hex = (seed: string): string => seed.padEnd(64, "0").replace(/[^0-9a-f]/g, "0").slice(0, 64);

const envelope = (input: {
  readonly writeId?: unknown; readonly epoch?: unknown; readonly domain?: string; readonly op: unknown;
}): string => JSON.stringify({
  write_id: input.writeId ?? hex("00"),
  account_epoch: input.epoch ?? EPOCH,
  domain: input.domain ?? "tasks",
  op: input.op,
});

const create = (id: string, content: Record<string, unknown> = { title: "x" }) =>
  ({ op: "create", record_id: id, content });

describe("grammar boundaries — the exact edge, on both sides", () => {
  /**
   * `RECORD_ID_PATTERN` is 1–256 printable ASCII. Both sides of the boundary are
   * probed, because a test that only sends the invalid one passes against a
   * route that refuses everything.
   *
   * red-proof: relax `RECORD_ID_PATTERN`'s upper bound in the contract's dist —
   * not applied, because that mutates a ratified artifact. Applied instead:
   * accept the envelope without calling `parseWriteOpEnvelopeJson` (see the
   * canonical-parser proof in `tasks-ops.test.ts`), which reddens this row too.
   */
  test("a 256-character record_id is accepted and a 257-character one is validation", async () => {
    const booted = boot();
    await cutOver(booted);
    expect((await post(booted, envelope({ writeId: hex("a1"), op: create("z".repeat(256)) }))).status).toBe(200);
    const over = await post(booted, envelope({ writeId: hex("a2"), op: create("z".repeat(257)) }));
    expect(over.status).toBe(WRITE_ERRORS.validation.status);
    expect(over.text).toBe(WRITE_ERRORS.validation.body);
  });

  test("a record_id containing a NUL is validation, not a stored record", async () => {
    const booted = boot();
    await cutOver(booted);
    const raw = `{"write_id":"${hex("a3")}","account_epoch":7,"domain":"tasks","op":{"op":"create","record_id":"a\\u0000b","content":{}}}`;
    expect((await post(booted, raw)).status).toBe(WRITE_ERRORS.validation.status);
    expect(booted.service.writePath.tasksRead.listRecords(OWNER_ACCOUNT_ID)).toEqual([]);
  });

  /**
   * The `write_id` grammar is lowercase hex. An uppercase one is a DIFFERENT
   * key, not the same key spelled loudly — and a route that accepted it
   * case-insensitively would give one op two idempotency keys.
   */
  test("an uppercase write_id is validation, not a second spelling of the same key", async () => {
    const booted = boot();
    await cutOver(booted);
    expect((await post(booted, envelope({ writeId: "A".repeat(64), op: create("t") }))).status)
      .toBe(WRITE_ERRORS.validation.status);
  });

  test("a non-integer or unsafe account_epoch is validation and never reaches the fence", async () => {
    const booted = boot();
    await cutOver(booted);
    for (const epoch of [7.5, 9007199254740993, -1, "seven"]) {
      const response = await post(booted, envelope({ writeId: hex("a4"), epoch, op: create("t") }));
      expect({ epoch, status: response.status })
        .toEqual({ epoch, status: WRITE_ERRORS.validation.status });
    }
  });

  /**
   * Over the contract's own limit. The interesting property is not that it is
   * refused — it is that it is refused as VALIDATION rather than crashing the
   * handler, because a 500 on a large body is a denial-of-service surface with
   * a stack trace attached.
   */
  test("a body over the ratified size limit is validation, not a 500", async () => {
    const booted = boot();
    await cutOver(booted);
    const oversize = envelope({
      writeId: hex("a5"),
      op: create("t", { blob: "x".repeat(MAX_WRITE_ENVELOPE_JSON_CODE_UNITS + 100_000) }),
    });
    expect(oversize.length).toBeGreaterThan(MAX_WRITE_ENVELOPE_JSON_CODE_UNITS);
    const response = await post(booted, oversize);
    expect(response.status).toBe(WRITE_ERRORS.validation.status);
    expect(response.text).toBe(WRITE_ERRORS.validation.body);
  });

  /**
   * FOUND A REAL DEFECT, and it is the one this whole file exists for.
   *
   * A 20,000-deep array nested inside the field bag PASSED the ratified
   * contract's `parseWriteOpEnvelopeJson` — whose own recursion sits inside a
   * `try`, so an overflow there is merely a rejection — and then overflowed the
   * stack inside the registry's fingerprint, where nothing was catching it. The
   * route answered **500**. Two recursive verifiers at different points in the
   * call stack do not fail at the same depth, so "the contract's parser will
   * stop it" was never a property, just a coincidence of stack budget.
   *
   * Fixed two ways, because the input and the class are different problems: an
   * explicit iterative depth bound answered as `validation`, and a top-level
   * guard on the handler so no client input can produce an unhandled failure.
   *
   * red-proof: remove the `exceedsFingerprintDepth` check in `tasks-ops.ts`.
   * APPLIED AND OBSERVED RED — 500, and `internalErrors: 1`.
   */
  test("deeply nested JSON is validation, not a 500 — and nothing reaches the guard", async () => {
    const booted = boot();
    await cutOver(booted);
    const run = `deep-${crypto.randomUUID()}`;
    const deep = `{"write_id":"${hex("a6")}","account_epoch":7,"domain":"tasks","op":{"op":"create","record_id":"t","content":{"v":${"[".repeat(20_000)}${"]".repeat(20_000)}}}}`;
    const response = await booted.service.app.request("/v1/tasks/ops", {
      method: "POST",
      headers: { authorization: booted.auth, "content-type": "application/json", "x-omi-run-id": run },
      body: deep,
    });
    expect(response.status).toBe(WRITE_ERRORS.validation.status);
    expect(await response.text()).toBe(WRITE_ERRORS.validation.body);
    // The guard did not fire: this is a refusal the route MEANT, not a crash it
    // caught. Those are different facts and the counter keeps them apart.
    expect(booted.service.writePath.opsCounter.tally(run))
      .toMatchObject({ outcomes: { validation: 1 }, internalErrors: 0 });
  });

  /**
   * The bound is a bound, not a ban on structure: one level under it is
   * ordinary data and must still apply.
   */
  test("a field bag just under the depth bound is applied normally", async () => {
    const booted = boot();
    await cutOver(booted);
    let nested: unknown = "leaf";
    for (let level = 0; level < 60; level += 1) nested = { v: nested };
    const response = await post(booted, envelope({ writeId: hex("a7"), op: create("deep-ok", { nested: nested as Record<string, unknown> }) }));
    expect(response.status).toBe(200);
    expect(booted.service.writePath.tasksRead.readRecord(OWNER_ACCOUNT_ID, "deep-ok")).not.toBeNull();
  });
});

describe("the opaque field bag is opaque, including for keys that mean something to JavaScript", () => {
  /**
   * R6 says the bag is opaque. That is a claim about semantics, and it has a
   * security edge: `__proto__` arriving as an object key, then flowing through
   * a spread merge in the store, is the ordinary prototype-pollution shape.
   *
   * red-proof: change the store's merge from `{ ...current, ...patch }` (which
   * DEFINES own properties) to a `for (const key in patch) target[key] = …`
   * assignment loop (which goes through setters). APPLIED, AND IT TAUGHT
   * SOMETHING: the first version of this test STAYED GREEN under that mutation,
   * because the assignment form does not pollute `Object.prototype` — it
   * retargets the merged object's OWN prototype through the `__proto__` setter.
   * Global pollution and per-object prototype substitution are different
   * failures, and the assertion only covered the first. The prototype identity
   * check below was added for the second, and the mutation then goes red.
   */
  test("a __proto__ key in a patch pollutes neither Object.prototype nor the stored record", async () => {
    const booted = boot();
    await cutOver(booted);
    await post(booted, envelope({ writeId: hex("b1"), op: create("pp", { ok: 1 }) }));
    const raw = `{"write_id":"${hex("b2")}","account_epoch":7,"domain":"tasks","op":{"op":"patch","record_id":"pp","patch":{"__proto__":{"polluted":"yes"},"ok":2}}}`;
    expect((await post(booted, raw)).status).toBe(200);

    expect(({} as Record<string, unknown>)["polluted"]).toBeUndefined();
    expect(Object.prototype).not.toHaveProperty("polluted");

    // The stored bag is an ORDINARY object. A merge that assigned through the
    // `__proto__` setter would leave this record with a substituted prototype
    // carrying invisible inherited keys — data nobody can see in the bag and
    // nobody serialises, which is a worse shape than a visible wrong value.
    const stored = booted.service.writePath.tasksRead.readRecord(OWNER_ACCOUNT_ID, "pp")?.content;
    expect(Object.getPrototypeOf(stored)).toBe(Object.prototype);
    expect(stored).toEqual({ ok: 2, __proto__: { polluted: "yes" } });
  });

  test("keys named constructor and toString are stored as ordinary data", async () => {
    const booted = boot();
    await cutOver(booted);
    expect((await post(booted, envelope({
      writeId: hex("b3"), op: create("ck", { constructor: "x", toString: "y" }),
    }))).status).toBe(200);
    expect(booted.service.writePath.tasksRead.readRecord(OWNER_ACCOUNT_ID, "ck")?.content)
      .toEqual({ constructor: "x", toString: "y" });
  });
});

describe("idempotency under concurrency", () => {
  /**
   * THE ONE THAT WOULD BE INVISIBLE. Eight identical envelopes dispatched
   * together: the registry lookup, the apply and the record must not be
   * separable by an interleaving, or one op applies twice and the second apply
   * is reported to the user as a success it did not ask for.
   *
   * The route's handler is synchronous from `registry.lookup` through
   * `registry.record` — there is no `await` between them, which is what closes
   * the window. That is easy to break by adding an innocuous `await` later, and
   * nothing else in the suite would notice.
   *
   * red-proof: insert `await Bun.sleep(0);` between the registry lookup and the
   * APPLY in `tasks-ops.ts`. APPLIED AND OBSERVED RED.
   *
   * The first attempt inserted it one line earlier — BEFORE the lookup — and
   * STAYED GREEN, correctly: a suspension before the lookup suspends the whole
   * critical section together and never interleaves two of them. Recorded
   * because it is the difference between "this test detects an await" and "this
   * test detects an await IN THE WINDOW", and only the second is the property.
   */
  test("eight concurrent identical envelopes apply exactly once", async () => {
    const booted = boot();
    await cutOver(booted);
    const bytes = envelope({ writeId: hex("c1"), op: create("conc-1", { n: 1 }) });

    const responses = await Promise.all(Array.from({ length: 8 }, () => post(booted, bytes)));
    const bodies = responses.map((response) => JSON.parse(response.text) as { idempotent: boolean; applied: { revision: string } });

    expect(responses.every((response) => response.status === 200)).toBe(true);
    // Exactly one apply, seven replays answered from the recorded outcome.
    expect(bodies.filter((body) => body.idempotent === false)).toHaveLength(1);
    // And they all report the SAME revision — a second apply would advance it.
    expect(new Set(bodies.map((body) => body.applied.revision)).size).toBe(1);
    expect(booted.service.writePath.tasksRead.listRecords(OWNER_ACCOUNT_ID)).toHaveLength(1);
  });
});

describe("no response difference tells an unauthenticated caller anything", () => {
  /**
   * `backend:ADR-012` §4: account existence must not be probeable through
   * response differences. The route family is public contract, so learning that
   * `/v1/{domain}/ops` exists is not a leak — learning anything about an
   * ACCOUNT would be. An unauthenticated caller must therefore get one answer
   * for every domain, writable or not.
   *
   * red-proof: move the envelope validation above the authentication block in
   * `tasks-ops.ts`. APPLIED AND OBSERVED RED — `/v1/zzz/ops` and
   * `/v1/tasks/ops` then answered differently to a caller with no credential.
   */
  test("every domain path answers one byte-identical refusal without a credential", async () => {
    const booted = boot();
    await cutOver(booted);
    const answers = new Set<string>();
    for (const path of ["/v1/tasks/ops", "/v1/zzz/ops", "/v1/memories/ops"]) {
      const response = await post(booted, "{}", path, "");
      answers.add(`${response.status} ${response.text}`);
    }
    expect(answers.size).toBe(1);
    expect([...answers][0])
      .toBe(`${WRITE_REFUSALS.authentication.status} ${WRITE_REFUSALS.authentication.body}`);
  });
});

describe("base_revision cannot be borrowed from another record", () => {
  /**
   * A revision is a point in ONE record's history. If a revision from record A
   * satisfied a precondition on record B, `base_revision` would stop being a
   * lost-update check and become a token anyone holding any revision could use.
   *
   * red-proof: in the store's `preconditionHolds`, compare against any record's
   * revision rather than this one's. APPLIED AND OBSERVED RED.
   */
  test("a revision from another record does not satisfy the precondition", async () => {
    const booted = boot();
    await cutOver(booted);
    const first = await post(booted, envelope({ writeId: hex("d1"), op: create("x1", { a: 1 }) }));
    await post(booted, envelope({ writeId: hex("d2"), op: create("x2", { a: 1 }) }));
    const foreign = JSON.parse(first.text).applied.revision as string;

    const borrowed = await post(booted, envelope({
      writeId: hex("d3"),
      op: { op: "patch", record_id: "x2", patch: { a: 2 }, base_revision: foreign },
    }));
    expect(borrowed.status).toBe(WRITE_ERRORS.conflict.status);
    expect(borrowed.text).toBe(WRITE_ERRORS.conflict.body);
  });

  /**
   * Two records created with identical content must not share a revision — if
   * they did, the borrowed-revision case above would be reachable by accident
   * rather than by attack.
   */
  test("identical content in two records produces different revisions", async () => {
    const booted = boot();
    await cutOver(booted);
    await post(booted, envelope({ writeId: hex("e1"), op: create("y1", { same: true }) }));
    await post(booted, envelope({ writeId: hex("e2"), op: create("y2", { same: true }) }));
    const revisions = booted.service.writePath.tasksRead.listRecords(OWNER_ACCOUNT_ID)
      .map((record) => record.revision);
    expect(revisions).toHaveLength(2);
    expect(new Set(revisions).size).toBe(2);
  });
});
