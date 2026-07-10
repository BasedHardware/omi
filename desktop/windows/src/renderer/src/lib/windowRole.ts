// One source of truth for "which window am I?" The overlay, insight-toast, and
// hidden capture windows all load the same renderer bundle at their own hash
// routes (set by main before routing), so window-singleton hosts (tray state,
// auth-change fan-out, startup perf marks) gate on the initial hash to run only
// in the main window.

/** Hash-route prefixes for the secondary (non-main) windows sharing this bundle. */
export const SECONDARY_HASHES = ['#/overlay', '#/insight-toast', '#/capture']

/** True in a secondary (overlay / insight-toast / capture) window. */
export function isSecondaryWindow(hash = window.location.hash): boolean {
  return SECONDARY_HASHES.some((h) => hash.startsWith(h))
}
