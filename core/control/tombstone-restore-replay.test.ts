import { describe, expect, test } from "bun:test";

import {
  MAX_TERMINAL_REPLAY_RECORDS,
  TERMINAL_APPLICATION_OUTCOME_VERSION,
  TERMINAL_FEED_FENCE_VERSION,
  TERMINAL_SET_SOURCE_RECEIPT_VERSION,
  TombstoneReplayInputError,
  buildTerminalReplayManifest,
  verifyTombstoneRestoreReplay,
  type RestoreCoordinate,
  type RestoreScope,
  type TerminalApplicationOutcome,
  type TerminalApplicationResult,
  type TerminalFeedFence,
  type TerminalReplayManifest,
  type TerminalReplayManifestRecord,
  type TerminalSetSourceReceipt,
  type TombstoneReplayInputErrorCode,
  type TombstoneReplayVerificationInput,
} from "./tombstone-restore-replay";

const digest = (character: string): string => character.repeat(64);

const record = (
  account: string,
  index: number,
): TerminalReplayManifestRecord => ({
  account_id: account,
  control_revision: 10 + index,
  deletion_epoch: 20 + index,
  terminal_record_digest: digest(String(index % 10)),
});

const manifest = (
  records: readonly TerminalReplayManifestRecord[] = [record("acct-a", 1), record("acct-b", 2)],
  overrides: Partial<{
    source_snapshot_digest: string;
    source_high_watermark: number;
    captured_at_epoch_seconds: number;
  }> = {},
): TerminalReplayManifest => buildTerminalReplayManifest({
  source_snapshot_digest: digest("a"),
  source_high_watermark: 40,
  captured_at_epoch_seconds: 1_800_000_100,
  records,
  ...overrides,
});

const restore = (
  scope: RestoreScope = "postgresql",
  overrides: Partial<RestoreCoordinate> = {},
): RestoreCoordinate => ({
  restore_id: "restore-fixture-1",
  restore_scope: scope,
  restored_snapshot_digest: digest("b"),
  restore_completed_at_epoch_seconds: 1_800_000_000,
  ...overrides,
});

const sourceReceipt = (
  value: TerminalReplayManifest,
  overrides: Partial<TerminalSetSourceReceipt> = {},
): TerminalSetSourceReceipt => ({
  version: TERMINAL_SET_SOURCE_RECEIPT_VERSION,
  sink_contract_version: "terminal-export-sink-v1",
  source_snapshot_digest: value.source_snapshot_digest,
  source_high_watermark: value.source_high_watermark,
  record_count: value.records.length,
  manifest_digest: value.manifest_digest,
  retention_locked_sink_receipt_digest: digest("c"),
  ...overrides,
});

const fence = (
  restored: RestoreCoordinate,
  value: TerminalReplayManifest,
  overrides: Partial<TerminalFeedFence> = {},
): TerminalFeedFence => ({
  version: TERMINAL_FEED_FENCE_VERSION,
  state: "held",
  restore_id: restored.restore_id,
  restore_scope: restored.restore_scope,
  source_snapshot_digest: value.source_snapshot_digest,
  source_high_watermark: value.source_high_watermark,
  fence_receipt_digest: digest("d"),
  ...overrides,
});

const application = (
  restored: RestoreCoordinate,
  terminal: TerminalReplayManifestRecord,
  result: TerminalApplicationResult = "applied",
  overrides: Partial<TerminalApplicationOutcome> = {},
): TerminalApplicationOutcome => ({
  version: TERMINAL_APPLICATION_OUTCOME_VERSION,
  restore_id: restored.restore_id,
  restore_scope: restored.restore_scope,
  restored_snapshot_digest: restored.restored_snapshot_digest,
  account_id: terminal.account_id,
  control_revision: terminal.control_revision,
  deletion_epoch: terminal.deletion_epoch,
  terminal_record_digest: terminal.terminal_record_digest,
  result,
  target_receipt_digest: result === "applied" || result === "already_absent" ? digest("e") : null,
  error_code: result === "retryable_error"
    ? "target_unavailable"
    : result === "terminal_error"
      ? "target_verification_failed"
      : null,
  ...overrides,
});

