import { createHash } from "node:crypto";

import { describe, expect, test } from "bun:test";

import type { AccountControlProjection } from "./account-control";
import {
  TERMINAL_APPLICATION_OUTCOME_VERSION,
  TERMINAL_FEED_FENCE_VERSION,
  TERMINAL_SET_SOURCE_RECEIPT_VERSION,
  buildTerminalReplayManifest,
  verifyTombstoneRestoreReplay,
  type TombstoneReplayCheckpoint,
} from "./tombstone-restore-replay";
import {
  RESTORE_CHECKPOINT_CANDIDATE_VERSION,
  RESTORE_GENERATION_ATTESTATION_VERSION,
  RESTORE_GENERATION_COORDINATE_VERSION,
  RETAINED_TERMINAL_FENCE_OBSERVATION_VERSION,
  RETAINED_TERMINAL_FENCE_VERSION,
  RestorePretrafficReadinessInputError,
  TERMINAL_FEED_APPLIED_COVERAGE_VERSION,
  evaluateRestorePretrafficReadiness,
  type PersistedRestoreCheckpointCandidate,
  type RestoreGenerationCoordinate,
  type RestorePretrafficReadinessInput,
  type RetainedTerminalFenceObservation,
  type TerminalFeedAppliedCoverage,
} from "./restore-pretraffic-readiness";

const hash = (character: string): string => character.repeat(64);
const ACCOUNT = "acct-restore-pretraffic";
const restore: RestoreGenerationCoordinate = {
  version: RESTORE_GENERATION_COORDINATE_VERSION,
  restore_id: "restore-pretraffic-1",
  restore_scope: "postgresql",
  restored_generation_digest: hash("1"),
  restored_snapshot_digest: hash("2"),
  restore_completed_at_epoch_seconds: 100,
  target_identity_digest: hash("d"),
};

const checkpoint = (): TombstoneReplayCheckpoint => {
  const record = {
    account_id: "acct-terminal",
    control_revision: 7,
    deletion_epoch: 9,
    terminal_record_digest: hash("3"),
  };
  const manifest = buildTerminalReplayManifest({
    source_snapshot_digest: hash("4"),
    source_high_watermark: 11,
    captured_at_epoch_seconds: 101,
    records: [record],
  });
  return verifyTombstoneRestoreReplay({
    restore: {
      restore_id: restore.restore_id,
      restore_scope: restore.restore_scope,
      restored_snapshot_digest: restore.restored_snapshot_digest,
      restore_completed_at_epoch_seconds: restore.restore_completed_at_epoch_seconds,
    },
    manifest,
    source_receipt: {
      version: TERMINAL_SET_SOURCE_RECEIPT_VERSION,
      sink_contract_version: "sink-v1",
      source_snapshot_digest: manifest.source_snapshot_digest,
      source_high_watermark: manifest.source_high_watermark,
      record_count: 1,
      manifest_digest: manifest.manifest_digest,
      retention_locked_sink_receipt_digest: hash("5"),
    },
    traffic_fence: {
      version: TERMINAL_FEED_FENCE_VERSION,
      state: "held",
      restore_id: restore.restore_id,
      restore_scope: restore.restore_scope,
      source_snapshot_digest: manifest.source_snapshot_digest,
      source_high_watermark: manifest.source_high_watermark,
      fence_receipt_digest: hash("6"),
    },
    applications: [{
      version: TERMINAL_APPLICATION_OUTCOME_VERSION,
      restore_id: restore.restore_id,
      restore_scope: restore.restore_scope,
      restored_snapshot_digest: restore.restored_snapshot_digest,
      ...record,
      result: "applied",
      target_receipt_digest: hash("7"),
      error_code: null,
    }],
  }).checkpoint!;
};

const sha256 = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");

