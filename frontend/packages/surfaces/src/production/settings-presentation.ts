import type { RefreshPhase } from "@omi-core/domain";
import type { SettingsSnapshot } from "./settings-merge.js";

/**
 * Account panel kind. A cached identity is a known fact and must not disappear
 * behind "Loading" just because refresh has not finished. Signed-out is only
 * proven once a snapshot has landed with a null identity on a non-loading
 * phase — never as the missing-data fallback, and never during initial-loading.
 */
export type AccountPresentation = "loading" | "unavailable" | "signed-out" | "signed-in";

export function accountPresentation(
  phase: RefreshPhase,
  snapshot: SettingsSnapshot | null,
): AccountPresentation {
  if (snapshot?.identity) return "signed-in";
  if (phase === "unavailable") return "unavailable";
  if (snapshot === null || phase === "initial-loading") return "loading";
  return "signed-out";
}
