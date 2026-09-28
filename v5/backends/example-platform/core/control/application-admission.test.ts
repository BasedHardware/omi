import { describe, expect, test } from "bun:test";

import type {
  AccountControlProjection,
  AccountGeneration,
  AccountLifecycleState,
} from "./account-control";
import {
  evaluateAccountControlAdmission,
  type AccountControlAdmissionReason,
} from "./application-admission";
import { evaluateWriteFence } from "./write-fence";

const ACCOUNT = "acct-application-admission-fixture";

const projection = (
  overrides: Partial<AccountControlProjection> = {},
): AccountControlProjection => ({
  account_id: ACCOUNT,
  control_revision: 9,
  account_generation: "new" as AccountGeneration,
  account_epoch: 4,
  lifecycle_state: "active" as AccountLifecycleState,
  deletion_epoch: null,
  activation: { activated_epoch: 4, at_control_revision: 9 },
  conflict: null,
  ...overrides,
});

const denied: readonly (readonly [
  string,
  AccountControlProjection | null,
  AccountControlAdmissionReason,
])[] = [
  ["missing", null, "control_state_absent"],
  ["conflicting", projection({
    conflict: { at_control_revision: 10, detail: "conflicting_observation" },
  }), "control_state_conflicting"],
  ["legacy", projection({ account_generation: "legacy" }), "account_generation_legacy"],
  ["migrating", projection({ account_generation: "migrating" }), "account_generation_migrating"],
  ["stranded", projection({
    account_generation: "rolled_back_stranded",
  }), "account_generation_rolled_back_stranded"],
  ["epoch absent", projection({ account_epoch: null }), "control_state_not_activated"],
  ["activation absent", projection({ activation: null }), "control_state_not_activated"],
  ["activation mismatch", projection({
    activation: { activated_epoch: 3, at_control_revision: 9 },
  }), "control_state_not_activated"],
];

describe("single-control application admission", () => {
  test("admits only active activated-new authority and returns no owner coordinate", () => {
    const decision = evaluateAccountControlAdmission(projection());
    expect(decision).toEqual({ admitted: true, account_epoch: 4 });
    expect(Object.isFrozen(decision)).toBe(true);
    expect(JSON.stringify(decision)).not.toContain(ACCOUNT);
  });

  for (const [label, candidate, reason] of denied) {
    test(`${label} control denies with ${reason}`, () => {
      const decision = evaluateAccountControlAdmission(candidate);
      expect(decision).toEqual({ admitted: false, reason });
      expect(Object.isFrozen(decision)).toBe(true);
      expect(JSON.stringify(decision)).not.toContain(ACCOUNT);
      expect(JSON.stringify(decision)).not.toContain("conflicting_observation");
    });
  }

  test("lifecycle dominates every generation and activation permutation", () => {
    const generations: readonly AccountGeneration[] = [
      "legacy", "migrating", "new", "rolled_back_stranded",
    ];
    const activations: readonly AccountControlProjection["activation"][] = [
      null,
      { activated_epoch: 3, at_control_revision: 8 },
      { activated_epoch: 4, at_control_revision: 9 },
    ];
    for (const lifecycle of ["deletion_pending", "deleted"] as const) {
      for (const accountGeneration of generations) {
        for (const activation of activations) {
          expect(evaluateAccountControlAdmission(projection({
            lifecycle_state: lifecycle,
            deletion_epoch: 31,
            account_generation: accountGeneration,
            activation,
          }))).toEqual({ admitted: false, reason: "account_lifecycle_not_active" });
        }
      }
    }
  });

  test("the decision is deterministic and detached from later projection mutation", () => {
    const mutable = projection();
    const first = evaluateAccountControlAdmission(mutable);
    const bytes = JSON.stringify(first);
    (mutable as { account_epoch: number | null }).account_epoch = 99;
    (mutable as { lifecycle_state: AccountLifecycleState }).lifecycle_state = "deleted";
    expect(JSON.stringify(first)).toBe(bytes);
    expect(evaluateAccountControlAdmission(projection())).toEqual(first);
  });
});

describe("write fence compatibility", () => {
  test("common control denials retain their exact existing write mapping", () => {
    for (const [, candidate, reason] of denied) {
      const decision = evaluateWriteFence(candidate, { request_epoch: 4 });
      expect(decision).toEqual({
        admitted: false,
        outcome: "control_unavailable",
        reason,
        evidence: "record_nothing",
      });
    }
    for (const lifecycle of ["deletion_pending", "deleted"] as const) {
      expect(evaluateWriteFence(projection({
        lifecycle_state: lifecycle,
        deletion_epoch: 31,
      }), { request_epoch: 4 })).toEqual({
        admitted: false,
        outcome: "authorization",
        reason: "account_lifecycle_not_active",
        evidence: "record_nothing",
      });
    }
  });

  test("request epoch handling begins only after common control admission", () => {
    expect(evaluateWriteFence(projection(), { request_epoch: null })).toEqual({
      admitted: false,
      outcome: "stale_epoch",
      reason: "request_epoch_absent",
      evidence: "record_nothing",
    });
    expect(evaluateWriteFence(projection(), { request_epoch: 3 })).toEqual({
      admitted: false,
      outcome: "stale_epoch",
      reason: "request_epoch_behind",
      evidence: "preserve_envelope",
    });
    expect(evaluateWriteFence(projection(), { request_epoch: 4 }))
      .toEqual({ admitted: true, account_epoch: 4 });
    expect(evaluateWriteFence(projection(), { request_epoch: 5 })).toEqual({
      admitted: false,
      outcome: "stale_epoch",
      reason: "request_epoch_ahead",
      evidence: "record_nothing",
    });
  });
});
