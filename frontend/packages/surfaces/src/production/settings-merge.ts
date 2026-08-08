export type AppearanceSelection = "default" | "system" | "light" | "dark";

/** null means "not signed in". Absent fields are absent, not empty strings. */
export type AccountIdentity = {
  readonly displayName: string;
  readonly email: string;
} | null;

/** One structured server payload. The client renders it; it does not derive plan logic. */
export type EntitlementState = {
  readonly planLabel: string;
  readonly limitKey: string;
  readonly used: number;
  /** null = unmetered. */
  readonly limit: number | null;
  readonly limitReached: boolean;
  readonly upgradeAvailable: boolean;
};

export type SettingsSnapshot = {
  readonly identity: AccountIdentity;
  readonly appearance: AppearanceSelection;
  readonly entitlement: EntitlementState | null;
};

/** Keyed patch. An absent key means UNCHANGED. There is no full-overwrite write. */
export type SettingsPatch = {
  readonly appearance?: AppearanceSelection;
};

/**
 * Merge a keyed settings patch into the current snapshot.
 * Explicit `undefined` values are ignored — only valid `AppearanceSelection`
 * literals apply; `Object.hasOwn` alone is not enough to overwrite with undefined.
 */
export function mergeSettingsPatch(current: SettingsSnapshot, patch: SettingsPatch): SettingsSnapshot {
  const appearance = Object.hasOwn(patch, "appearance") && patch.appearance !== undefined
    ? patch.appearance
    : current.appearance;
  return {
    identity: current.identity,
    appearance,
    entitlement: current.entitlement,
  };
}

export function entitlementNotice(
  entitlement: EntitlementState | null,
  canRoute: boolean,
): { show: boolean; upgrade: "route" | "unavailable" | "none"; usageKind: "metered" | "unmetered" | "none" } {
  if (!entitlement) {
    return { show: false, upgrade: "none", usageKind: "none" };
  }
  const usageKind = entitlement.limit === null ? "unmetered" : "metered";
  if (!entitlement.limitReached) {
    return { show: false, upgrade: "none", usageKind };
  }
  if (entitlement.upgradeAvailable && canRoute) {
    return { show: true, upgrade: "route", usageKind };
  }
  return { show: true, upgrade: "unavailable", usageKind };
}

/** Returns label args for settings.usageOf / settings.usageUnmetered, or null when nothing honest to show. */
export function usageLabelArgs(
  entitlement: EntitlementState | null,
): { used: number; limit?: number } | null {
  if (!entitlement) return null;
  if (entitlement.limit === null) {
    return { used: entitlement.used };
  }
  return { used: entitlement.used, limit: entitlement.limit };
}
