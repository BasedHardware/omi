/**
 * Settings domain and wire contract.
 *
 * The service owns identity + entitlement as one coherent optional-auth read.
 * Appearance is deliberately absent from that envelope: it is a device-local
 * preference injected by the shell and is not account-scoped server state.
 */

export type SettingsAppearanceSelection = "default" | "system" | "light" | "dark";

export interface SettingsIdentity {
  readonly displayName: string;
  readonly email: string;
}

export interface SettingsEntitlement {
  readonly planLabel: string;
  readonly limitKey: string;
  readonly used: number;
  /** null is the authoritative unmetered state. */
  readonly limit: number | null;
  readonly limitReached: boolean;
  readonly upgradeAvailable: boolean;
}

/** No credential was presented. Entitlement absence is mandatory here. */
export interface SettingsSignedOutWireEnvelope {
  readonly identity: null;
  readonly entitlement: null;
}

/** A presented, accepted credential selected one account coherently. */
export interface SettingsSignedInWireEnvelope {
  readonly identity: SettingsIdentity;
  readonly entitlement: SettingsEntitlement | null;
}

/** Exact success body of GET /v1/settings. */
export type SettingsWireEnvelope =
  | SettingsSignedOutWireEnvelope
  | SettingsSignedInWireEnvelope;

export type SettingsSnapshot =
  | (SettingsSignedOutWireEnvelope & { readonly appearance: SettingsAppearanceSelection })
  | (SettingsSignedInWireEnvelope & { readonly appearance: SettingsAppearanceSelection });

/** Keyed patch. Appearance is the only current local setting. */
export interface SettingsPatch {
  readonly appearance?: SettingsAppearanceSelection;
}

/**
 * Host/device preference seam. `null` means this device has no saved choice;
 * implementations never read account state and never call the service.
 */
export interface SettingsAppearancePreference {
  readAppearance(): Promise<SettingsAppearanceSelection | null>;
  writeAppearance(value: SettingsAppearanceSelection): Promise<void>;
}

export function isSettingsAppearanceSelection(value: unknown): value is SettingsAppearanceSelection {
  return value === "default" || value === "system" || value === "light" || value === "dark";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const keys = Object.keys(value);
  return keys.length === expected.length && expected.every((key) => Object.hasOwn(value, key));
}

function parseIdentity(value: unknown): SettingsIdentity | null {
  if (!isRecord(value) || !hasExactKeys(value, ["displayName", "email"])) return null;
  if (typeof value["displayName"] !== "string" || typeof value["email"] !== "string") return null;
  return { displayName: value["displayName"], email: value["email"] };
}

function isNonNegativeFinite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function parseEntitlement(value: unknown): SettingsEntitlement | null {
  if (!isRecord(value) || !hasExactKeys(value, [
    "planLabel",
    "limitKey",
    "used",
    "limit",
    "limitReached",
    "upgradeAvailable",
  ])) return null;
  const limit = value["limit"];
  if (
    typeof value["planLabel"] !== "string"
    || typeof value["limitKey"] !== "string"
    || !isNonNegativeFinite(value["used"])
    || !(limit === null || isNonNegativeFinite(limit))
    || typeof value["limitReached"] !== "boolean"
    || typeof value["upgradeAvailable"] !== "boolean"
    || (limit === null && value["limitReached"])
  ) return null;
  return {
    planLabel: value["planLabel"],
    limitKey: value["limitKey"],
    used: value["used"],
    limit,
    limitReached: value["limitReached"],
    upgradeAvailable: value["upgradeAvailable"],
  };
}

/**
 * Strict object boundary for the exact Settings success envelope.
 *
 * Missing/extra fields, arrays, malformed values, non-finite/negative usage,
 * signed-out-with-entitlement, and unmetered-but-reached all fail closed. Empty
 * identity strings and nulls are returned exactly as supplied; nothing is
 * repaired or defaulted at this service boundary.
 */
export function parseSettingsWireEnvelope(value: unknown): SettingsWireEnvelope | null {
  if (!isRecord(value) || !hasExactKeys(value, ["identity", "entitlement"])) return null;
  if (value["identity"] === null) {
    return value["entitlement"] === null ? { identity: null, entitlement: null } : null;
  }
  const identity = parseIdentity(value["identity"]);
  if (identity === null) return null;
  if (value["entitlement"] === null) return { identity, entitlement: null };
  const entitlement = parseEntitlement(value["entitlement"]);
  return entitlement === null ? null : { identity, entitlement };
}
