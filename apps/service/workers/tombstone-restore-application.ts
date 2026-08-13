import { isProxy } from "node:util/types";

import {
  TERMINAL_FEED_FENCE_VERSION,
  verifyTombstoneRestoreReplay,
  type RestoreCoordinate,
  type TerminalApplicationOutcome,
  type TerminalFeedFence,
  type TerminalReplayManifest,
  type TerminalReplayManifestRecord,
  type TerminalSetSourceReceipt,
  type TombstoneReplayReport,
} from "../../../core/control/tombstone-restore-replay";

const COORDINATOR: unique symbol = Symbol("tombstone-restore-application-coordinator");
const DIGEST = /^[0-9a-f]{64}$/;
const MAX_COORDINATE_LENGTH = 256;

export interface CompleteTerminalSet {
  readonly manifest: TerminalReplayManifest;
  readonly source_receipt: TerminalSetSourceReceipt;
}

export interface RetentionLockedTerminalSetPort {
  /** Missing source state must be returned as null, never as an empty manifest. */
  loadCompleteTerminalSet(restore: RestoreCoordinate): Promise<CompleteTerminalSet | null>;
}

export interface HeldTerminalFeedFenceSession {
  /** Reads the current fence receipt; null means no held-fence proof exists. */
  readCurrentFence(): Promise<TerminalFeedFence | null>;
}

export interface TerminalFeedFencePort {
  /**
   * The adapter guarantees the same source fence surrounds the whole callback.
   * The coordinator independently checks its receipt before and after target work.
   */
  withHeldTerminalFeedFence<T>(
    request: Readonly<{
      restore: RestoreCoordinate;
      source_snapshot_digest: string;
      source_high_watermark: number;
      manifest_digest: string;
    }>,
    callback: (session: HeldTerminalFeedFenceSession) => Promise<T>,
  ): Promise<T>;
}

export interface TerminalRecordApplicationPort {
  /** Null is explicit missing progress and can never become a successful outcome. */
  applyTerminalRecord(request: Readonly<{
    restore: RestoreCoordinate;
    terminal_record: TerminalReplayManifestRecord;
  }>): Promise<TerminalApplicationOutcome | null>;
}

export interface TombstoneRestoreApplicationDependencies {
  readonly terminal_set_source: RetentionLockedTerminalSetPort;
  readonly terminal_feed_fence: TerminalFeedFencePort;
  readonly target_application: TerminalRecordApplicationPort;
}

export type TombstoneRestoreApplicationStopCode =
  | "terminal_set_missing"
  | "terminal_set_dependency_failed"
  | "terminal_set_invalid"
  | "terminal_feed_fence_dependency_failed"
  | "terminal_feed_fence_invalid"
  | "target_application_dependency_failed"
  | "target_application_invalid";

export type TombstoneRestoreApplicationOutcome =
  | Readonly<{ kind: "evaluated"; report: TombstoneReplayReport }>
  | Readonly<{ kind: "stopped"; stop_code: TombstoneRestoreApplicationStopCode }>;

export interface TombstoneRestoreApplicationCoordinator {
  readonly [COORDINATOR]: true;
  /** Produces a lifecycle report only. It never opens traffic or mints authority. */
  run(restore: RestoreCoordinate): Promise<TombstoneRestoreApplicationOutcome>;
}

type PlainRecord = Record<string, unknown>;

const exactRecord = (value: unknown, keys: readonly string[]): PlainRecord => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) throw new TypeError("invalid restore input");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  if (actual.some((key) => typeof key !== "string") || actual.length !== keys.length
    || keys.some((key) => !Object.prototype.hasOwnProperty.call(descriptors, key))) {
    throw new TypeError("invalid restore input");
  }
  const detached: PlainRecord = {};
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (descriptor === undefined || !descriptor.enumerable || !("value" in descriptor)) {
      throw new TypeError("invalid restore input");
    }
    detached[key] = descriptor.value;
  }
  return detached;
};

const ownMethod = <Arguments extends readonly unknown[], Result>(
  owner: unknown,
  key: string,
): ((...arguments_: Arguments) => Result) => {
  const row = exactRecord(owner, [key]);
  const method = row[key];
  if (typeof method !== "function" || isProxy(method)) throw new TypeError("invalid restore dependency");
  return method.bind(owner) as (...arguments_: Arguments) => Result;
};

const boundedCoordinate = (value: unknown): value is string => typeof value === "string"
  && value.length > 0 && value.length <= MAX_COORDINATE_LENGTH && /^[\x21-\x7e]+$/.test(value);

const safeEpoch = (value: unknown): value is number => typeof value === "number"
  && Number.isSafeInteger(value) && value >= 0;

