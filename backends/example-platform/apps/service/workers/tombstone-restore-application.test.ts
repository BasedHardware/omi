import { describe, expect, test } from "bun:test";

import {
  TERMINAL_APPLICATION_OUTCOME_VERSION,
  TERMINAL_FEED_FENCE_VERSION,
  TERMINAL_SET_SOURCE_RECEIPT_VERSION,
  buildTerminalReplayManifest,
  type RestoreCoordinate,
  type TerminalApplicationOutcome,
  type TerminalFeedFence,
  type TerminalReplayManifestRecord,
} from "../../../core/control/tombstone-restore-replay";
import {
  defineTombstoneRestoreApplicationCoordinator,
  type CompleteTerminalSet,
  type HeldTerminalFeedFenceSession,
  type TerminalFeedFencePort,
  type TombstoneRestoreApplicationDependencies,
} from "./tombstone-restore-application";

const hash = (value: string): string => value.repeat(64);
const restore: RestoreCoordinate = {
  restore_id: "restore-app-1",
  restore_scope: "postgresql",
  restored_snapshot_digest: hash("a"),
  restore_completed_at_epoch_seconds: 100,
};
const records: readonly TerminalReplayManifestRecord[] = [
  { account_id: "acct-a", control_revision: 3, deletion_epoch: 5, terminal_record_digest: hash("1") },
  { account_id: "acct-b", control_revision: 4, deletion_epoch: 6, terminal_record_digest: hash("2") },
];

const terminalSet = (
  terminalRecords: readonly TerminalReplayManifestRecord[] = records,
): CompleteTerminalSet => {
  const manifest = buildTerminalReplayManifest({
    source_snapshot_digest: hash("b"),
    source_high_watermark: 12,
    captured_at_epoch_seconds: 101,
    records: terminalRecords,
  });
  return {
    manifest,
    source_receipt: {
      version: TERMINAL_SET_SOURCE_RECEIPT_VERSION,
      sink_contract_version: "retention-sink-v1",
      source_snapshot_digest: manifest.source_snapshot_digest,
      source_high_watermark: manifest.source_high_watermark,
      record_count: manifest.records.length,
      manifest_digest: manifest.manifest_digest,
      retention_locked_sink_receipt_digest: hash("c"),
    },
  };
};

const heldFence = (overrides: Partial<TerminalFeedFence> = {}): TerminalFeedFence => ({
  version: TERMINAL_FEED_FENCE_VERSION,
  state: "held",
  restore_id: restore.restore_id,
  restore_scope: restore.restore_scope,
  source_snapshot_digest: hash("b"),
  source_high_watermark: 12,
  fence_receipt_digest: hash("d"),
  ...overrides,
});

const application = (
  record: TerminalReplayManifestRecord,
  result: TerminalApplicationOutcome["result"] = "applied",
  overrides: Partial<TerminalApplicationOutcome> = {},
): TerminalApplicationOutcome => ({
  version: TERMINAL_APPLICATION_OUTCOME_VERSION,
  restore_id: restore.restore_id,
  restore_scope: restore.restore_scope,
  restored_snapshot_digest: restore.restored_snapshot_digest,
  account_id: record.account_id,
  control_revision: record.control_revision,
  deletion_epoch: record.deletion_epoch,
  terminal_record_digest: record.terminal_record_digest,
  result,
  target_receipt_digest: result === "applied" || result === "already_absent" ? hash("e") : null,
  error_code: result === "retryable_error" ? "target_unavailable"
    : result === "terminal_error" ? "target_verification_failed" : null,
  ...overrides,
});

