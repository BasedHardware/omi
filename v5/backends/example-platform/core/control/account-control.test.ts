import { describe, expect, test } from "bun:test";

import {
  activateEpoch,
  admitObservation,
  deactivateEpoch,
  initialiseProjection,
  isWellFormedAccountId,
  reconcileConflict,
  type AccountControlObservation,
  type AccountControlProjection,
} from "./account-control";
import { evaluateWriteFence } from "./write-fence";

const ACCOUNT = "acct-control-unit-fixture";

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

const accepted = (result: ReturnType<typeof admitObservation>): AccountControlProjection => {
  expect(result.accepted).toBe(true);
  return result.projection;
};

/** Walks ADR-010 §1's forward activation order and returns the live projection. */
const cutOver = (): AccountControlProjection => {
  let projection = accepted(initialiseProjection(observation()));
  projection = accepted(admitObservation(projection, observation({
    control_revision: 2,
    account_generation: "migrating",
  })));
  projection = accepted(admitObservation(projection, observation({
    control_revision: 3,
    account_generation: "new",
    account_epoch: 7,
  })));
  const activated = activateEpoch(projection, { epoch: 7, at_control_revision: 3 });
  expect(activated.activated).toBe(true);
  if (!activated.activated) throw new Error("unreachable");
  return activated.projection;
};

describe("the forward activation order of ADR-010 §1", () => {
  /**
   * The order is the specification, so the test walks it rather than asserting on
   * a hand-built end state. Each step's fence behaviour is asserted where it
   * happens: a state that is reached only by an illegal shortcut can then never
   * be mistaken for a healthy one.
   */
  test("writes are fenced at every step until the destination activates the epoch", () => {
    let projection = accepted(initialiseProjection(observation()));
    // Step 0 — legacy owns authority. The platform is not a write target.
    expect(evaluateWriteFence(projection, { request_epoch: null }).admitted).toBe(false);

    // Step 1 — legacy CAS to `migrating`, which "fences interactive and
    // background writes".
    projection = accepted(admitObservation(projection, observation({
      control_revision: 2,
      account_generation: "migrating",
    })));
    expect(evaluateWriteFence(projection, { request_epoch: null }).admitted).toBe(false);

    // Step 3 — legacy CAS to `new` with a monotonic account epoch. Step 2 (the
    // destination copies and verifies but denies product writes) is the state
    // above; the fence's answer is unchanged, which is what "denies product
    // writes" means here.
    projection = accepted(admitObservation(projection, observation({
      control_revision: 3,
      account_generation: "new",
      account_epoch: 7,
    })));
    // STILL FENCED. Legacy has moved; the destination has not activated. This is
    // the step an implementation is most likely to skip.
    expect(evaluateWriteFence(projection, { request_epoch: 7 })).toMatchObject({
      admitted: false,
      reason: "control_state_not_activated",
    });

    // Step 4 — "The destination activates exactly that epoch."
    const activated = activateEpoch(projection, { epoch: 7, at_control_revision: 3 });
    expect(activated.activated).toBe(true);
    if (!activated.activated) throw new Error("unreachable");
    expect(evaluateWriteFence(activated.projection, { request_epoch: 7 })).toEqual({
      admitted: true,
      account_epoch: 7,
    });
  });

  /**
   * "EXACTLY that epoch" is the whole content of step 4.
   *
   * red-proof: relax the epoch check in `activateEpoch` from
   * `request.epoch !== projection.account_epoch` to
   * `request.epoch > projection.account_epoch`. Activating epoch 6 against a
   * control record at 7 then succeeds, and the op stamped 6 — a genuine
   * straggler — is admitted. This goes red.
   */
  test("the destination cannot activate an epoch the control record does not carry", () => {
    let projection = accepted(initialiseProjection(observation()));
    projection = accepted(admitObservation(projection, observation({
      control_revision: 2, account_generation: "migrating",
    })));
    projection = accepted(admitObservation(projection, observation({
      control_revision: 3, account_generation: "new", account_epoch: 7,
    })));

    for (const epoch of [6, 8]) {
      expect(activateEpoch(projection, { epoch, at_control_revision: 3 })).toEqual({
        activated: false,
        reason: "epoch_mismatch",
      });
    }
    // And not against a revision the projection has already moved past.
    expect(activateEpoch(projection, { epoch: 7, at_control_revision: 2 })).toEqual({
      activated: false,
      reason: "control_revision_mismatch",
    });
  });

  test("the destination refuses to activate a non-new or non-active account", () => {
    const migrating = accepted(initialiseProjection(observation({
      control_revision: 2, account_generation: "migrating", account_epoch: 7,
    })));
    expect(activateEpoch(migrating, { epoch: 7, at_control_revision: 2 })).toEqual({
      activated: false, reason: "account_generation_not_new",
    });

    const deleting = accepted(initialiseProjection(observation({
      control_revision: 3,
      account_generation: "new",
      account_epoch: 7,
      lifecycle_state: "deletion_pending",
      deletion_epoch: 1,
    })));
    expect(activateEpoch(deleting, { epoch: 7, at_control_revision: 3 })).toEqual({
      activated: false, reason: "account_lifecycle_not_active",
    });
  });
});