const parseRestore = (value: unknown): RestoreCoordinate => {
  const row = exactRecord(value, [
    "restore_id", "restore_scope", "restored_snapshot_digest",
    "restore_completed_at_epoch_seconds",
  ]);
  if (!boundedCoordinate(row.restore_id)
    || (row.restore_scope !== "legacy" && row.restore_scope !== "postgresql")
    || typeof row.restored_snapshot_digest !== "string" || !DIGEST.test(row.restored_snapshot_digest)
    || !safeEpoch(row.restore_completed_at_epoch_seconds)) throw new TypeError("invalid restore input");
  return Object.freeze({
    restore_id: row.restore_id,
    restore_scope: row.restore_scope,
    restored_snapshot_digest: row.restored_snapshot_digest,
    restore_completed_at_epoch_seconds: row.restore_completed_at_epoch_seconds,
  });
};

const deepFreeze = <T>(value: T): T => {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value)) deepFreeze(child);
  }
  return value;
};

const stopped = (
  stop_code: TombstoneRestoreApplicationStopCode,
): TombstoneRestoreApplicationOutcome => Object.freeze({ kind: "stopped" as const, stop_code });

const sameFence = (left: TerminalFeedFence | null, right: TerminalFeedFence | null): boolean =>
  left !== null && right !== null
  && left.version === TERMINAL_FEED_FENCE_VERSION && right.version === TERMINAL_FEED_FENCE_VERSION
  && left.state === "held" && right.state === "held"
  && left.restore_id === right.restore_id
  && left.restore_scope === right.restore_scope
  && left.source_snapshot_digest === right.source_snapshot_digest
  && left.source_high_watermark === right.source_high_watermark
  && left.fence_receipt_digest === right.fence_receipt_digest;

const validateTerminalSet = (
  restore: RestoreCoordinate,
  value: unknown,
): CompleteTerminalSet => {
  const row = exactRecord(value, ["manifest", "source_receipt"]);
  verifyTombstoneRestoreReplay({
    restore,
    manifest: row.manifest,
    source_receipt: row.source_receipt,
    traffic_fence: null,
    applications: [],
  });
  // Detach the validated source synchronously so later adapter mutation cannot
  // change the coordinates used under the fence.
  const detached = deepFreeze(structuredClone({
    manifest: row.manifest,
    source_receipt: row.source_receipt,
  })) as CompleteTerminalSet;
  verifyTombstoneRestoreReplay({
    restore,
    manifest: detached.manifest,
    source_receipt: detached.source_receipt,
    traffic_fence: null,
    applications: [],
  });
  return detached;
};