const dependencies = (options: {
  source?: CompleteTerminalSet | null;
  fences?: readonly (TerminalFeedFence | null)[];
  apply?: (record: TerminalReplayManifestRecord, index: number) => Promise<TerminalApplicationOutcome | null>;
  sourceError?: Error;
  fenceError?: Error;
} = {}) => {
  const calls: string[] = [];
  const source = options.source === undefined ? terminalSet() : options.source;
  const fences = [...(options.fences ?? [heldFence(), heldFence()])];
  let applicationIndex = 0;
  const value: TombstoneRestoreApplicationDependencies = {
    terminal_set_source: {
      async loadCompleteTerminalSet(valueRestore) {
        calls.push("source");
        expect(Object.isFrozen(valueRestore)).toBe(true);
        if (options.sourceError) throw options.sourceError;
        return source;
      },
    },
    terminal_feed_fence: {
      async withHeldTerminalFeedFence(request, callback) {
        calls.push("fence:enter");
        expect(Object.isFrozen(request)).toBe(true);
        if (options.fenceError) throw options.fenceError;
        let readIndex = 0;
        const session: HeldTerminalFeedFenceSession = {
          async readCurrentFence() {
            calls.push("fence:read");
            return fences[readIndex++] ?? null;
          },
        };
        try { return await callback(session); } finally { calls.push("fence:exit"); }
      },
    },
    target_application: {
      async applyTerminalRecord(request) {
        calls.push(`apply:${request.terminal_record.account_id}`);
        expect(Object.isFrozen(request)).toBe(true);
        const index = applicationIndex++;
        return options.apply
          ? options.apply(request.terminal_record, index)
          : application(request.terminal_record, index === 0 ? "applied" : "already_absent");
      },
    },
  };
  return { value, calls };
};

