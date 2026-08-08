import type { DeadLetter } from "@omi-core/contracts";
import type { StoreStatus } from "@omi-core/domain";
import type {
  AccountIdentity,
  AppearanceSelection,
  EntitlementState,
  SettingsPatch,
  SettingsSnapshot,
} from "./settings-merge.js";

export type {
  AccountIdentity,
  AppearanceSelection,
  EntitlementState,
  SettingsPatch,
  SettingsSnapshot,
};

/**
 * Composition boundary the platform settings slice will implement.
 * Fixtures and the legacy adapter satisfy the same surface-facing port;
 * a rewritten backend can provide another factory without changing product
 * components or their offline/status behavior.
 */
export type ProductionSettingsStore = {
  snapshot(): Promise<SettingsSnapshot>;
  patch(patch: SettingsPatch): Promise<void>;
  signOut(): Promise<void>;
  status(): StoreStatus;
  subscribe(listener: () => void): () => void;
  refresh(): Promise<void>;
  deadLetters(): Promise<DeadLetter[]>;
  discardDeadLetter(opId: string): Promise<void>;
};
