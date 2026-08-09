import type { RefreshPhase, RefreshStatus } from "@omi-core/domain";
import type { RefreshPhaseNoticeKey } from "./lifecycle-presentation.js";

/**
 * Conservative worst-of across Home's two search projections.
 *
 * Home is a merged spine over memories + conversations. There is no ratified
 * multi-source rule, so prefer the reading that never tells the user
 * everything is fine when either source is not: any `unavailable` without
 * retained rows becomes surface `unavailable`; any failure while either side
 * still has saved rows becomes `saved-but-refresh-failed`.
 */
export function combineHomeRefreshStatuses(
  left: RefreshStatus,
  right: RefreshStatus,
): RefreshStatus {
  const hasSavedData = left.hasSavedData || right.hasSavedData;
  const phases = [left.phase, right.phase];
  if (phases.includes("unavailable")) {
    return hasSavedData
      ? { phase: "saved-but-refresh-failed", hasSavedData: true }
      : { phase: "unavailable", hasSavedData: false };
  }
  if (phases.includes("saved-but-refresh-failed")) {
    return { phase: "saved-but-refresh-failed", hasSavedData: true };
  }
  if (phases.includes("initial-loading")) {
    return { phase: "initial-loading", hasSavedData };
  }
  if (phases.includes("refreshing")) {
    return { phase: "refreshing", hasSavedData };
  }
  return { phase: "ready", hasSavedData };
}

/**
 * Distinguishes what Home must render for a combined refresh status + loaded rows.
 *
 * Notice keys come from `refreshPhaseNoticeKey` (lifecycle-presentation.ts) —
 * this module stays free of relative value imports so Node hermetic tests can
 * execute it directly (same discipline as chat-reconcile.ts).
 */
export function homeSurfacePresentation(
  status: RefreshStatus,
  rowCount: number,
  noticeKey: RefreshPhaseNoticeKey | null,
): {
  phase: RefreshPhase;
  noticeKey: RefreshPhaseNoticeKey | null;
  showsSavedRows: boolean;
  showsFailureIndication: boolean;
} {
  return {
    phase: status.phase,
    noticeKey,
    showsSavedRows: rowCount > 0,
    showsFailureIndication: status.phase === "saved-but-refresh-failed" || status.phase === "unavailable",
  };
}