describe("the rollback order of ADR-010 §1", () => {
  /**
   * "1. The destination fences/deactivates the epoch and drains or rejects work.
   *  2. Legacy compare-and-swaps to `rolled_back_stranded`."
   *
   * The destination moves FIRST. If deactivation could only be expressed as a
   * consequence of legacy's transition, the window between the two steps is one
   * where both generations accept writes — which is the split brain ADR-010's
   * alternatives table rejects by name.
   */
  test("the destination can fence before legacy has moved, and writes deny in the gap", () => {
    const live = cutOver();
    expect(evaluateWriteFence(live, { request_epoch: 7 }).admitted).toBe(true);

    const fenced = deactivateEpoch(live);
    // Legacy still says `new`; the destination has withdrawn activation.
    expect(fenced.account_generation).toBe("new");
    expect(evaluateWriteFence(fenced, { request_epoch: 7 })).toMatchObject({
      admitted: false,
      outcome: "control_unavailable",
      reason: "control_state_not_activated",
    });

    const rolledBack = accepted(admitObservation(fenced, observation({
      control_revision: 4,
      account_generation: "rolled_back_stranded",
      account_epoch: 7,
    })));
    expect(evaluateWriteFence(rolledBack, { request_epoch: 7 })).toMatchObject({
      admitted: false,
      reason: "account_generation_rolled_back_stranded",
    });
  });
});

