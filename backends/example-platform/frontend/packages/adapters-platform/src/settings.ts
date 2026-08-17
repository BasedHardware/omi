/** Platform client for the settled Settings identity/entitlement wire. */

import type {
  HttpClient,
  SettingsWireEnvelope,
} from "@omi-core/contracts";
import { parseSettingsWireEnvelope } from "@omi-core/contracts";

export const PLATFORM_SETTINGS_PATH = "/v1/settings";
export const PLATFORM_CURRENT_SESSION_PATH = "/v1/session/current";

export type PlatformSettingsReadOutcome =
  | { readonly kind: "snapshot"; readonly snapshot: SettingsWireEnvelope }
  | { readonly kind: "auth-invalid"; readonly status: 401 | 403 }
  | { readonly kind: "unavailable"; readonly status: number };

/**
 * Optional-auth read. Only the host-originated typed reason means signed-out;
 * a server 401 means a presented credential was rejected and stays unavailable.
 */
export async function fetchPlatformSettings(http: HttpClient): Promise<PlatformSettingsReadOutcome> {
  const response = await http.request("GET", PLATFORM_SETTINGS_PATH);
  if (response.transportFailureReason === "not-authenticated") {
    return { kind: "snapshot", snapshot: { identity: null, entitlement: null } };
  }
  if (response.status === 401 || response.status === 403) {
    return { kind: "auth-invalid", status: response.status };
  }
  if (response.status !== 200) return { kind: "unavailable", status: response.status };
  const snapshot = parseSettingsWireEnvelope(response.json);
  return snapshot === null
    ? { kind: "unavailable", status: response.status }
    : { kind: "snapshot", snapshot };
}

export type PlatformCurrentSessionDeleteOutcome =
  | { readonly ok: true }
  | { readonly ok: false; readonly status: number };

/** Exact bodyless current-session revocation. */
export async function deletePlatformCurrentSession(
  http: HttpClient,
): Promise<PlatformCurrentSessionDeleteOutcome> {
  const response = await http.request("DELETE", PLATFORM_CURRENT_SESSION_PATH);
  return response.status === 204 ? { ok: true } : { ok: false, status: response.status };
}
