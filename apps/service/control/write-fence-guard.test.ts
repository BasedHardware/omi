import { describe, expect, test } from "bun:test";

import type { AccountControlObservation } from "../../../core/control/account-control";
import { createWriteFenceCounter, UNATTRIBUTED_RUN } from "./fence-counter";
import { WRITE_FENCE_REFUSALS, writeFenceRefusalResponse } from "./fence-http";
import { createInMemoryAccountControlProjectionStore } from "./projection-store";
import { applyWriteFence } from "./write-fence-guard";

const ACCOUNT = "acct-guard-unit-fixture";

const observation = (
  overrides: Partial<AccountControlObservation> = {},
): AccountControlObservation => ({
  account_id: ACCOUNT,
  control_revision: 1,
  account_generation: "legacy",
  account_epoch: null,
  lifecycle_state: "active",
  deletion_epoch: null,
  ...overrides,
});

const liveStore = () => {
  const store = createInMemoryAccountControlProjectionStore();
  store.observe(observation());
  store.observe(observation({ control_revision: 2, account_generation: "migrating" }));
  store.observe(observation({ control_revision: 3, account_generation: "new", account_epoch: 7 }));
  const activated = store.activate(ACCOUNT, { epoch: 7, at_control_revision: 3 });
  expect(activated.activated).toBe(true);
  return store;
};

describe("the store denies for an account it has never been told about", () => {
  test("an unknown account has no projection and the fence denies", () => {
    const store = createInMemoryAccountControlProjectionStore();
    expect(store.read("acct-never-heard-of")).toBeNull();
    const decision = applyWriteFence(
      { store, counter: createWriteFenceCounter() },
      { accountId: "acct-never-heard-of", requestEpoch: 7, runId: "r" },
    );
    expect(decision).toMatchObject({ admitted: false, reason: "control_state_absent" });
  });
});

describe("a rejected observation still changes the row when it poisons", () => {
  /**
   * The failure this pins is a plausible one-line "cleanup": returning early on
   * `!result.accepted` in `observe`. Every pure-function test in
   * `core/control/account-control.test.ts` stays green under that mutation,
   * because the poison is in the returned value — it is only the STORE that
   * would drop it, and the fence would then keep serving from the last healthy
   * row while a conflicting observation sat unrecorded.
   *
   * red-proof: add `if (!result.accepted) return result;` before `rows.set(...)`
   * in `projection-store.ts`. This goes red; nothing in core/ does.
   */
  test("a conflicting observation persists the poison and stops writes", () => {
    const store = liveStore();
    const counter = createWriteFenceCounter();
    expect(applyWriteFence({ store, counter }, { accountId: ACCOUNT, requestEpoch: 7, runId: "r1" }).admitted)
      .toBe(true);

    const conflicting = store.observe(observation({
      control_revision: 3, account_generation: "new", account_epoch: 99,
    }));
    expect(conflicting.accepted).toBe(false);
    expect(store.read(ACCOUNT)?.conflict).not.toBeNull();

    expect(applyWriteFence({ store, counter }, { accountId: ACCOUNT, requestEpoch: 7, runId: "r1" }))
      .toMatchObject({ admitted: false, reason: "control_state_conflicting" });
  });

  test("a stale redelivery does not poison and writes continue", () => {
    const store = liveStore();
    const stale = store.observe(observation({ control_revision: 2, account_generation: "migrating" }));
    expect(stale).toMatchObject({ accepted: false, reason: "stale_observation" });
    expect(store.read(ACCOUNT)?.conflict).toBeNull();
    expect(applyWriteFence(
      { store, counter: createWriteFenceCounter() },
      { accountId: ACCOUNT, requestEpoch: 7, runId: "r" },
    ).admitted).toBe(true);
  });
});

