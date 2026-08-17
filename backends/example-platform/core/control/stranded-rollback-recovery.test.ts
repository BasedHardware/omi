import { describe, expect, test } from "bun:test";

import {
  STRANDED_ROLLBACK_RECOVERY_CONTRACT_VERSION,
  STRANDED_ROLLBACK_RECOVERY_SURFACES,
  STRANDED_ROLLBACK_RECOVERY_WINDOW_SECONDS,
  STRANDED_ROLLBACK_SOURCE_RECEIPT_VERSION,
  StrandedRollbackRecoveryInputError,
  isVerifiedStrandedRollbackRecoveryManifest,
  verifyStrandedRollbackRecovery,
} from "./stranded-rollback-recovery";

const ACCOUNT = "acct-stranded-fixture";
const digest = (value: string): string => value.repeat(64);
const rolledBackAt = 1_800_000_000;
const coordinate = () => ({
  version: "stranded-rollback-coordinate-v1" as const,
  account_id: ACCOUNT,
  control_revision: 9,
  account_epoch: 4,
  database_generation_digest: digest("a"),
  cutover_frontier_digest: digest("b"),
  rollback_frontier_digest: digest("c"),
  cutover_at_epoch_seconds: rolledBackAt - 3_600,
  rolled_back_at_epoch_seconds: rolledBackAt,
  recovery_deadline_epoch_seconds: rolledBackAt + STRANDED_ROLLBACK_RECOVERY_WINDOW_SECONDS,
});
const control = (overrides: Record<string, unknown> = {}) => ({
  account_id: ACCOUNT,
  control_revision: 9,
  account_generation: "rolled_back_stranded",
  account_epoch: 4,
  lifecycle_state: "active",
  deletion_epoch: null,
  activation: null,
  conflict: null,
  ...overrides,
});
const receipts = () => STRANDED_ROLLBACK_RECOVERY_SURFACES.map((surface, index) => ({
  version: STRANDED_ROLLBACK_SOURCE_RECEIPT_VERSION,
  manifest_contract_version: STRANDED_ROLLBACK_RECOVERY_CONTRACT_VERSION,
  scanner_contract_version: `scanner-${surface}-v1`,
  account_id: ACCOUNT,
  control_revision: 9,
  account_epoch: 4,
  database_generation_digest: digest("a"),
  surface,
  source_frontier_digest: String(index % 10).repeat(64),
  source_fence_state: "held" as const,
  source_fence_receipt_digest: digest("d"),
  record_count: index,
  record_set_digest: digest("e"),
}));
const input = (overrides: Record<string, unknown> = {}) => ({
  control_projection: control(),
  rollback_coordinate: coordinate(),
  source_receipts: receipts(),
  observed_at_epoch_seconds: rolledBackAt + 1,
  ...overrides,
});

const expectCode = (call: () => unknown, code: string): void => {
  try {
    call();
    throw new Error("expected input error");
  } catch (error) {
    expect(error).toBeInstanceOf(StrandedRollbackRecoveryInputError);
    expect((error as StrandedRollbackRecoveryInputError).code).toBe(code);
  }
};

describe("stranded rollback recovery manifest", () => {
  test("binds every existing destination surface into one recoverable 30-day manifest", () => {
    const forward = verifyStrandedRollbackRecovery(input());
    const reverse = verifyStrandedRollbackRecovery(input({ source_receipts: receipts().reverse() }));
    expect(forward.report).toEqual(reverse.report);
    expect(forward.verified_manifest).toEqual(reverse.verified_manifest);
    expect(forward.report).toMatchObject({
      status: "recoverable",
      supplied_source_count: 11,
      required_source_count: 11,
      missing_surfaces: [],
      unfenced_surfaces: [],
      blockers: [],
    });
    expect(forward.verified_manifest?.rows.map((row) => row.surface))
      .toEqual([...STRANDED_ROLLBACK_RECOVERY_SURFACES]);
    expect(isVerifiedStrandedRollbackRecoveryManifest(forward.verified_manifest)).toBe(true);
    expect(JSON.stringify(forward.report)).not.toContain(ACCOUNT);
  });

  test("changes from recoverable to disposition-due exactly at the fixed deadline", () => {
    const before = verifyStrandedRollbackRecovery(input({
      observed_at_epoch_seconds: coordinate().recovery_deadline_epoch_seconds - 1,
    }));
    const at = verifyStrandedRollbackRecovery(input({
      observed_at_epoch_seconds: coordinate().recovery_deadline_epoch_seconds,
    }));
    expect(before.report.status).toBe("recoverable");
    expect(at.report.status).toBe("disposition_due");
    expect(at.report.manifest_digest).toBe(before.report.manifest_digest);
  });

  test("missing, released, or wrong-generation sources remain blocked", () => {
    const missing = verifyStrandedRollbackRecovery(input({ source_receipts: receipts().slice(1) }));
    expect(missing.report).toMatchObject({
      status: "blocked",
      blockers: ["source_missing"],
      missing_surfaces: ["durable_work"],
      manifest_digest: null,
    });
    const released = receipts();
    released[0] = { ...released[0]!, source_fence_state: "released" };
    expect(verifyStrandedRollbackRecovery(input({ source_receipts: released })).report)
      .toMatchObject({ status: "blocked", blockers: ["source_fence_not_held"] });
    expect(verifyStrandedRollbackRecovery(input({
      control_projection: control({ account_generation: "legacy", account_epoch: 4 }),
    })).report).toMatchObject({
      status: "blocked",
      blockers: ["control_not_rolled_back_stranded"],
    });
  });

  test("rejects arbitrary windows, stale coordinates, duplicates, and old receipt versions", () => {
    expectCode(() => verifyStrandedRollbackRecovery(input({
      rollback_coordinate: { ...coordinate(), recovery_deadline_epoch_seconds: rolledBackAt + 10 },
    })), "invalid_rollback_coordinate");
    expectCode(() => verifyStrandedRollbackRecovery(input({
      control_projection: control({ control_revision: 10 }),
    })), "rollback_coordinate_mismatch");
    const duplicate = receipts();
    duplicate[1] = { ...duplicate[0]! };
    expectCode(() => verifyStrandedRollbackRecovery(input({ source_receipts: duplicate })),
      "duplicate_source_receipt");
    const old = receipts();
    old[0] = { ...old[0]!, version: "stranded-rollback-source-receipt-v0" as never };
    expectCode(() => verifyStrandedRollbackRecovery(input({ source_receipts: old })),
      "invalid_source_receipt");
  });

  test("rejects proxies, accessors, sparse arrays, and JSON-forged manifests", () => {
    expectCode(() => verifyStrandedRollbackRecovery(new Proxy(input(), {})), "invalid_input");
    const accessor = input();
    Object.defineProperty(accessor, "source_receipts", { enumerable: true, get: receipts });
    expectCode(() => verifyStrandedRollbackRecovery(accessor), "invalid_input");
    const sparse = receipts();
    delete sparse[0];
    expectCode(() => verifyStrandedRollbackRecovery(input({ source_receipts: sparse })),
      "invalid_source_receipts");
    const verified = verifyStrandedRollbackRecovery(input()).verified_manifest!;
    expect(isVerifiedStrandedRollbackRecoveryManifest(JSON.parse(JSON.stringify(verified)))).toBe(false);
    expect(Object.isFrozen(verified)).toBe(true);
    expect(Object.isFrozen(verified.rows)).toBe(true);
  });
});
