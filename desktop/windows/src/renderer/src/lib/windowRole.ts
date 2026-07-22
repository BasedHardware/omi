// One source of truth for "which window am I?" The bar loads this same renderer
// bundle (index.html) at its own hash route (set by main before routing), so
// window-singleton hosts (tray state, auth-change fan-out, startup perf marks)
// gate on the initial hash to run only in the main window. The glow,
// insight-toast, and capture windows now load their own slim HTML entries
// (perf/win-slim-aux-windows) but keep the same `#/<route>` hash, so this check
// stays correct for any code path they still reach.

/** Hash-route prefixes for the secondary (non-main) windows sharing this bundle. */
export const SECONDARY_HASHES = ['#/bar', '#/insight-toast', '#/capture', '#/glow']

/** True in a secondary (bar / insight-toast / capture / glow) window. */
export function isSecondaryWindow(hash = window.location.hash): boolean {
  return SECONDARY_HASHES.some((h) => hash.startsWith(h))
}
