import { describe, expect, test } from "bun:test";

import type {
  AccountControlProjection,
  AccountGeneration,
  AccountLifecycleState,
} from "./account-control";
import { evaluateWriteFence, type WriteFenceReason } from "./write-fence";

const ACCOUNT = "acct-fence-unit-fixture";

const projectionAt = (overrides: Partial<AccountControlProjection> = {}): AccountControlProjection => ({
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

describe("the account epoch fence admits only an op stamped with the active epoch", () => {
  test("an op at the active epoch is admitted", () => {
    const decision = evaluateWriteFence(projectionAt(), { request_epoch: 4 });
    expect(decision).toEqual({ admitted: true, account_epoch: 4 });
  });

  /**
   * red-proof: in `evaluateWriteFence`, change the straggler test from
   * `request.request_epoch < active` to `request.request_epoch < active - 1`
   * (or delete the branch entirely). An op one epoch behind is then admitted and
   * this goes red on the first assertion.
   */
  test("an op behind the active epoch is refused as stale_epoch, and its envelope is preserved", () => {
    const decision = evaluateWriteFence(projectionAt(), { request_epoch: 3 });
    expect(decision).toEqual({
      admitted: false,
      outcome: "stale_epoch",
      reason: "request_epoch_behind",
      evidence: "preserve_envelope",
    });
  });

  /**
   * `backend:ADR-010` §3's whole point. `stale_epoch` means "refresh control
   * state and retry"; `authentication` means "re-authenticate". A straggler whose
   * session is perfectly valid must never be told to re-authenticate — that is
   * the unsatisfiable loop ADR-010 amended ADR-004 §4 to prevent.
   *
   * red-proof: in `evaluateWriteFence`, return outcome `"authentication"` instead
   * of `"stale_epoch"` for `request_epoch_behind`. This goes red; the assertion
   * above goes red too, which is the point — the conflation is not expressible
   * without breaking the class.
   */
  test("a stale-epoch refusal is not an authentication refusal", () => {
    const decision = evaluateWriteFence(projectionAt(), { request_epoch: 0 });
    expect(decision.admitted).toBe(false);
    if (decision.admitted) throw new Error("unreachable");
    expect(decision.outcome).toBe("stale_epoch");
    expect(decision.outcome).not.toBe("authentication");
    expect(decision.outcome).not.toBe("authorization");
    expect(decision.outcome).not.toBe("entitlement");
  });

  /**
   * The server, not the client, is behind. Same instruction, so the same class —
   * but preserving here would manufacture a dead letter for an op that is about
   * to apply once the projection catches up.
   *
   * red-proof: give `request_epoch_ahead` `evidence: "preserve_envelope"`. This
   * goes red on the evidence assertion.
   */
  test("an op ahead of the active epoch is refused without preserving an envelope", () => {
    const decision = evaluateWriteFence(projectionAt(), { request_epoch: 5 });
    expect(decision).toEqual({
      admitted: false,
      outcome: "stale_epoch",
      reason: "request_epoch_ahead",
      evidence: "record_nothing",
    });
  });

  test("an op carrying no epoch at all is refused", () => {
    const decision = evaluateWriteFence(projectionAt(), { request_epoch: null });
    expect(decision).toEqual({
      admitted: false,
      outcome: "stale_epoch",
      reason: "request_epoch_absent",
      evidence: "record_nothing",
    });
  });
});

describe("missing, conflicting and unactivated control state all deny", () => {
  /**
   * `backend:ADR-010` §1: "Missing, stale, conflicting, or unordered control
   * state denies writes." The consequence it accepts by name: "The new backend
   * sacrifices write availability rather than guessing."
   *
   * red-proof: in `evaluateWriteFence`, replace the `projection === null` guard
   * with `if (projection === null) return { admitted: true, account_epoch: request.request_epoch ?? 0 }`.
   * This goes red — and so does the whole point of the module.
   */
  test("a missing projection denies", () => {
    const decision = evaluateWriteFence(null, { request_epoch: 4 });
    expect(decision).toEqual({
      admitted: false,
      outcome: "control_unavailable",
      reason: "control_state_absent",
      evidence: "record_nothing",
    });
  });

  /**
   * red-proof: delete the `projection.conflict !== null` guard. A poisoned
   * projection still carries a plausible generation, epoch and activation, so
   * every later check passes and the write is ADMITTED. This goes red.
   */
  test("a conflicted projection denies even though its fields look healthy", () => {
    const conflicted = projectionAt({
      conflict: { at_control_revision: 10, detail: "conflicting_observation" },
    });
    // Everything else about this row would admit.
    expect(evaluateWriteFence(projectionAt(), { request_epoch: 4 }).admitted).toBe(true);
    expect(evaluateWriteFence(conflicted, { request_epoch: 4 })).toEqual({
      admitted: false,
      outcome: "control_unavailable",
      reason: "control_state_conflicting",
      evidence: "record_nothing",
    });
  });

  /**
   * ADR-010 §1 step 4 — "The destination activates exactly that epoch." Generation
   * `new` is legacy's statement; activation is this side's. Both are required.
   *
   * red-proof: delete the activation block. The `new`-but-unactivated row then
   * admits, which is the window the rollback order exists to close.
   */
  test("generation new without a matching destination activation denies", () => {
    for (const activation of [null, { activated_epoch: 3, at_control_revision: 9 }]) {
      expect(evaluateWriteFence(projectionAt({ activation }), { request_epoch: 4 })).toEqual({
        admitted: false,
        outcome: "control_unavailable",
        reason: "control_state_not_activated",
        evidence: "record_nothing",
      });
    }
  });
});

describe("generation fences are backpressure, and none of them retains user content", () => {
  const cases: readonly (readonly [AccountGeneration, WriteFenceReason])[] = [
    ["legacy", "account_generation_legacy"],
    ["migrating", "account_generation_migrating"],
    ["rolled_back_stranded", "account_generation_rolled_back_stranded"],
  ];

  for (const [generation, reason] of cases) {
    test(`generation ${generation} denies with ${reason}`, () => {
      const decision = evaluateWriteFence(
        projectionAt({ account_generation: generation }),
        { request_epoch: 4 },
      );
      expect(decision).toEqual({
        admitted: false,
        outcome: "control_unavailable",
        reason,
        evidence: "record_nothing",
      });
    });
  }

  /**
   * The ratified migration window is "a maintenance notice, not a local buffer",
   * and the spike memo's rule is that a fenced account's refusal is recorded
   * NOWHERE — it is backpressure, not evidence. Only the straggler retains a
   * user's edit, and its retention window is still owed to David (ruling B3), so
   * widening preservation would create that record class before its policy.
   *
   * red-proof: give `account_generation_migrating` `evidence: "preserve_envelope"`.
   * This goes red.
   */
  test("exactly one refusal in the whole fence preserves an envelope", () => {
    const projections: readonly (AccountControlProjection | null)[] = [
      null,
      projectionAt({ conflict: { at_control_revision: 10, detail: "conflicting_observation" } }),
      projectionAt({ account_generation: "legacy" }),
      projectionAt({ account_generation: "migrating" }),
      projectionAt({ account_generation: "rolled_back_stranded" }),
      projectionAt({ lifecycle_state: "deletion_pending", deletion_epoch: 1 }),
      projectionAt({ lifecycle_state: "deleted", deletion_epoch: 1 }),
      projectionAt({ activation: null }),
      projectionAt(),
    ];
    const epochs: readonly (number | null)[] = [null, 0, 3, 4, 5];
    const preserved: string[] = [];
    for (const projection of projections) {
      for (const epoch of epochs) {
        const decision = evaluateWriteFence(projection, { request_epoch: epoch });
        if (!decision.admitted && decision.evidence === "preserve_envelope") {
          preserved.push(decision.reason);
        }
      }
    }
    expect([...new Set(preserved)]).toEqual(["request_epoch_behind"]);
  });
});

describe("lifecycle dominates generation", () => {
  /**
   * `backend:ADR-014` §1: "Lifecycle dominates generation ... Where lifecycle and
   * generation disagree, lifecycle wins." Its alternatives table rejects encoding
   * deletion inside the generation enum because that "makes deletion invisible to
   * paths that switch on generation" — so the test that matters is the one where
   * generation says `new`, activation is present, and the epoch matches exactly.
   * Everything about this row admits except the lifecycle.
   *
   * red-proof: move the lifecycle check BELOW the generation switch and below the
   * activation block in `evaluateWriteFence`. Both cases here then return
   * `{admitted: true}` and this goes red.
   */
  for (const lifecycle of ["deletion_pending", "deleted"] as const) {
    test(`a ${lifecycle} account denies a write that is otherwise perfectly admissible`, () => {
      const admissible = projectionAt();
      expect(evaluateWriteFence(admissible, { request_epoch: 4 }).admitted).toBe(true);

      const decision = evaluateWriteFence(
        projectionAt({ lifecycle_state: lifecycle, deletion_epoch: 77 }),
        { request_epoch: 4 },
      );
      expect(decision).toEqual({
        admitted: false,
        outcome: "authorization",
        reason: "account_lifecycle_not_active",
        evidence: "record_nothing",
      });
    });
  }

  /**
   * `backend:ADR-012` §4: "account existence must not be probeable through
   * response differences." A deleted account and an account whose grant was never
   * issued must reach the client as the same outcome class, or the refusal is an
   * existence oracle.
   *
   * red-proof: give `account_lifecycle_not_active` its own outcome — say
   * `"stale_epoch"` or a new `"deleted"` — and this goes red.
   */
  test("a deleted account refuses in the same class an ungranted one would", () => {
    const deleted = evaluateWriteFence(
      projectionAt({ lifecycle_state: "deleted", deletion_epoch: 77 }),
      { request_epoch: 4 },
    );
    expect(deleted.admitted).toBe(false);
    if (deleted.admitted) throw new Error("unreachable");
    // `authorization` is the class an exact-grant failure produces (ADR-010 §3).
    expect(deleted.outcome).toBe("authorization");
  });
});