const candidate = (): PersistedRestoreCheckpointCandidate => {
  const selected = checkpoint();
  const base = {
    version: "postgres-restore-replay-checkpoint-candidate-v1",
    restored_generation_digest: restore.restored_generation_digest,
    restore_id: selected.restore_id,
    restore_scope: selected.restore_scope,
    restored_snapshot_digest: selected.restored_snapshot_digest,
    restore_completed_at_epoch_seconds: selected.restore_completed_at_epoch_seconds,
    source_snapshot_digest: selected.source_snapshot_digest,
    source_feed_generation_digest: hash("f"),
    partition_topology_digest: hash("0"),
    source_high_watermark: selected.source_high_watermark,
    manifest_digest: selected.manifest_digest,
    record_count: 1,
    terminal_source_receipt_binding_digest: selected.terminal_source_receipt_binding_digest,
    application_set_digest: selected.application_set_digest,
    terminal_feed_fence_receipt_digest: selected.traffic_fence_receipt_digest,
    checkpoint_digest: selected.checkpoint_digest,
  };
  const candidateDigest = sha256(base);
  const recordedAt = "1800000000123456";
  return {
    version: RESTORE_CHECKPOINT_CANDIDATE_VERSION,
    checkpoint: selected,
    restored_generation_digest: restore.restored_generation_digest,
    source_feed_generation_digest: hash("f"),
    partition_topology_digest: hash("0"),
    candidate_digest: candidateDigest,
    record_count: 1,
    recorded_at_epoch_micros: recordedAt,
    persistence_receipt_digest: sha256({
      version: "postgres-restore-replay-checkpoint-candidate-receipt-v1",
      restored_generation_digest: restore.restored_generation_digest,
      restore_id: selected.restore_id,
      candidate_digest: candidateDigest,
      recorded_at_epoch_micros: recordedAt,
    }),
  };
};

const coverage = (
  selected = checkpoint(),
  overrides: Partial<TerminalFeedAppliedCoverage> = {},
): TerminalFeedAppliedCoverage => ({
  version: TERMINAL_FEED_APPLIED_COVERAGE_VERSION,
  state: "complete",
  restore_id: restore.restore_id,
  restore_scope: restore.restore_scope,
  restored_generation_digest: restore.restored_generation_digest,
  restored_snapshot_digest: restore.restored_snapshot_digest,
  source_snapshot_digest: selected.source_snapshot_digest,
  source_feed_generation_digest: hash("f"),
  partition_topology_digest: hash("0"),
  source_current_high_watermark: selected.source_high_watermark,
  gap_free_through_high_watermark: selected.source_high_watermark,
  applied_through_high_watermark: selected.source_high_watermark,
  checkpoint_digest: selected.checkpoint_digest,
  coverage_receipt_digest: hash("9"),
  ...overrides,
});

const control = (overrides: Partial<AccountControlProjection> = {}): AccountControlProjection => ({
  account_id: ACCOUNT,
  control_revision: 12,
  account_generation: "new",
  account_epoch: 5,
  lifecycle_state: "active",
  deletion_epoch: null,
  activation: { activated_epoch: 5, at_control_revision: 12 },
  conflict: null,
  ...overrides,
});

const noFence = (): RetainedTerminalFenceObservation => ({
  version: RETAINED_TERMINAL_FENCE_OBSERVATION_VERSION,
  state: "current",
  latest_fence: null,
  observation_receipt_digest: hash("a"),
});

const input = (
  overrides: Partial<RestorePretrafficReadinessInput> = {},
): RestorePretrafficReadinessInput => {
  const selected = candidate();
  return {
    restore_generation: restore,
    generation_attestation: {
      version: RESTORE_GENERATION_ATTESTATION_VERSION,
      state: "current",
      restore_id: restore.restore_id,
      restore_scope: restore.restore_scope,
      restored_generation_digest: restore.restored_generation_digest,
      restored_snapshot_digest: restore.restored_snapshot_digest,
      target_identity_digest: restore.target_identity_digest,
      attestation_receipt_digest: hash("f"),
    },
    checkpoint_candidate: selected,
    terminal_feed_coverage: coverage(selected.checkpoint),
    control_projection: control(),
    retained_fence_observation: noFence(),
    ...overrides,
  };
};

