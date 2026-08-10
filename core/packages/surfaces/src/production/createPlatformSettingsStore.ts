import type {
  HttpClient,
  SettingsAppearancePreference,
} from "@omi-core/contracts";
import { PlatformSettingsStore } from "@omi-core/domain";
import type { ProductionSettingsStore } from "./ProductionSettingsStore.js";

/** Bind host-owned privileged HTTP + device preference to the Settings port. */
export function createPlatformProductionSettingsStore(
  http: HttpClient,
  preference: SettingsAppearancePreference,
): Promise<ProductionSettingsStore> {
  return PlatformSettingsStore.open(http, preference);
}