const applications = (
  restored: RestoreCoordinate,
  value: TerminalReplayManifest,
): TerminalApplicationOutcome[] => value.records.map((terminal, index) => application(
  restored,
  terminal,
  index % 2 === 0 ? "applied" : "already_absent",
  { target_receipt_digest: digest(index % 2 === 0 ? "e" : "f") },
));

const input = (
  scope: RestoreScope = "postgresql",
  overrides: Partial<TombstoneReplayVerificationInput> = {},
): TombstoneReplayVerificationInput => {
  const restored = restore(scope);
  const terminalManifest = manifest();
  return {
    restore: restored,
    manifest: terminalManifest,
    source_receipt: sourceReceipt(terminalManifest),
    traffic_fence: fence(restored, terminalManifest),
    applications: applications(restored, terminalManifest),
    ...overrides,
  };
};

const expectErrorCode = (call: () => unknown, code: TombstoneReplayInputErrorCode): void => {
  try {
    call();
    throw new Error("expected tombstone replay input error");
  } catch (error) {
    expect(error).toBeInstanceOf(TombstoneReplayInputError);
    expect((error as TombstoneReplayInputError).code).toBe(code);
  }
};

describe("complete replay checkpoint", () => {
  test("both restore scopes produce an exact deterministic checkpoint", () => {
    for (const scope of ["legacy", "postgresql"] as const) {
      const value = input(scope);
      const first = verifyTombstoneRestoreReplay(value);
      const replay = verifyTombstoneRestoreReplay(value);
      expect(first).toEqual(replay);
      expect(first).toMatchObject({
        restore_scope: scope,
        record_count: 2,
        successful_count: 2,
        missing_count: 0,
        retryable_error_count: 0,
        terminal_error_count: 0,
        blockers: [],
      });
      expect(first.checkpoint?.checkpoint_digest).toMatch(/^[0-9a-f]{64}$/);
    }
  });

  test("manifest and application order do not change the checkpoint", () => {
    const restored = restore();
    const forwardManifest = manifest([record("acct-a", 1), record("acct-b", 2)]);
    const reverseManifest = manifest([record("acct-b", 2), record("acct-a", 1)]);
    expect(reverseManifest).toEqual(forwardManifest);

    const forward = verifyTombstoneRestoreReplay({
      restore: restored,
      manifest: forwardManifest,
      source_receipt: sourceReceipt(forwardManifest),
      traffic_fence: fence(restored, forwardManifest),
      applications: applications(restored, forwardManifest),
    });
    const reversed = verifyTombstoneRestoreReplay({
      restore: restored,
      manifest: reverseManifest,
      source_receipt: sourceReceipt(reverseManifest),
      traffic_fence: fence(restored, reverseManifest),
      applications: applications(restored, reverseManifest).reverse(),
    });
    expect(reversed).toEqual(forward);
  });

  test("a receipt-backed empty terminal set can pass without treating absence as proof", () => {
    const restored = restore("legacy");
    const empty = manifest([]);
    const report = verifyTombstoneRestoreReplay({
      restore: restored,
      manifest: empty,
      source_receipt: sourceReceipt(empty),
      traffic_fence: fence(restored, empty),
      applications: [],
    });
    expect(report).toMatchObject({ record_count: 0, successful_count: 0, blockers: [] });
    expect(report.checkpoint).not.toBeNull();
  });
});

