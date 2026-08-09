import type { RefreshPhase } from "@omi-core/domain";
import type { MessageKey } from "@omi-core/i18n";

/** Compile-time proof that a narrow key union really exists in the catalog. */
type CatalogKey<T extends MessageKey> = T;

/**
 * Catalog keys a refresh-phase notice may render. Narrow rather than bare
 * `MessageKey` so call sites can pass a computed key to `t()` / `translate()`
 * without widening into placeholder-message overloads.
 */
export type RefreshPhaseNoticeKey = CatalogKey<
  | "lifecycle.loading"
  | "lifecycle.refreshing"
  | "lifecycle.savedFailed"
  | "lifecycle.unavailable"
>;

/**
 * Single RefreshPhase → catalog-key map for every production surface.
 *
 * Exhaustive: `ready` is the only phase with no notice (`null`). Any new
 * `RefreshPhase` member falls through to `never` and fails `tsc` until copy
 * is chosen here — the previous per-surface `default: return null` would
 * silently render nothing.
 */
export function refreshPhaseNoticeKey(phase: RefreshPhase): RefreshPhaseNoticeKey | null {
  switch (phase) {
    case "initial-loading":
      return "lifecycle.loading";
    case "refreshing":
      return "lifecycle.refreshing";
    case "saved-but-refresh-failed":
      return "lifecycle.savedFailed";
    case "unavailable":
      return "lifecycle.unavailable";
    case "ready":
      return null;
    default: {
      const _exhaustive: never = phase;
      throw new Error(`unhandled refresh phase: ${JSON.stringify(_exhaustive)}`);
    }
  }
}
