/**
 * ⚠ KNOWN DEFECTS, ESCALATED AND UNRULED. **NOTHING HERE IS DESIRED BEHAVIOUR.**
 *
 * Read `data/run-2026-08-09/blocked/OPS-b1-idempotency-and-b5-gc-disagree-across-an-epoch-boundary.md`
 * before you read the assertions. This file executes two behaviours that are
 * currently WRONG in ways no lane is entitled to fix at night, and it exists so
 * that they are reproducible, visible, and impossible to change by accident
 * while the escalation is open.
 *
 * ── WHY PIN A DEFECT AT ALL, GIVEN W4 ───────────────────────────────────────
 *
 * This repo has already paid for a test that PINNED a defect instead of
 * catching it: the cross-side test held the raw-row-id leak in place, and every
 * assertion passed the whole time the door was wrong. The thing that made that
 * dangerous was not the pinning — it was that nothing said so. A pin nobody can
 * mistake for a specification is a record; a pin that reads like a
 * specification is a trap.
 *
 * So: this file is named `known-defect`, every test name says what is wrong,
 * and each assertion is written as "today this happens, and that is the bug".
 * When the escalation is ruled, this file is deleted or inverted by whoever
 * implements the ruling — it is not evidence that the behaviour was accepted.
 */

import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { WRITE_ERRORS, WRITE_REFUSALS } from "@omi-core/ratified-contracts/write/ops";

import { createLocalDevService, type LocalService } from "../app-facing";

const OWNER_ACCOUNT_ID = "local-dev-user";
const EPOCH = 7;

interface Booted { readonly service: LocalService; readonly auth: string }