describe("source, fence, and progress blockers", () => {
  test("source receipt mismatch fails before a report exists, including empty-set claims", () => {
    const value = input();
    for (const receipt of [
      sourceReceipt(value.manifest, { record_count: 0 }),
      sourceReceipt(value.manifest, { source_snapshot_digest: digest("9") }),
      sourceReceipt(value.manifest, { source_high_watermark: 41 }),
      sourceReceipt(value.manifest, { manifest_digest: digest("8") }),
    ]) {
      expectErrorCode(() => verifyTombstoneRestoreReplay({ ...value, source_receipt: receipt }),
        "source_receipt_mismatch");
    }

    const empty = manifest([]);
    expectErrorCode(() => verifyTombstoneRestoreReplay({
      ...value,
      manifest: empty,
      source_receipt: sourceReceipt(empty, { record_count: 1 }),
      applications: [],
    }), "source_receipt_mismatch");
  });

  test("a pre-restore source or missing, released, and mismatched fence blocks checkpoint", () => {
    const restored = restore();
    const oldManifest = manifest(undefined, { captured_at_epoch_seconds: 1_799_999_999 });
    const old = verifyTombstoneRestoreReplay({
      restore: restored,
      manifest: oldManifest,
      source_receipt: sourceReceipt(oldManifest),
      traffic_fence: null,
      applications: applications(restored, oldManifest),
    });
    expect(old.blockers).toEqual(["terminal_set_predates_restore", "terminal_feed_not_held"]);
    expect(old.checkpoint).toBeNull();

    const current = input();
    for (const trafficFence of [
      null,
      fence(current.restore, current.manifest, { state: "released" }),
      fence(current.restore, current.manifest, { source_high_watermark: 39 }),
      fence(current.restore, current.manifest, { restore_scope: "legacy" }),
    ]) {
      const report = verifyTombstoneRestoreReplay({ ...current, traffic_fence: trafficFence });
      expect(report.blockers).toEqual(["terminal_feed_not_held"]);
      expect(report.checkpoint).toBeNull();
    }
  });

  test("missing, retryable, and terminal application work remains distinct", () => {
    const value = input();
    const first = value.manifest.records[0]!;
    const second = value.manifest.records[1]!;
    const report = verifyTombstoneRestoreReplay({
      ...value,
      applications: [
        application(value.restore, first, "retryable_error"),
        application(value.restore, second, "terminal_error"),
      ],
    });
    expect(report).toMatchObject({
      successful_count: 0,
      missing_count: 0,
      retryable_error_count: 1,
      terminal_error_count: 1,
      blockers: ["application_retryable_error", "application_terminal_error"],
      checkpoint: null,
    });

    const partial = verifyTombstoneRestoreReplay({
      ...value,
      applications: [application(value.restore, first)],
    });
    expect(partial).toMatchObject({
      successful_count: 1,
      missing_count: 1,
      blockers: ["application_missing"],
      checkpoint: null,
    });
  });
});

describe("strict outcome and coordinate closure", () => {
  test("success/error receipt combinations are exact", () => {
    const value = input();
    const terminal = value.manifest.records[0]!;
    for (const malformed of [
      application(value.restore, terminal, "applied", { target_receipt_digest: null }),
      application(value.restore, terminal, "already_absent", { error_code: "target_conflict" }),
      application(value.restore, terminal, "retryable_error", { target_receipt_digest: digest("1") }),
      application(value.restore, terminal, "retryable_error", { error_code: "target_conflict" }),
      application(value.restore, terminal, "terminal_error", { error_code: "target_unavailable" }),
    ]) {
      expectErrorCode(() => verifyTombstoneRestoreReplay({ ...value, applications: [malformed] }),
        "invalid_application_outcome");
    }
  });

  test("extra, duplicate, swapped, and cross-restore outcomes fail", () => {
    const value = input();
    const first = value.manifest.records[0]!;
    const second = value.manifest.records[1]!;
    const firstApplication = application(value.restore, first);
    expectErrorCode(() => verifyTombstoneRestoreReplay({
      ...value,
      applications: [firstApplication, { ...firstApplication }],
    }), "duplicate_application_outcome");
    expectErrorCode(() => verifyTombstoneRestoreReplay({
      ...value,
      applications: [application(value.restore, record("acct-extra", 9))],
    }), "application_not_in_manifest");
    expectErrorCode(() => verifyTombstoneRestoreReplay({
      ...value,
      applications: [application(value.restore, first, "applied", {
        terminal_record_digest: second.terminal_record_digest,
      })],
    }), "application_coordinate_mismatch");
    expectErrorCode(() => verifyTombstoneRestoreReplay({
      ...value,
      applications: [application(value.restore, first, "applied", { restore_id: "restore-other" })],
    }), "application_coordinate_mismatch");
  });

  test("every identity-bearing success coordinate changes the checkpoint", () => {
    const value = input();
    const baseline = verifyTombstoneRestoreReplay(value).checkpoint!;
    const changedFence = verifyTombstoneRestoreReplay({
      ...value,
      traffic_fence: { ...value.traffic_fence!, fence_receipt_digest: digest("7") },
    }).checkpoint!;
    const changedApplications = value.applications.map((row, index) => index === 0
      ? { ...row, target_receipt_digest: digest("6") }
      : row);
    const changedResult = verifyTombstoneRestoreReplay({
      ...value,
      applications: changedApplications,
    }).checkpoint!;
    const changedSourceReceipt = verifyTombstoneRestoreReplay({
      ...value,
      source_receipt: {
        ...value.source_receipt,
        retention_locked_sink_receipt_digest: digest("5"),
      },
    }).checkpoint!;
    const changedRestore = restore("postgresql", {
      restore_completed_at_epoch_seconds: value.restore.restore_completed_at_epoch_seconds - 1,
    });
    const changedRestoreCheckpoint = verifyTombstoneRestoreReplay({
      ...value,
      restore: changedRestore,
      traffic_fence: fence(changedRestore, value.manifest),
      applications: applications(changedRestore, value.manifest),
    }).checkpoint!;
    expect(changedFence.checkpoint_digest).not.toBe(baseline.checkpoint_digest);
    expect(changedResult.checkpoint_digest).not.toBe(baseline.checkpoint_digest);
    expect(changedSourceReceipt.checkpoint_digest).not.toBe(baseline.checkpoint_digest);
    expect(changedRestoreCheckpoint.checkpoint_digest).not.toBe(baseline.checkpoint_digest);
  });
});