describe("tombstone restore application coordinator", () => {
  test("complete and exact-empty terminal sets checkpoint under one continuously held fence", async () => {
    for (const source of [terminalSet(), terminalSet([])]) {
      const fixture = dependencies({ source });
      const coordinator = defineTombstoneRestoreApplicationCoordinator(fixture.value);
      const outcome = await coordinator.run(restore);
      expect(outcome.kind).toBe("evaluated");
      if (outcome.kind !== "evaluated") throw new Error("expected evaluated");
      expect(outcome.report.checkpoint?.checkpoint_digest).toMatch(/^[0-9a-f]{64}$/);
      expect(outcome.report.record_count).toBe(source.manifest.records.length);
      expect(outcome.report.successful_count).toBe(source.manifest.records.length);
      expect(Object.isFrozen(coordinator)).toBe(true);
      expect(Object.isFrozen(outcome)).toBe(true);
      expect(Object.isFrozen(outcome.report)).toBe(true);
      expect(fixture.calls.at(-2)).toBe("fence:read");
      expect(fixture.calls.at(-1)).toBe("fence:exit");
    }
  });

  test("missing source is not converted to an empty terminal set", async () => {
    const fixture = dependencies({ source: null });
    expect(await defineTombstoneRestoreApplicationCoordinator(fixture.value).run(restore))
      .toEqual({ kind: "stopped", stop_code: "terminal_set_missing" });
    expect(fixture.calls).toEqual(["source"]);
  });

  test("missing, retryable, and terminal target outcomes remain distinct blockers", async () => {
    const missing = dependencies({ apply: async (record, index) => index === 0 ? application(record) : null });
    const missingOutcome = await defineTombstoneRestoreApplicationCoordinator(missing.value).run(restore);
    expect(missingOutcome.kind === "evaluated" && missingOutcome.report.blockers)
      .toEqual(["application_missing"]);

    for (const [result, blocker] of [
      ["retryable_error", "application_retryable_error"],
      ["terminal_error", "application_terminal_error"],
    ] as const) {
      const fixture = dependencies({
        apply: async (record, index) => application(record, index === 0 ? result : "applied"),
      });
      const outcome = await defineTombstoneRestoreApplicationCoordinator(fixture.value).run(restore);
      expect(outcome.kind === "evaluated" && outcome.report.blockers).toEqual([blocker]);
      expect(outcome.kind === "evaluated" && outcome.report.checkpoint).toBeNull();
    }
  });

  test("released or replaced fences after target awaits cannot produce a checkpoint", async () => {
    for (const finalFence of [
      heldFence({ state: "released" }),
      heldFence({ fence_receipt_digest: hash("f") }),
      heldFence({ source_high_watermark: 13 }),
      null,
    ]) {
      const fixture = dependencies({ fences: [heldFence(), finalFence] });
      const outcome = await defineTombstoneRestoreApplicationCoordinator(fixture.value).run(restore);
      expect(outcome.kind === "evaluated" && outcome.report.blockers)
        .toContain("terminal_feed_not_held");
      expect(outcome.kind === "evaluated" && outcome.report.checkpoint).toBeNull();
    }
  });

  test("an invalid initial fence blocks before any target application", async () => {
    const fixture = dependencies({ fences: [heldFence({ state: "released" })] });
    const outcome = await defineTombstoneRestoreApplicationCoordinator(fixture.value).run(restore);
    expect(outcome.kind === "evaluated" && outcome.report.blockers)
      .toContain("terminal_feed_not_held");
    expect(fixture.calls.filter((call) => call.startsWith("apply:"))).toEqual([]);
  });

  test("duplicate and foreign target outcomes fail closed", async () => {
    const duplicate = dependencies({
      apply: async (_record, index) => application(records[0]!, index === 0 ? "applied" : "already_absent"),
    });
    expect(await defineTombstoneRestoreApplicationCoordinator(duplicate.value).run(restore))
      .toEqual({ kind: "stopped", stop_code: "target_application_invalid" });

    const foreign = dependencies({
      apply: async (record, index) => application(record, "applied", index === 0
        ? { restore_id: "foreign-restore" } : {}),
    });
    expect(await defineTombstoneRestoreApplicationCoordinator(foreign.value).run(restore))
      .toEqual({ kind: "stopped", stop_code: "target_application_invalid" });
  });

  test("dependency failures collapse to content-safe closed codes", async () => {
    const secret = "sensitive transcript and database path";
    const sourceFailure = dependencies({ sourceError: new Error(secret) });
    const sourceOutcome = await defineTombstoneRestoreApplicationCoordinator(sourceFailure.value)
      .run(restore);
    expect(sourceOutcome).toEqual({ kind: "stopped", stop_code: "terminal_set_dependency_failed" });

    const targetFailure = dependencies({ apply: async () => { throw new Error(secret); } });
    const targetOutcome = await defineTombstoneRestoreApplicationCoordinator(targetFailure.value)
      .run(restore);
    expect(targetOutcome).toEqual({ kind: "stopped", stop_code: "target_application_dependency_failed" });
    expect(JSON.stringify([sourceOutcome, targetOutcome])).not.toContain(secret);
  });

  test("hostile restore and malformed source are rejected without opening a fence", async () => {
    const fixture = dependencies();
    let getterCalls = 0;
    const hostile: Record<string, unknown> = {
      restore_id: restore.restore_id,
      restore_scope: restore.restore_scope,
      restored_snapshot_digest: restore.restored_snapshot_digest,
    };
    Object.defineProperty(hostile, "restore_completed_at_epoch_seconds", {
      enumerable: true,
      get() { getterCalls += 1; return 100; },
    });
    await expect(defineTombstoneRestoreApplicationCoordinator(fixture.value).run(hostile as never))
      .rejects.toThrow("invalid restore input");
    expect(getterCalls).toBe(0);
    expect(fixture.calls).toEqual([]);

    const malformed = dependencies({ source: { manifest: terminalSet().manifest } as never });
    expect(await defineTombstoneRestoreApplicationCoordinator(malformed.value).run(restore))
      .toEqual({ kind: "stopped", stop_code: "terminal_set_invalid" });
    expect(malformed.calls).toEqual(["source"]);
  });

  test("hostile fence and application accessors are never invoked", async () => {
    let fenceGetterCalls = 0;
    const hostileFence = { ...heldFence() } as Record<string, unknown>;
    Object.defineProperty(hostileFence, "state", {
      enumerable: true,
      get() { fenceGetterCalls += 1; return "held"; },
    });
    const fenced = dependencies({ fences: [heldFence(), hostileFence as never] });
    expect(await defineTombstoneRestoreApplicationCoordinator(fenced.value).run(restore))
      .toEqual({ kind: "stopped", stop_code: "terminal_feed_fence_invalid" });
    expect(fenceGetterCalls).toBe(0);

    let applicationGetterCalls = 0;
    const hostileApplication = { ...application(records[0]!) } as Record<string, unknown>;
    Object.defineProperty(hostileApplication, "result", {
      enumerable: true,
      get() { applicationGetterCalls += 1; return "applied"; },
    });
    const applied = dependencies({
      apply: async (_record, index) => index === 0 ? hostileApplication as never : null,
    });
    expect(await defineTombstoneRestoreApplicationCoordinator(applied.value).run(restore))
      .toEqual({ kind: "stopped", stop_code: "target_application_invalid" });
    expect(applicationGetterCalls).toBe(0);
  });

  test("a captured callback invoked after the fence wrapper returns performs no I/O", async () => {
    let captured: ((session: HeldTerminalFeedFenceSession) => Promise<unknown>) | null = null;
    let fenceReads = 0;
    let targetCalls = 0;
    const base = dependencies().value;
    const escapingFence: TerminalFeedFencePort = {
      async withHeldTerminalFeedFence<T>(_request: unknown, callback: (
        session: HeldTerminalFeedFenceSession,
      ) => Promise<T>): Promise<T> {
        captured = callback as (session: HeldTerminalFeedFenceSession) => Promise<unknown>;
        return Object.freeze({
          kind: "stopped",
          stop_code: "terminal_feed_fence_dependency_failed",
        }) as T;
      },
    };
    const coordinator = defineTombstoneRestoreApplicationCoordinator({
      ...base,
      terminal_feed_fence: escapingFence,
      target_application: {
        async applyTerminalRecord() { targetCalls += 1; return null; },
      },
    });
    expect(await coordinator.run(restore)).toEqual({
      kind: "stopped", stop_code: "terminal_feed_fence_dependency_failed",
    });
    expect(captured).not.toBeNull();
    const invoke = captured as unknown as (
      session: HeldTerminalFeedFenceSession,
    ) => Promise<unknown>;
    expect(await invoke({
      async readCurrentFence() { fenceReads += 1; return heldFence(); },
    })).toEqual({ kind: "stopped", stop_code: "terminal_feed_fence_dependency_failed" });
    expect(fenceReads).toBe(0);
    expect(targetCalls).toBe(0);
  });

  test("an in-flight callback that resumes after wrapper return cannot begin target work", async () => {
    let releaseRead: ((value: TerminalFeedFence) => void) | null = null;
    const pendingRead = new Promise<TerminalFeedFence>((resolve) => { releaseRead = resolve; });
    let escaped: Promise<unknown> | null = null;
    let fenceReads = 0;
    let targetCalls = 0;
    const base = dependencies().value;
    const coordinator = defineTombstoneRestoreApplicationCoordinator({
      ...base,
      terminal_feed_fence: {
        async withHeldTerminalFeedFence<T>(_request, callback): Promise<T> {
          escaped = callback({
            async readCurrentFence() { fenceReads += 1; return pendingRead; },
          });
          return Object.freeze({
            kind: "stopped",
            stop_code: "terminal_feed_fence_dependency_failed",
          }) as T;
        },
      },
      target_application: {
        async applyTerminalRecord() { targetCalls += 1; return null; },
      },
    });
    expect(await coordinator.run(restore)).toEqual({
      kind: "stopped", stop_code: "terminal_feed_fence_dependency_failed",
    });
    expect(fenceReads).toBe(1);
    const resolveRead = releaseRead as unknown as (value: TerminalFeedFence) => void;
    resolveRead(heldFence());
    const escapedResult = escaped as unknown as Promise<unknown>;
    expect(await escapedResult).toEqual({
      kind: "stopped", stop_code: "terminal_feed_fence_dependency_failed",
    });
    expect(targetCalls).toBe(0);
  });

  test("captures exact dependency methods before any await and rejects dependency accessors", async () => {
    const fixture = dependencies();
    const coordinator = defineTombstoneRestoreApplicationCoordinator(fixture.value);
    fixture.value.terminal_set_source.loadCompleteTerminalSet = async () => null;
    fixture.value.terminal_feed_fence.withHeldTerminalFeedFence = async () => {
      throw new Error("mutated fence method");
    };
    fixture.value.target_application.applyTerminalRecord = async () => {
      throw new Error("mutated target method");
    };
    const outcome = await coordinator.run(restore);
    expect(outcome.kind === "evaluated" && outcome.report.checkpoint).not.toBeNull();

    for (const key of ["terminal_set_source", "terminal_feed_fence", "target_application"] as const) {
      let getterCalls = 0;
      const hostile = { ...fixture.value } as Record<string, unknown>;
      Object.defineProperty(hostile, key, {
        enumerable: true,
        get() { getterCalls += 1; return fixture.value[key]; },
      });
      expect(() => defineTombstoneRestoreApplicationCoordinator(hostile as never))
        .toThrow("invalid restore input");
      expect(getterCalls).toBe(0);
    }

    let methodGetterCalls = 0;
    const hostileSource: Record<string, unknown> = {};
    Object.defineProperty(hostileSource, "loadCompleteTerminalSet", {
      enumerable: true,
      get() { methodGetterCalls += 1; return async () => terminalSet(); },
    });
    expect(() => defineTombstoneRestoreApplicationCoordinator({
      ...fixture.value,
      terminal_set_source: hostileSource as never,
    })).toThrow("invalid restore input");
    expect(methodGetterCalls).toBe(0);
  });

  test("captures the held-session reader and rejects session accessors without invoking them", async () => {
    const fixture = dependencies();
    let getterCalls = 0;
    const hostileSession: Record<string, unknown> = {};
    Object.defineProperty(hostileSession, "readCurrentFence", {
      enumerable: true,
      get() { getterCalls += 1; return async () => heldFence(); },
    });
    const outcome = await defineTombstoneRestoreApplicationCoordinator({
      ...fixture.value,
      terminal_feed_fence: {
        async withHeldTerminalFeedFence(_request, callback) {
          return callback(hostileSession as never);
        },
      },
    }).run(restore);
    expect(outcome).toEqual({ kind: "stopped", stop_code: "terminal_feed_fence_invalid" });
    expect(getterCalls).toBe(0);

    let reads = 0;
    const mutableSession: HeldTerminalFeedFenceSession = {
      async readCurrentFence() {
        reads += 1;
        mutableSession.readCurrentFence = async () => {
          throw new Error("mutated session reader");
        };
        return heldFence();
      },
    };
    const stable = await defineTombstoneRestoreApplicationCoordinator({
      ...fixture.value,
      terminal_feed_fence: {
        async withHeldTerminalFeedFence(_request, callback) { return callback(mutableSession); },
      },
    }).run(restore);
    expect(stable.kind === "evaluated" && stable.report.checkpoint).not.toBeNull();
    expect(reads).toBe(2);
  });

  test("a broken wrapper releasing during an in-flight target write cannot yield a checkpoint", async () => {
    let releaseTarget: ((outcome: TerminalApplicationOutcome) => void) | null = null;
    const pendingTarget = new Promise<TerminalApplicationOutcome>((resolve) => {
      releaseTarget = resolve;
    });
    let escaped: Promise<unknown> | null = null;
    let fenceReads = 0;
    const source = terminalSet([records[0]!]);
    const base = dependencies({
      source,
      apply: async () => pendingTarget,
    }).value;
    const coordinator = defineTombstoneRestoreApplicationCoordinator({
      ...base,
      terminal_feed_fence: {
        async withHeldTerminalFeedFence<T>(_request, callback): Promise<T> {
          escaped = callback({
            async readCurrentFence() { fenceReads += 1; return heldFence(); },
          });
          while (fenceReads === 0) await Promise.resolve();
          return Object.freeze({
            kind: "stopped",
            stop_code: "terminal_feed_fence_dependency_failed",
          }) as T;
        },
      },
    });
    const outer = await coordinator.run(restore);
    expect(outer).toEqual({ kind: "stopped", stop_code: "terminal_feed_fence_dependency_failed" });
    const resolveTarget = releaseTarget as unknown as (outcome: TerminalApplicationOutcome) => void;
    resolveTarget(application(records[0]!));
    const escapedResult = escaped as unknown as Promise<unknown>;
    expect(await escapedResult).toEqual({
      kind: "stopped", stop_code: "terminal_feed_fence_dependency_failed",
    });
    expect(fenceReads).toBe(1);
    expect(JSON.stringify(escapedResult)).not.toContain("checkpoint_digest");
  });
});