describe("missing, stale, conflicting and unordered control state", () => {
  test("a late redelivery is dropped without poisoning", () => {
    const live = cutOver();
    const result = admitObservation(live, observation({
      control_revision: 2, account_generation: "migrating",
    }));
    expect(result).toMatchObject({ accepted: false, reason: "stale_observation" });
    // Redelivery is ordinary publisher behaviour and must not cost availability.
    expect(result.projection).toBe(live);
    expect(evaluateWriteFence(result.projection, { request_epoch: 7 }).admitted).toBe(true);
  });

  test("an identical redelivery at the current revision is idempotent", () => {
    let projection = accepted(initialiseProjection(observation()));
    const again = admitObservation(projection, observation());
    expect(again.accepted).toBe(true);
    expect(again.projection).toEqual(projection);
  });

  /**
   * Two different truths at one revision. This side cannot know which is the
   * account's state, and ADR-010 forbids guessing.
   *
   * red-proof: in `admitObservation`, replace the same-revision branch with
   * `return { accepted: true, projection: project(observation, current.activation, null) };`
   * — i.e. last-write-wins. The projection then silently adopts the second
   * observation, `conflict` stays null, and the fence admits. This goes red on
   * both the conflict assertion and the fence assertion.
   */
  test("two different observations at one revision poison the projection", () => {
    const live = cutOver();
    const conflicting = admitObservation(live, observation({
      control_revision: 3, account_generation: "new", account_epoch: 99,
    }));
    expect(conflicting).toMatchObject({ accepted: false, reason: "conflicting_observation" });
    expect(conflicting.projection.conflict).toMatchObject({
      at_control_revision: 3,
      detail: "conflicting_observation",
    });
    expect(evaluateWriteFence(conflicting.projection, { request_epoch: 7 })).toMatchObject({
      admitted: false,
      reason: "control_state_conflicting",
    });
  });

  test("a poisoned projection is not healed by further observations", () => {
    const live = cutOver();
    const poisoned = admitObservation(live, observation({
      control_revision: 3, account_generation: "new", account_epoch: 99,
    })).projection;
    const later = admitObservation(poisoned, observation({
      control_revision: 4, account_generation: "new", account_epoch: 8,
    }));
    expect(later).toMatchObject({ accepted: false, reason: "projection_conflicted" });
    expect(later.projection.conflict).not.toBeNull();
  });

  /**
   * `rolled_back_stranded` is terminal until re-cutover is decided (ADR-014 §8
   * lists it among the policies gated at the first production cohort), and
   * `deleted -> active` is a resurrection.
   *
   * red-proof: delete the `LEGAL_GENERATION_TRANSITIONS` check in
   * `admitObservation`. The stranded account walks straight back to `new`, and
   * with an activation still in hand it would serve writes again. This goes red.
   */
  test("an illegal generation transition poisons rather than being applied", () => {
    const live = cutOver();
    const stranded = accepted(admitObservation(live, observation({
      control_revision: 4, account_generation: "rolled_back_stranded", account_epoch: 7,
    })));
    const resurrected = admitObservation(stranded, observation({
      control_revision: 5, account_generation: "new", account_epoch: 7,
    }));
    expect(resurrected).toMatchObject({
      accepted: false, reason: "unordered_generation_transition",
    });
    expect(evaluateWriteFence(resurrected.projection, { request_epoch: 7 }).admitted).toBe(false);
  });

  /**
   * ADR-014 §1: `active -> deletion_pending -> deleted`, one way. §4 says a
   * restore WILL produce resurrected rows, so an observation walking lifecycle
   * backwards is a state this system expects to see and must not apply silently.
   *
   * red-proof: delete the `LIFECYCLE_ORDER` comparison in `admitObservation`.
   * The deleted account returns to `active` and writes resume. This goes red.
   */
  test("a lifecycle resurrection poisons rather than being applied", () => {
    const live = cutOver();
    const deleting = accepted(admitObservation(live, observation({
      control_revision: 4,
      account_generation: "new",
      account_epoch: 7,
      lifecycle_state: "deleted",
      deletion_epoch: 31,
    })));
    expect(evaluateWriteFence(deleting, { request_epoch: 7 })).toMatchObject({
      admitted: false, outcome: "authorization",
    });

    const resurrected = admitObservation(deleting, observation({
      control_revision: 5, account_generation: "new", account_epoch: 7,
    }));
    expect(resurrected).toMatchObject({ accepted: false, reason: "unordered_lifecycle" });
    expect(evaluateWriteFence(resurrected.projection, { request_epoch: 7 }).admitted).toBe(false);
  });

  /**
   * red-proof: delete the `observation.account_epoch < current.account_epoch`
   * check. The epoch walks backwards to 6, a straggler op stamped 6 matches, and
   * the fence admits an op the account has already moved past. This goes red.
   */
  test("an epoch that walks backwards poisons rather than being applied", () => {
    const live = cutOver();
    const rewound = admitObservation(live, observation({
      control_revision: 4, account_generation: "new", account_epoch: 6,
    }));
    expect(rewound).toMatchObject({ accepted: false, reason: "unordered_epoch" });
    expect(evaluateWriteFence(rewound.projection, { request_epoch: 6 }).admitted).toBe(false);
  });

  test("an epoch that disappears poisons", () => {
    const live = cutOver();
    const withdrawn = admitObservation(live, observation({
      control_revision: 4, account_generation: "new", account_epoch: null,
    }));
    expect(withdrawn).toMatchObject({ accepted: false, reason: "withdrawn_epoch" });
  });

  test("a second account identifier at one projection key poisons", () => {
    const live = cutOver();
    const split = admitObservation(live, {
      ...observation({ control_revision: 4, account_generation: "new", account_epoch: 7 }),
      account_id: "acct-someone-else",
    });
    expect(split).toMatchObject({ accepted: false, reason: "account_id_mismatch" });
  });

  /**
   * ADR-014 §1: "A deletion epoch accompanies the state." An incomplete terminal
   * record is not a usable one — the deletion epoch joins the lease and commit
   * tuple (§6), so a tombstone without it cannot fence anything.
   */
  test("a terminal lifecycle without a deletion epoch is malformed", () => {
    const live = cutOver();
    const incomplete = admitObservation(live, observation({
      control_revision: 4,
      account_generation: "new",
      account_epoch: 7,
      lifecycle_state: "deleted",
      deletion_epoch: null,
    }));
    expect(incomplete).toMatchObject({ accepted: false, reason: "malformed_observation" });
    expect(evaluateWriteFence(incomplete.projection, { request_epoch: 7 }).admitted).toBe(false);
  });
});