const boot = (): Booted => {
  const service = createLocalDevService({
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

const post = async (booted: Booted, body: string): Promise<{ status: number; text: string }> => {
  const response = await booted.service.app.request("/v1/tasks/ops", {
    method: "POST",
    headers: { authorization: booted.auth, "content-type": "application/json" },
    body,
  });
  return { status: response.status, text: await response.text() };
};

const hex = (seed: string): string => seed.padEnd(64, "0").replace(/[^0-9a-f]/g, "0").slice(0, 64);

describe("⚠ DEFECT 1 — a crash-replay across an epoch advance is reported as a permanent failure for an edit that APPLIED", () => {
  /**
   * B1 exists to make one sentence true: "opId idempotency on the server
   * absorbs the replay." B5 collects the registry row at an epoch advance,
   * correctly, on the argument that the fence will refuse every later replay.
   * Both are ruled. Together they produce this.
   *
   * There is no red-proof on this test, deliberately: it asserts a defect, and
   * a mutation that made it go red would be a FIX — which is the escalation
   * nobody may apply tonight. What the test protects is that the defect cannot
   * change shape silently while the ruling is pending.
   */
  test("the replayed envelope is refused stale_epoch while its record sits in the store", async () => {
    const booted = boot();
    await cutOver(booted);

    const envelope = JSON.stringify({
      write_id: hex("aa"), account_epoch: EPOCH, domain: "tasks",
      op: { op: "create", record_id: "prescription", content: { title: "Pick up prescription for Mum" } },
    });

    const applied = await post(booted, envelope);
    expect(applied.status).toBe(200);
    const record = JSON.parse(applied.text).applied as { record_id: string; revision: string };

    // The epoch advances. B5's GC collects the row that would have answered the
    // replay — and reports that it did, which is the ruling working correctly.
    await control(booted, "/v1/qa/control/observe", observation({
      control_revision: 4, account_generation: "new", account_epoch: EPOCH + 1,
    }));
    expect(await control(booted, "/v1/qa/control/activate", { epoch: EPOCH + 1, at_control_revision: 4 }))
      .toMatchObject({ activated: true, write_id_rows_collected: 1 });

    // The client crashed before its tombstone, so it replays the same journaled
    // bytes. THIS IS THE DEFECT: a permanent, never-retryable refusal.
    const replay = await post(booted, envelope);
    expect(replay.status).toBe(WRITE_REFUSALS.stale_epoch.status);
    expect(replay.text).toBe(WRITE_REFUSALS.stale_epoch.body);

    // …for an edit that is in the record, unchanged.
    expect(booted.service.writePath.tasksRead.readRecord(OWNER_ACCOUNT_ID, "prescription"))
      .toMatchObject({ revision: record.revision });
  });

  /**
   * The second half, and the one that reaches a person: the server retains the
   * envelope as a straggler — a row whose whole meaning under B3 is "this edit
   * was refused and this is the only surviving copy" — about an edit that is
   * neither refused nor uniquely held. The client renders David's signed copy
   * on this outcome and invites the user to paste the edit back in, which
   * would DUPLICATE it.
   */
  test("the server retains a lost-edit record for an edit that was not lost", async () => {
    const booted = boot();
    await cutOver(booted);
    const envelope = JSON.stringify({
      write_id: hex("bb"), account_epoch: EPOCH, domain: "tasks",
      op: { op: "create", record_id: "prescription", content: { title: "Pick up prescription for Mum" } },
    });
    await post(booted, envelope);
    await control(booted, "/v1/qa/control/observe", observation({
      control_revision: 4, account_generation: "new", account_epoch: EPOCH + 1,
    }));
    await control(booted, "/v1/qa/control/activate", { epoch: EPOCH + 1, at_control_revision: 4 });
    await post(booted, envelope);

    const preserved = booted.service.writePath.stragglers.exportAccount(OWNER_ACCOUNT_ID);
    expect(preserved).toHaveLength(1);
    expect(preserved[0]?.envelope_json).toContain("Pick up prescription for Mum");
    // And the "lost" edit is right here.
    expect(booted.service.writePath.tasksRead.readRecord(OWNER_ACCOUNT_ID, "prescription")).not.toBeNull();
  });
});

describe("⚠ DEFECT 1b — after the GC, the same write_id re-stamped at the new epoch applies AGAIN", () => {
  /**
   * THE THIRD FACE OF THE SAME CAUSE, and the opposite direction from Defect 1.
   *
   * R18's corrected premise is that a registry row does two jobs: answer a
   * replay idempotently, and witness that an op applied. It does a third — it is
   * the only witness that a `write_id` was ever USED, and therefore the only
   * thing that can tell a laundered key from a legitimate one.
   *
   * Defect 1 is a false FAILURE: old-epoch bytes replayed after the advance are
   * told permanently that an applied edit failed. This is a false SUCCESS: the
   * same key re-stamped at the NEW epoch with DIFFERENT content is accepted and
   * applied, where the un-collected path answers `409 write_id_reuse`. Same
   * cause — B5's collection destroys the evidence — opposite consequence.
   *
   * Why it matters to the amendment rather than as another complaint: a horizon
   * that retains only "was this op applied?" closes Defect 1 and leaves this one
   * standing. **The retained thing has to be the fingerprint, not just the
   * outcome.** Within-horizon, both answers are existing wire values —
   * `accepted_idempotent` for same key + same fingerprint, `write_id_reuse` for
   * same key + different fingerprint — so no enum and no copy moves.
   *
   * Added under R18-A, at fable's instruction, including the pre-GC control it
   * asked for: without that control this test cannot distinguish "the GC broke
   * reuse detection" from "reuse detection never worked".
   */
  const laundered = (writeId: string, epoch: number, title: string): string => JSON.stringify({
    write_id: writeId, account_epoch: epoch, domain: "tasks",
    op: { op: "create", record_id: "launder", content: { title } },
  });

  /**
   * THE CONTROL. Same key, different content, SAME epoch — no GC has happened,
   * the row is still there, and the reuse check does its job. If this ever goes
   * red, the test below is measuring a broken reuse check rather than the GC.
   */
  test("CONTROL — before any epoch advance, the same write_id with different content is refused", async () => {
    const booted = boot();
    await cutOver(booted);
    const key = hex("cc");

    expect((await post(booted, laundered(key, EPOCH, "first"))).status).toBe(200);
    const reuse = await post(booted, laundered(key, EPOCH, "second-laundered"));

    expect(reuse.status).toBe(WRITE_ERRORS.write_id_reuse.status);
    expect(reuse.text).toBe(WRITE_ERRORS.write_id_reuse.body);
    // Nothing was laundered in.
    expect(booted.service.writePath.tasksRead.readRecord(OWNER_ACCOUNT_ID, "launder")?.content)
      .toEqual({ title: "first" });
  });

  /**
   * THE DEFECT. Identical to the control except that the epoch advances in
   * between — which is the only difference, and it flips a 409 into a 200.
   */
  test("after the epoch advance collects the row, the same key launders different content in", async () => {
    const booted = boot();
    await cutOver(booted);
    const key = hex("dd");

    expect((await post(booted, laundered(key, EPOCH, "first"))).status).toBe(200);

    await control(booted, "/v1/qa/control/observe", observation({
      control_revision: 4, account_generation: "new", account_epoch: EPOCH + 1,
    }));
    // B5's GC, executing correctly, reports exactly what it destroyed.
    expect(await control(booted, "/v1/qa/control/activate", { epoch: EPOCH + 1, at_control_revision: 4 }))
      .toMatchObject({ activated: true, write_id_rows_collected: 1 });

    const relaunder = await post(booted, laundered(key, EPOCH + 1, "second-laundered"));

    // THE DEFECT: 200, not 409. The control above proves the reuse check works.
    expect(relaunder.status).toBe(200);
    expect(JSON.parse(relaunder.text).idempotent).toBe(false);
    // And the laundered content is now the record.
    expect(booted.service.writePath.tasksRead.readRecord(OWNER_ACCOUNT_ID, "launder")?.content)
      .toEqual({ title: "second-laundered" });
  });
});

describe("⚠ DEFECT 2 — the straggler table has no size bound", () => {
  /**
   * Every bound on this table is a rule about destroying a user's only
   * surviving copy of an edit they wrote, and B3's premise is that a summary
   * does not satisfy the retention. Fable declined to sign the retention
   * WINDOW for this record class; a SIZE bound is the same class of decision
   * and has no signature. So it is measured here and ruled nowhere.
   *
   * The only bound that exists is David's 90-day cap, and nothing schedules the
   * sweeper that would enforce it.
   */
  test("every byte of every refused envelope is retained, with no cap on count or size", async () => {
    const booted = boot();
    await cutOver(booted);

    let sent = 0;
    for (const seed of ["e1", "e2", "e3"]) {
      const envelope = JSON.stringify({
        write_id: hex(seed), account_epoch: EPOCH - 1, domain: "tasks",
        op: { op: "patch", record_id: "t", patch: { blob: "y".repeat(100_000) } },
      });
      sent += envelope.length;
      expect((await post(booted, envelope)).status).toBe(WRITE_REFUSALS.stale_epoch.status);
    }

    const preserved = booted.service.writePath.stragglers.exportAccount(OWNER_ACCOUNT_ID);
    const retained = preserved.reduce((total, row) => total + row.envelope_json.length, 0);
    expect(preserved).toHaveLength(3);
    expect(retained).toBe(sent);
  });
});
