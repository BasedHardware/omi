/**
 * Shared platform scoping for the PostHog-backed stats routes.
 *
 * Scopes:
 *   - "macos"  — desktop events (`$os_name = 'macOS'`).
 *   - "mobile" — the mobile apps (iOS / Android / iPadOS). Mobile has sent
 *     PostHog events since 2025-03 (iOS) / 2026-05 (Android) — it is fully
 *     instrumented for usage metrics, but does NOT emit `Sign In Completed`,
 *     so signup cohorts for non-macOS scopes anchor on first-seen-any-event.
 *   - "all"    — every Omi platform. No OS constraint (keeps Windows and any
 *     events missing `$os_name`), but excludes the `cfc_*` events of Context
 *     for Claude, a second product reporting into this PostHog project whose
 *     events carry no `$os` and would otherwise be counted as Omi users.
 */

export type PlatformScope = "all" | "macos" | "mobile";

export const MOBILE_OS_NAMES = ["iOS", "Android", "iPadOS"] as const;

export function parsePlatformScope(raw: string | null): PlatformScope {
  return raw === "macos" || raw === "mobile" ? raw : "all";
}

/**
 * SQL fragment (starting with `AND …`, or empty) restricting an events query
 * to the scope. `osColumn` exists because older routes filter on
 * `properties.$os` while newer ones use `properties.$os_name` — the values
 * are identical for macOS/iOS/Android/iPadOS.
 */
export function scopeFilterAnd(
  scope: PlatformScope,
  osColumn = "properties.$os_name",
): string {
  if (scope === "macos") return `AND ${osColumn} = 'macOS'`;
  if (scope === "mobile") {
    return `AND ${osColumn} IN (${MOBILE_OS_NAMES.map((os) => `'${os}'`).join(", ")})`;
  }
  return "AND NOT startsWith(event, 'cfc_')";
}
