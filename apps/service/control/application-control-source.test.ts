import { describe, expect, test } from "bun:test";

import type { AccountControlProjection } from "../../../core/control/account-control";
import {
  inspectApplicationAccountControl,
  type ApplicationAccountControlSource,
  type ApplicationControlSourceReason,
} from "./application-control-source";

const ACCOUNT = "acct-control-source";

const projection = (
  overrides: Partial<AccountControlProjection> = {},
): AccountControlProjection => ({
  account_id: ACCOUNT,
  control_revision: 12,
  account_generation: "new",
  account_epoch: 7,
  lifecycle_state: "active",
  deletion_epoch: null,
  activation: { activated_epoch: 7, at_control_revision: 12 },
  conflict: null,
  ...overrides,
});

const sourceOf = (result: unknown, calls = { value: 0 }): ApplicationAccountControlSource => ({
  async load(accountId: string): Promise<unknown> {
    calls.value += 1;
    expect(accountId).toBe(ACCOUNT);
    return result;
  },
});

describe("coherent application account-control source", () => {
  test("one current activated-new observation emits only owner-free binding coordinates", async () => {
    const calls = { value: 0 };
    const result = await inspectApplicationAccountControl(sourceOf({
      status: "current",
      projection: projection(),
    }, calls), ACCOUNT);

    expect(calls.value).toBe(1);
    expect(result).toEqual({
      admitted: true,
      account_epoch: 7,
      control_revision: 12,
      destination_activation_revision: 12,
    });
    expect(Object.isFrozen(result)).toBe(true);
    expect(JSON.stringify(result)).not.toContain(ACCOUNT);
  });

  test("closed non-current states and source failures each deny after one call", async () => {
    const rows: readonly [unknown, ApplicationControlSourceReason][] = [
      [{ status: "absent" }, "control_state_absent"],
      [{ status: "stale" }, "control_source_stale"],
      [{ status: "unavailable" }, "control_source_unavailable"],
    ];
    for (const [raw, reason] of rows) {
      const calls = { value: 0 };
      expect(await inspectApplicationAccountControl(sourceOf(raw, calls), ACCOUNT))
        .toEqual({ admitted: false, reason });
      expect(calls.value).toBe(1);
    }

    const sentinel = "raw provider or database detail";
    for (const load of [
      () => { throw new Error(sentinel); },
      () => Promise.reject(new Error(sentinel)),
    ]) {
      let calls = 0;
      const result = await inspectApplicationAccountControl({
        async load(): Promise<unknown> {
          calls += 1;
          return await load();
        },
      }, ACCOUNT);
      expect(calls).toBe(1);
      expect(result).toEqual({ admitted: false, reason: "control_source_unavailable" });
      expect(JSON.stringify(result)).not.toContain(sentinel);
    }
  });

  test("current control denials preserve the shared admission reason", async () => {
    const rows: readonly [Partial<AccountControlProjection>, ApplicationControlSourceReason][] = [
      [{ conflict: { at_control_revision: 12, detail: "conflicting_observation" } }, "control_state_conflicting"],
      [{ account_generation: "legacy", activation: null }, "account_generation_legacy"],
      [{ account_generation: "migrating", activation: null }, "account_generation_migrating"],
      [{
        account_generation: "rolled_back_stranded",
        activation: null,
      }, "account_generation_rolled_back_stranded"],
      [{ activation: null }, "control_state_not_activated"],
      [{ lifecycle_state: "deletion_pending", deletion_epoch: 9 }, "account_lifecycle_not_active"],
      [{ lifecycle_state: "deleted", deletion_epoch: 9 }, "account_lifecycle_not_active"],
    ];
    for (const [overrides, reason] of rows) {
      expect(await inspectApplicationAccountControl(sourceOf({
        status: "current",
        projection: projection(overrides),
      }), ACCOUNT)).toEqual({ admitted: false, reason });
    }
  });

  test("hostile or malformed current results fail content-safely", async () => {
    let statusGetterCalls = 0;
    const statusAccessor = Object.create(Object.prototype, {
      status: { enumerable: true, get: () => { statusGetterCalls += 1; return "current"; } },
      projection: { enumerable: true, value: projection() },
    });
    let accountGetterCalls = 0;
    const accountAccessor = Object.create(Object.prototype, {
      ...Object.fromEntries(Object.entries(projection()).map(([key, value]) => [key, {
        enumerable: true,
        value,
      }])),
      account_id: {
        enumerable: true,
        get: () => { accountGetterCalls += 1; return ACCOUNT; },
      },
    });
    class ProjectionClass {
      account_id = ACCOUNT;
    }
    const hostile: readonly unknown[] = [
      { status: "current", projection: { ...projection(), account_id: "other-account" } },
      { status: "current", projection: { ...projection(), extra: true } },
      statusAccessor,
      { status: "current", projection: accountAccessor },
      { status: "current", projection: new Proxy(projection(), {}) },
      { status: "current", projection: new ProjectionClass() },
      { status: "current", projection: { ...projection(), control_revision: Number.MAX_SAFE_INTEGER + 1 } },
      { status: "current", projection: { ...projection(), deletion_epoch: 2 } },
      { status: "current", projection: {
        ...projection(),
        activation: { activated_epoch: 6, at_control_revision: 12 },
      } },
      { status: "current", projection: {
        ...projection(),
        conflict: { at_control_revision: 12, detail: "raw_conflict_detail" },
      } },
      { status: "absent", projection: null },
      { status: "future" },
      new Proxy({ status: "absent" }, {}),
    ];
    for (const raw of hostile) {
      const result = await inspectApplicationAccountControl(sourceOf(raw), ACCOUNT);
      expect(result).toEqual({ admitted: false, reason: "control_source_invalid" });
      expect(JSON.stringify(result)).not.toContain("raw_conflict_detail");
    }
    expect(statusGetterCalls).toBe(0);
    expect(accountGetterCalls).toBe(0);
  });

  test("inspection detaches from the source row and freezes every result", async () => {
    const row = projection();
    const admitted = await inspectApplicationAccountControl(sourceOf({
      status: "current",
      projection: row,
    }), ACCOUNT);
    (row as { control_revision: number }).control_revision = 99;
    (row.activation as { at_control_revision: number }).at_control_revision = 99;
    expect(admitted).toEqual({
      admitted: true,
      account_epoch: 7,
      control_revision: 12,
      destination_activation_revision: 12,
    });

    const denied = await inspectApplicationAccountControl(sourceOf({ status: "stale" }), ACCOUNT);
    expect(Object.isFrozen(denied)).toBe(true);
    expect(JSON.stringify(denied)).not.toContain(ACCOUNT);
  });

  test("invalid account or dependency never invokes the source", async () => {
    let calls = 0;
    const source: ApplicationAccountControlSource = {
      async load(): Promise<unknown> {
        calls += 1;
        return { status: "absent" };
      },
    };
    expect(await inspectApplicationAccountControl(source, "bad account"))
      .toEqual({ admitted: false, reason: "control_source_invalid" });
    expect(await inspectApplicationAccountControl(new Proxy(source, {}), ACCOUNT))
      .toEqual({ admitted: false, reason: "control_source_invalid" });
    expect(calls).toBe(0);
  });
});
