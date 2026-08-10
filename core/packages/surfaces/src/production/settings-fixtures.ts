import { parseRecordId, type DeadLetter } from "@omi-core/contracts";
import type { QueuePhase } from "@omi-core/sync";
import type { RefreshPhase, StoreStatus } from "@omi-core/domain";
import { mergeSettingsPatch } from "./settings-merge.js";
import type {
  AppearanceSelection,
  EntitlementState,
  SettingsPatch,
  SettingsSnapshot,
} from "./settings-merge.js";
import type { ProductionSettingsStore } from "./ProductionSettingsStore.js";

export const SETTINGS_FIXED_NOW = Date.UTC(2026, 7, 7, 12, 0, 0);

export const SETTINGS_FIXTURE_STATES = [
  "signed-in",
  "signed-out",
  "loading",
  "entitlement-absent",
  "limit-reached",
  "unmetered",
  "upgrade-unavailable",
  "unavailable",
  "saving-failed",
] as const;
export type SettingsFixtureState = (typeof SETTINGS_FIXTURE_STATES)[number];

function queue(phase: QueuePhase) {
  return { phase, pendingCount: phase === "idle" ? 0 : 1 };
}

function baseEntitlement(overrides: Partial<EntitlementState> = {}): EntitlementState {
  return {
    planLabel: "Omi Plus",
    limitKey: "memories",
    used: 42,
    limit: 100,
    limitReached: false,
    upgradeAvailable: true,
    ...overrides,
  };
}

function signedInIdentity() {
  return { displayName: "Alex Rivera", email: "alex@example.com" };
}

function snapshotFor(state: SettingsFixtureState): SettingsSnapshot {
  const appearance: AppearanceSelection = "system";
  switch (state) {
    case "signed-out":
      return { identity: null, appearance, entitlement: null };
    case "loading":
      // Loading must not claim a signed-in or signed-out outcome yet.
      return { identity: null, appearance, entitlement: null };
    case "entitlement-absent":
      return {
        identity: signedInIdentity(),
        appearance,
        entitlement: null,
      };
    case "limit-reached":
      return {
        identity: signedInIdentity(),
        appearance: "dark",
        entitlement: baseEntitlement({ used: 100, limit: 100, limitReached: true, upgradeAvailable: true }),
      };
    case "unmetered":
      return {
        identity: signedInIdentity(),
        appearance: "light",
        entitlement: baseEntitlement({ used: 7, limit: null, limitReached: false }),
      };
    case "upgrade-unavailable":
      return {
        identity: signedInIdentity(),
        appearance: "default",
        entitlement: baseEntitlement({ used: 100, limit: 100, limitReached: true, upgradeAvailable: false }),
      };
    case "unavailable":
      // 503 blackout: the whole read is absent, including identity. Forced by the
      // served settings types when the entitlement source fails.
      return { identity: null, appearance, entitlement: null };
    case "saving-failed":
      return {
        identity: signedInIdentity(),
        appearance: "system",
        entitlement: baseEntitlement(),
      };
    default:
      return {
        identity: signedInIdentity(),
        appearance: "system",
        entitlement: baseEntitlement(),
      };
  }
}

function deadLetter(now: number): DeadLetter {
  const recordId = parseRecordId("fixture-settings");
  if (!recordId) throw new Error("fixture id is not a valid RecordId: fixture-settings");
  return {
    opId: "fixture-dead-settings-001",
    recordId: recordId.id,
    domain: "settings",
    summary: "Update appearance",
    failure: { kind: "permanent", reason: "validation", detail: "The settings change was rejected." },
    deadAt: now,
  };
}

export function fixtureSettingsStore(state: SettingsFixtureState, now = SETTINGS_FIXED_NOW): ProductionSettingsStore {
  let data = snapshotFor(state);
  const refreshPhase: RefreshPhase = state === "loading"
    ? "initial-loading"
    : state === "unavailable"
      ? "unavailable"
      : state === "saving-failed"
        ? "saved-but-refresh-failed"
        : "ready";
  const status: StoreStatus = {
    refresh: {
      phase: refreshPhase,
      hasSavedData: state !== "signed-out" && state !== "loading" && state !== "unavailable",
    },
    queue: queue("idle"),
  };
  let dead: DeadLetter[] = [];
  const listeners = new Set<() => void>();
  const notify = (): void => { listeners.forEach((listener) => listener()); };

  return {
    async snapshot() { return data; },
    status() { return status; },
    async deadLetters() { return dead; },
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    async refresh() {
      // Unavailable stays phase-driven like memories/tasks; retry notifies without
      // inventing a second error tone on top of the blackout presentation.
      notify();
    },
    async patch(patch: SettingsPatch) {
      if (state === "saving-failed") throw new Error("fixture patch failed");
      data = mergeSettingsPatch(data, patch);
      notify();
    },
    async signOut() {
      // Replay is 204 by contract — already-signed-out stays a quiet success.
      if (state === "saving-failed" && data.identity !== null) {
        throw new Error("fixture sign out failed");
      }
      data = { ...data, identity: null, entitlement: null };
      notify();
    },
    async discardDeadLetter(opId) {
      dead = dead.filter((letter) => letter.opId !== opId);
      notify();
    },
  };
}