describe("an accepted observation that moves the epoch drops the activation", () => {
  /**
   * ADR-010 §1 step 4 activates exactly ONE epoch. A second cutover — legacy
   * advancing the epoch again — must not inherit the previous activation, or the
   * destination would serve the new epoch on the strength of having approved the
   * old one, and step 4 would never run again.
   *
   * red-proof: in `admitObservation`, carry `current.activation` through
   * unconditionally. The advanced-epoch row then admits without re-activation and
   * this goes red.
   */
  test("advancing the epoch re-fences until the destination activates again", () => {
    const live = cutOver();
    const advanced = accepted(admitObservation(live, observation({
      control_revision: 4, account_generation: "new", account_epoch: 8,
    })));
    expect(advanced.activation).toBeNull();
    expect(evaluateWriteFence(advanced, { request_epoch: 8 })).toMatchObject({
      admitted: false, reason: "control_state_not_activated",
    });

    const reactivated = activateEpoch(advanced, { epoch: 8, at_control_revision: 4 });
    expect(reactivated.activated).toBe(true);
    if (!reactivated.activated) throw new Error("unreachable");
    expect(evaluateWriteFence(reactivated.projection, { request_epoch: 8 }).admitted).toBe(true);
    // ...and the op created under the old epoch is now the straggler.
    expect(evaluateWriteFence(reactivated.projection, { request_epoch: 7 })).toEqual({
      admitted: false,
      outcome: "stale_epoch",
      reason: "request_epoch_behind",
      evidence: "preserve_envelope",
    });
  });
});

describe("reconciliation is an explicit operator act", () => {
  test("a conflict clears only with a stated reason, and re-fences the destination", () => {
    const live = cutOver();
    const poisoned = admitObservation(live, observation({
      control_revision: 3, account_generation: "new", account_epoch: 99,
    })).projection;

    expect(reconcileConflict(poisoned, observation({
      control_revision: 5, account_generation: "new", account_epoch: 8,
    }), { reason: "   " })).toMatchObject({ accepted: false });

    const reconciled = reconcileConflict(poisoned, observation({
      control_revision: 5, account_generation: "new", account_epoch: 8,
    }), { reason: "operator verified legacy control record at revision 5" });
    expect(reconciled.accepted).toBe(true);
    expect(reconciled.projection.conflict).toBeNull();
    // Reconciliation does not re-open writes by itself: whatever was activated
    // was decided against state now known to be untrustworthy.
    expect(reconciled.projection.activation).toBeNull();
    expect(evaluateWriteFence(reconciled.projection, { request_epoch: 8 }).admitted).toBe(false);
  });
});

describe("the account identifier is opaque here, by RISK-015", () => {
  /**
   * `backend:ADR-012` §1 (platform-owned account root) is settled; §2's grammar
   * is blocked on `frontend:ADR-006`, and "until reconciled, neither scheme is
   * implemented in a shared contract". So this projection accepts a
   * Firebase-shaped id and a word slug alike and asserts nothing about either.
   *
   * This test exists to pin the ABSENCE of a grammar. If someone later adds
   * `^acct_(\w+-){3}\w+$` here, it goes red — which is the intended alarm, not a
   * nuisance: that regex is ADR-012 §2 reaching the one place a wire would
   * inherit it from.
   */
  test("no identifier grammar is enforced beyond containment", () => {
    expect(isWellFormedAccountId("acct_tidy-otter-brisk-cedar")).toBe(true);
    expect(isWellFormedAccountId("flying-dragon-vibrant")).toBe(true);
    expect(isWellFormedAccountId("SbY7nRk2QcW0pLxTgH9m")).toBe(true);
    expect(isWellFormedAccountId("550e8400-e29b-41d4-a716-446655440000")).toBe(true);

    expect(isWellFormedAccountId("")).toBe(false);
    expect(isWellFormedAccountId("has space")).toBe(false);
    expect(isWellFormedAccountId("a".repeat(129))).toBe(false);
    expect(isWellFormedAccountId(null)).toBe(false);
    expect(isWellFormedAccountId(7)).toBe(false);
  });
});
