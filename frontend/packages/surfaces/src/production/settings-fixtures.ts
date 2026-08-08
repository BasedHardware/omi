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

function snapshotFor(state: SettingsFixtureState): SettingsSnapshot {
  const appearance: AppearanceSelection = "system";
  switch (state) {
    case "signed-out":
      return { identity: null, appearance, entitlement: null };
    case "limit-reached":
      return {
        identity: { displayName: "Alex Rivera", email: "alex@example.com" },
        appearance: "dark",
        entitlement: baseEntitlement({ used: 100, limit: 100, limitReached: true, upgradeAvailable: true }),
      };
    case "unmetered":
      return {
        identity: { displayName: "Alex Rivera", email: "alex@example.com" },
        appearance: "light",
        entitlement: baseEntitlement({ used: 7, limit: null, limitReached: false }),
      };
    case "upgrade-unavailable":
      return {
        identity: { displayName: "Alex Rivera", email: "alex@example.com" },
        appearance: "default",
        entitlement: baseEntitlement({ used: 100, limit: 100, limitReached: true, upgradeAvailable: false }),
      };
    case "unavailable":
    case "saving-failed":
      return {
        identity: { displayName: "Alex Rivera", email: "alex@example.com" },
        appearance: "system",
        entitlement: baseEntitlement(),
      };
    default:
      return {
        identity: { displayName: "Alex Rivera", email: "alex@example.com" },
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
  const refreshPhase: RefreshPhase = state === "unavailable"
    ? "unavailable"
    : state === "saving-failed"
      ? "saved-but-refresh-failed"
      : "ready";
  const status: StoreStatus = {
    refresh: { phase: refreshPhase, hasSavedData: state !== "signed-out" },
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
      if (state === "unavailable") throw new Error("fixture refresh failed");
      notify();
    },
    async patch(patch: SettingsPatch) {
      if (state === "saving-failed") throw new Error("fixture patch failed");
      data = mergeSettingsPatch(data, patch);
      notify();
    },
    async signOut() {
      if (state === "saving-failed") throw new Error("fixture sign out failed");
      data = { ...data, identity: null, entitlement: null };
      notify();
    },
    async discardDeadLetter(opId) {
      dead = dead.filter((letter) => letter.opId !== opId);
      notify();
    },
  };
}