describe("the producer-side counter is keyed by run and derived from the decision", () => {
  /**
   * red-proof: in `write-fence-guard.ts`, move `counter.record(...)` ABOVE the
   * `evaluateWriteFence` call and pass a synthesised admitted decision — the
   * dispatch-side shape STATE.md forbids. The tallies below then report an
   * admission for the stale write and this goes red.
   */
  test("tallies separate runs and count the outcome the fence produced", () => {
    const store = liveStore();
    const counter = createWriteFenceCounter();
    const dependencies = { store, counter };

    applyWriteFence(dependencies, { accountId: ACCOUNT, requestEpoch: 7, runId: "run-a" });
    applyWriteFence(dependencies, { accountId: ACCOUNT, requestEpoch: 6, runId: "run-a" });
    applyWriteFence(dependencies, { accountId: ACCOUNT, requestEpoch: 6, runId: "run-b" });

    expect(counter.tally("run-a")).toEqual({
      admitted: 1,
      refused: {
        authentication: 0, authorization: 0, entitlement: 0,
        stale_epoch: 1, control_unavailable: 0,
      },
      preservedEnvelopes: 1,
    });
    expect(counter.tally("run-b")?.refused.stale_epoch).toBe(1);
    // A run that produced no decision is null, never an all-zero tally that
    // reads as "measured, and nothing happened".
    expect(counter.tally("run-c")).toBeNull();
  });

  test("a missing run id is bucketed visibly rather than dropped", () => {
    const store = liveStore();
    const counter = createWriteFenceCounter();
    applyWriteFence({ store, counter }, { accountId: ACCOUNT, requestEpoch: 6, runId: undefined });
    applyWriteFence({ store, counter }, { accountId: ACCOUNT, requestEpoch: 6, runId: "  " });
    expect(counter.tally(UNATTRIBUTED_RUN)?.refused.stale_epoch).toBe(2);
  });
});

describe("the reference HTTP binding keeps the four outcome classes distinguishable", () => {
  /**
   * `backend:ADR-010` §3 amends ADR-004 §4 precisely because 401 and 403 were
   * mapped together onto re-authentication. The status code alone is therefore
   * NOT sufficient — authorization and entitlement share 403 — which is why the
   * ADR requires "a shared status class [that] carries the outcome".
   *
   * red-proof: drop `refusal_outcome` from the body in `fence-http.ts`. The
   * authorization and entitlement bodies become byte-identical and this goes red.
   */
  test("every outcome is distinguishable from every other on the wire", () => {
    const wires = Object.entries(WRITE_FENCE_REFUSALS);
    const seen = new Set<string>();
    for (const [outcome, wire] of wires) {
      const key = `${wire.status}|${wire.body}`;
      expect(seen.has(key)).toBe(false);
      seen.add(key);
      expect(JSON.parse(wire.body).refusal_outcome).toBe(outcome);
    }
    expect(seen.size).toBe(5);
    // Status alone would collapse authorization and entitlement.
    expect(WRITE_FENCE_REFUSALS.authorization.status)
      .toBe(WRITE_FENCE_REFUSALS.entitlement.status);
  });

  test("no refusal body carries a reason, an epoch or an account identifier", () => {
    const store = liveStore();
    const counter = createWriteFenceCounter();
    const decision = applyWriteFence(
      { store, counter },
      { accountId: ACCOUNT, requestEpoch: 6, runId: "leak-check" },
    );
    const response = writeFenceRefusalResponse(decision);
    expect(response.status).toBe(409);
    const body = WRITE_FENCE_REFUSALS.stale_epoch.body;
    expect(Object.keys(JSON.parse(body)).sort()).toEqual(["error", "refusal_outcome"]);
    for (const secret of [ACCOUNT, "request_epoch_behind", "7", "6"]) {
      expect(body).not.toContain(secret);
    }
  });

  test("an admitted decision has no refusal response", () => {
    expect(() => writeFenceRefusalResponse({ admitted: true, account_epoch: 7 })).toThrow(TypeError);
  });
});