export const defineTombstoneRestoreApplicationCoordinator = (
  dependenciesValue: TombstoneRestoreApplicationDependencies,
): TombstoneRestoreApplicationCoordinator => {
  const dependencies = exactRecord(dependenciesValue, [
    "terminal_set_source", "terminal_feed_fence", "target_application",
  ]);
  const loadCompleteTerminalSet = ownMethod<
    readonly [RestoreCoordinate], Promise<CompleteTerminalSet | null>
  >(dependencies.terminal_set_source, "loadCompleteTerminalSet");
  const withHeldTerminalFeedFence = ownMethod<
    readonly [
      Readonly<{
        restore: RestoreCoordinate;
        source_snapshot_digest: string;
        source_high_watermark: number;
        manifest_digest: string;
      }>,
      (session: HeldTerminalFeedFenceSession) => Promise<TombstoneRestoreApplicationOutcome>,
    ],
    Promise<TombstoneRestoreApplicationOutcome>
  >(dependencies.terminal_feed_fence, "withHeldTerminalFeedFence");
  const applyTerminalRecord = ownMethod<
    readonly [Readonly<{
      restore: RestoreCoordinate;
      terminal_record: TerminalReplayManifestRecord;
    }>],
    Promise<TerminalApplicationOutcome | null>
  >(dependencies.target_application, "applyTerminalRecord");

  return Object.freeze({
  [COORDINATOR]: true as const,
  async run(restoreValue: RestoreCoordinate): Promise<TombstoneRestoreApplicationOutcome> {
    const restore = parseRestore(restoreValue);
    let sourceValue: CompleteTerminalSet | null;
    try {
      sourceValue = await loadCompleteTerminalSet(restore);
    } catch {
      return stopped("terminal_set_dependency_failed");
    }
    if (sourceValue === null) return stopped("terminal_set_missing");

    let source: CompleteTerminalSet;
    try {
      source = validateTerminalSet(restore, sourceValue);
    } catch {
      return stopped("terminal_set_invalid");
    }

    const fenceRequest = Object.freeze({
      restore,
      source_snapshot_digest: source.manifest.source_snapshot_digest,
      source_high_watermark: source.manifest.source_high_watermark,
      manifest_digest: source.manifest.manifest_digest,
    });
    let callbackCount = 0;
    let callbackResult: TombstoneRestoreApplicationOutcome | undefined;
    let returned: TombstoneRestoreApplicationOutcome;
    let callbackLeaseOpen = true;
    try {
      returned = await withHeldTerminalFeedFence(
        fenceRequest,
        async (session) => {
          if (!callbackLeaseOpen) return stopped("terminal_feed_fence_dependency_failed");
          callbackCount += 1;
          if (callbackCount !== 1) {
            callbackResult = stopped("terminal_feed_fence_dependency_failed");
            return callbackResult;
          }
          let readCurrentFence: () => Promise<TerminalFeedFence | null>;
          try {
            readCurrentFence = ownMethod<readonly [], Promise<TerminalFeedFence | null>>(
              session,
              "readCurrentFence",
            );
          } catch {
            callbackResult = stopped("terminal_feed_fence_invalid");
            return callbackResult;
          }

          let initialFence: TerminalFeedFence | null;
          try {
            initialFence = await readCurrentFence();
          } catch {
            callbackResult = stopped("terminal_feed_fence_dependency_failed");
            return callbackResult;
          }
          if (!callbackLeaseOpen) {
            callbackResult = stopped("terminal_feed_fence_dependency_failed");
            return callbackResult;
          }

          let preflight: TombstoneReplayReport;
          try {
            preflight = verifyTombstoneRestoreReplay({
              restore,
              manifest: source.manifest,
              source_receipt: source.source_receipt,
              traffic_fence: initialFence,
              applications: [],
            });
            initialFence = deepFreeze(structuredClone(initialFence));
            preflight = verifyTombstoneRestoreReplay({
              restore,
              manifest: source.manifest,
              source_receipt: source.source_receipt,
              traffic_fence: initialFence,
              applications: [],
            });
          } catch {
            callbackResult = stopped("terminal_feed_fence_invalid");
            return callbackResult;
          }
          if (preflight.blockers.includes("terminal_set_predates_restore")
            || preflight.blockers.includes("terminal_feed_not_held")) {
            callbackResult = Object.freeze({ kind: "evaluated" as const, report: preflight });
            return callbackResult;
          }

          const applications: TerminalApplicationOutcome[] = [];
          for (const terminalRecord of source.manifest.records) {
            let application: TerminalApplicationOutcome | null;
            try {
              application = await applyTerminalRecord(Object.freeze({
                restore,
                terminal_record: terminalRecord,
              }));
            } catch {
              callbackResult = stopped("target_application_dependency_failed");
              return callbackResult;
            }
            if (!callbackLeaseOpen) {
              callbackResult = stopped("terminal_feed_fence_dependency_failed");
              return callbackResult;
            }
            if (application !== null) {
              try {
                // Validate and detach before the next await so an adapter cannot
                // mutate an earlier result while a later record is in flight.
                verifyTombstoneRestoreReplay({
                  restore,
                  manifest: source.manifest,
                  source_receipt: source.source_receipt,
                  traffic_fence: initialFence,
                  applications: [application],
                });
                const detached = deepFreeze(structuredClone(application));
                verifyTombstoneRestoreReplay({
                  restore,
                  manifest: source.manifest,
                  source_receipt: source.source_receipt,
                  traffic_fence: initialFence,
                  applications: [detached],
                });
                applications.push(detached);
              } catch {
                callbackResult = stopped("target_application_invalid");
                return callbackResult;
              }
            }
          }

          let finalFence: TerminalFeedFence | null;
          try {
            finalFence = await readCurrentFence();
          } catch {
            callbackResult = stopped("terminal_feed_fence_dependency_failed");
            return callbackResult;
          }
          if (!callbackLeaseOpen) {
            callbackResult = stopped("terminal_feed_fence_dependency_failed");
            return callbackResult;
          }

          try {
            verifyTombstoneRestoreReplay({
              restore,
              manifest: source.manifest,
              source_receipt: source.source_receipt,
              traffic_fence: finalFence,
              applications: [],
            });
            finalFence = deepFreeze(structuredClone(finalFence));
            verifyTombstoneRestoreReplay({
              restore,
              manifest: source.manifest,
              source_receipt: source.source_receipt,
              traffic_fence: finalFence,
              applications: [],
            });
          } catch {
            callbackResult = stopped("terminal_feed_fence_invalid");
            return callbackResult;
          }

          // A new receipt, even at the same coordinates, does not prove one
          // uninterrupted fence surrounded all application writes.
          const continuouslyHeldFence = sameFence(initialFence, finalFence) ? finalFence : null;
          let report: TombstoneReplayReport;
          try {
            report = verifyTombstoneRestoreReplay({
              restore,
              manifest: source.manifest,
              source_receipt: source.source_receipt,
              traffic_fence: continuouslyHeldFence,
              applications,
            });
          } catch {
            callbackResult = stopped("target_application_invalid");
            return callbackResult;
          }
          callbackResult = Object.freeze({ kind: "evaluated" as const, report });
          return callbackResult;
        },
      );
    } catch {
      return stopped("terminal_feed_fence_dependency_failed");
    } finally {
      callbackLeaseOpen = false;
    }
    // A fence adapter cannot manufacture or replay a callback result.
    if (callbackCount !== 1 || callbackResult === undefined || returned !== callbackResult) {
      return stopped("terminal_feed_fence_dependency_failed");
    }
    return returned;
  },
  });
};