describe("restore pretraffic readiness", () => {
  test("returns only consistent checkpoint evidence for one exact complete snapshot", () => {
    const result = evaluateRestorePretrafficReadiness(input());
    expect(result).toEqual({
      version: "restore-pretraffic-readiness-v1",
      kind: "consistent_checkpoint_evidence",
      blockers: [],
      readiness_evidence_digest: result.readiness_evidence_digest,
    });
    expect(result.readiness_evidence_digest).toMatch(/^[0-9a-f]{64}$/);
    expect(Object.isFrozen(result)).toBe(true);
    expect(Object.isFrozen(result.blockers)).toBe(true);
    expect(JSON.stringify(result)).not.toContain(ACCOUNT);
    expect(JSON.stringify(result)).not.toMatch(/account_epoch|admitted|grant|credential/);
  });

  test("missing checkpoint and coverage never become empty success", () => {
    expect(evaluateRestorePretrafficReadiness(input({
      checkpoint_candidate: null,
      terminal_feed_coverage: null,
    }))).toMatchObject({
      kind: "blocked",
      blockers: ["checkpoint_missing", "terminal_feed_coverage_missing"],
    });
  });

  test("cross-restore, generation, snapshot, checkpoint, and source coverage block", () => {
    const mutations: readonly Partial<TerminalFeedAppliedCoverage>[] = [
      { restore_id: "restore-other" },
      { restored_generation_digest: hash("b") },
      { restored_snapshot_digest: hash("c") },
      { source_snapshot_digest: hash("d") },
      { checkpoint_digest: hash("e") },
      { source_feed_generation_digest: hash("a") },
      { partition_topology_digest: hash("b") },
    ];
    for (const mutation of mutations) {
      expect(evaluateRestorePretrafficReadiness(input({
        terminal_feed_coverage: coverage(checkpoint(), mutation),
      }))).toMatchObject({ kind: "blocked", blockers: ["terminal_feed_coverage_mismatch"] });
    }
    const changed = candidate();
    changed.checkpoint = { ...changed.checkpoint, restore_id: "restore-other" } as never;
    expect(() => evaluateRestorePretrafficReadiness(input({ checkpoint_candidate: changed })))
      .toThrow(RestorePretrafficReadinessInputError);
  });

  test("incomplete and lagging feed coverage block even beyond checkpoint high-water", () => {
    for (const patch of [
      { state: "incomplete" as const },
      { source_current_high_watermark: 12 },
      { source_current_high_watermark: 12, applied_through_high_watermark: 11 },
    ]) {
      expect(evaluateRestorePretrafficReadiness(input({
        terminal_feed_coverage: coverage(checkpoint(), patch),
      }))).toMatchObject({ kind: "blocked", blockers: ["terminal_feed_coverage_incomplete"] });
    }
    expect(evaluateRestorePretrafficReadiness(input({
      terminal_feed_coverage: coverage(checkpoint(), {
        source_current_high_watermark: 14,
        gap_free_through_high_watermark: 14,
        applied_through_high_watermark: 14,
      }),
    }))).toMatchObject({ kind: "blocked", blockers: ["terminal_feed_coverage_mismatch"] });
  });

  test("target identity, candidate bytes, and stable persistence receipt resist substitution", () => {
    expect(evaluateRestorePretrafficReadiness(input({
      generation_attestation: {
        version: RESTORE_GENERATION_ATTESTATION_VERSION,
        state: "current",
        restore_id: restore.restore_id,
        restore_scope: restore.restore_scope,
        restored_generation_digest: restore.restored_generation_digest,
        restored_snapshot_digest: restore.restored_snapshot_digest,
        target_identity_digest: hash("9"),
        attestation_receipt_digest: hash("8"),
      },
    }))).toMatchObject({ kind: "blocked", blockers: ["generation_attestation_mismatch"] });

    for (const mutation of [
      { candidate_digest: hash("a") },
      { persistence_receipt_digest: hash("b") },
      { recorded_at_epoch_micros: "1800000000123457" },
      { source_feed_generation_digest: hash("c") },
      { partition_topology_digest: hash("d") },
    ] as const) {
      expect(() => evaluateRestorePretrafficReadiness(input({
        checkpoint_candidate: { ...candidate(), ...mutation },
      }))).toThrow(RestorePretrafficReadinessInputError);
    }
  });

  test("every current-control denial remains a pretraffic blocker", () => {
    for (const [projection, reason] of [
      [null, "control_state_absent"],
      [control({ conflict: { at_control_revision: 13, detail: "projection_conflicted" } }),
        "control_state_conflicting"],
      [control({ lifecycle_state: "deleted", deletion_epoch: 20 }), "account_lifecycle_not_active"],
      [control({ account_generation: "legacy" }), "account_generation_legacy"],
      [control({ activation: null }), "control_state_not_activated"],
    ] as const) {
      expect(evaluateRestorePretrafficReadiness(input({ control_projection: projection })))
        .toMatchObject({ kind: "blocked", blockers: expect.arrayContaining([reason]) });
    }
  });

  test("any latest retained terminal fence blocks, with higher epochs exactly dominant", () => {
    for (const deletionEpoch of [1, 20, Number.MAX_SAFE_INTEGER]) {
      expect(evaluateRestorePretrafficReadiness(input({
        retained_fence_observation: {
          version: RETAINED_TERMINAL_FENCE_OBSERVATION_VERSION,
          state: "current",
          latest_fence: {
            version: RETAINED_TERMINAL_FENCE_VERSION,
            account_id: ACCOUNT,
            deletion_epoch: deletionEpoch,
            control_revision: deletionEpoch,
            terminal_record_digest: hash("b"),
            source_restore_id: "older-or-newer-restore",
            restored_snapshot_digest: hash("c"),
            fence_receipt_digest: hash("d"),
          },
          observation_receipt_digest: hash("e"),
        },
      }))).toMatchObject({ kind: "blocked", blockers: ["retained_terminal_fence_present"] });
    }
    expect(evaluateRestorePretrafficReadiness(input({
      retained_fence_observation: {
        version: RETAINED_TERMINAL_FENCE_OBSERVATION_VERSION,
        state: "unavailable",
      },
    }))).toMatchObject({ kind: "blocked", blockers: ["retained_fence_unavailable"] });
  });

  test("control drift changes evidence and a final denial cannot reuse earlier clear bytes", () => {
    const before = evaluateRestorePretrafficReadiness(input());
    const revisionDrift = evaluateRestorePretrafficReadiness(input({
      control_projection: control({ control_revision: 13 }),
    }));
    const lifecycleDrift = evaluateRestorePretrafficReadiness(input({
      control_projection: control({ lifecycle_state: "deletion_pending", deletion_epoch: 21 }),
    }));
    expect(revisionDrift.kind).toBe("consistent_checkpoint_evidence");
    expect(revisionDrift.readiness_evidence_digest).not.toBe(before.readiness_evidence_digest);
    expect(lifecycleDrift.kind).toBe("blocked");
    expect(lifecycleDrift.readiness_evidence_digest).not.toBe(before.readiness_evidence_digest);
  });

  test("hostile values fail without accessors and output never carries content", () => {
    let getterCalls = 0;
    const hostile = { ...input() } as Record<string, unknown>;
    Object.defineProperty(hostile, "control_projection", {
      enumerable: true,
      get() { getterCalls += 1; return control(); },
    });
    expect(() => evaluateRestorePretrafficReadiness(hostile))
      .toThrow(RestorePretrafficReadinessInputError);
    expect(getterCalls).toBe(0);
    expect(() => evaluateRestorePretrafficReadiness(new Proxy(input(), {})))
      .toThrow(RestorePretrafficReadinessInputError);

    const blocked = evaluateRestorePretrafficReadiness(input({
      retained_fence_observation: {
        version: RETAINED_TERMINAL_FENCE_OBSERVATION_VERSION,
        state: "unavailable",
      },
    }));
    expect(JSON.stringify(blocked)).not.toContain(ACCOUNT);
    expect(JSON.stringify(blocked)).not.toMatch(/transcript|memory|prompt|provider|path/);
  });

  test("results are detached and deterministic across later input mutation", () => {
    const mutable = input();
    const first = evaluateRestorePretrafficReadiness(mutable);
    const bytes = JSON.stringify(first);
    (mutable.control_projection as { lifecycle_state: string }).lifecycle_state = "deleted";
    expect(JSON.stringify(first)).toBe(bytes);
    expect(evaluateRestorePretrafficReadiness(input())).toEqual(first);
  });
});