describe("hostile input and content-safe output", () => {
  test("rejects proxies, accessors, extras, sparse/decorated arrays, bad values, and over-budget sets", () => {
    const value = input();
    expectErrorCode(() => verifyTombstoneRestoreReplay(new Proxy(value, {})), "invalid_input");
    expectErrorCode(() => verifyTombstoneRestoreReplay({ ...value, extra: true }), "invalid_input");

    let getterCalls = 0;
    const hostileRecord = { ...value.manifest.records[0] } as Record<string, unknown>;
    Object.defineProperty(hostileRecord, "account_id", {
      enumerable: true,
      get: () => {
        getterCalls += 1;
        return "acct-a";
      },
    });
    expectErrorCode(() => buildTerminalReplayManifest({
      source_snapshot_digest: digest("a"),
      source_high_watermark: 1,
      captured_at_epoch_seconds: 1,
      records: [hostileRecord],
    }), "invalid_manifest");
    expect(getterCalls).toBe(0);

    const sparse = [...value.applications];
    delete sparse[0];
    expectErrorCode(() => verifyTombstoneRestoreReplay({ ...value, applications: sparse }),
      "invalid_application_outcome");
    const decorated = [...value.applications] as TerminalApplicationOutcome[] & { extra?: boolean };
    decorated.extra = true;
    expectErrorCode(() => verifyTombstoneRestoreReplay({ ...value, applications: decorated }),
      "invalid_application_outcome");

    expectErrorCode(() => buildTerminalReplayManifest({
      source_snapshot_digest: digest("a"),
      source_high_watermark: -1,
      captured_at_epoch_seconds: 1,
      records: [],
    }), "invalid_manifest");
    expectErrorCode(() => buildTerminalReplayManifest({
      source_snapshot_digest: digest("a"),
      source_high_watermark: 1,
      captured_at_epoch_seconds: 1,
      records: new Array(MAX_TERMINAL_REPLAY_RECORDS + 1).fill(record("acct-over", 1)),
    }), "manifest_over_budget");
    expectErrorCode(() => verifyTombstoneRestoreReplay({
      ...value,
      applications: new Array(MAX_TERMINAL_REPLAY_RECORDS + 1).fill(value.applications[0]),
    }), "application_over_budget");
  });

  test("output is deeply frozen, row-free, and detached from later input mutation", () => {
    const base = input();
    const value = {
      ...base,
      manifest: {
        ...base.manifest,
        records: base.manifest.records.map((row) => ({ ...row })),
      },
      applications: base.applications.map((row) => ({ ...row })),
    };
    const report = verifyTombstoneRestoreReplay(value);
    const rendered = JSON.stringify(report);
    expect(rendered).not.toContain("acct-a");
    expect(rendered).not.toContain("acct-b");
    expect(rendered).not.toContain("terminal_record_digest");
    expect(Object.isFrozen(report)).toBe(true);
    expect(Object.isFrozen(report.blockers)).toBe(true);
    expect(Object.isFrozen(report.checkpoint)).toBe(true);

    (value.applications[0] as { target_receipt_digest: string }).target_receipt_digest = digest("9");
    (value.manifest.records[0] as { account_id: string }).account_id = "acct-mutated";
    expect(JSON.stringify(report)).toBe(rendered);
  });
});
