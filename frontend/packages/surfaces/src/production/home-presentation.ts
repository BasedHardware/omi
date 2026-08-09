import type { RefreshPhase, RefreshStatus } from "@omi-core/domain";

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

export function homePhaseNoticeKey(phase: RefreshPhase):
  | "lifecycle.loading"
  | "lifecycle.refreshing"
  | "lifecycle.savedFailed"
  | "lifecycle.unavailable"
  | null {
  switch (phase) {
    case "initial-loading": return "lifecycle.loading";
    case "refreshing": return "lifecycle.refreshing";
    case "saved-but-refresh-failed": return "lifecycle.savedFailed";
    case "unavailable": return "lifecycle.unavailable";
    default: return null;
  }
}

/** Distinguishes what Home must render for a combined refresh status + loaded rows. */
export function homeSurfacePresentation(status: RefreshStatus, rowCount: number): {
  phase: RefreshPhase;
  noticeKey: ReturnType<typeof homePhaseNoticeKey>;
  showsSavedRows: boolean;
  showsFailureIndication: boolean;
} {
  const noticeKey = homePhaseNoticeKey(status.phase);
  return {
    phase: status.phase,
    noticeKey,
    showsSavedRows: rowCount > 0,
    showsFailureIndication: status.phase === "saved-but-refresh-failed" || status.phase === "unavailable",
  };
}
