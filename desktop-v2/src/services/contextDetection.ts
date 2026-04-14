/**
 * Context detection — detects app/window context changes.
 *
 * Ported from the Swift app's ContextDetection.swift.
 * Normalizes window titles to strip noise (spinners, timers, counts)
 * so that trivial title changes don't trigger re-analysis.
 */

// ---------------------------------------------------------------------------
// Window title normalization
// ---------------------------------------------------------------------------

/**
 * Normalize a window title by stripping noise that changes frequently
 * but doesn't represent a meaningful context switch.
 */
export function normalizeWindowTitle(title: string): string {
  let normalized = title;

  // Strip Braille spinner characters (U+2800-U+28FF)
  normalized = normalized.replace(/[\u2800-\u28FF]/g, "");

  // Strip common progress spinners
  normalized = normalized.replace(/[✳↻◐◑◒◓⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]/g, "");

  // Strip timer patterns like "12:34" or "1:23:45"
  normalized = normalized.replace(/\b\d{1,2}:\d{2}(:\d{2})?\b/g, "");

  // Strip terminal dimensions like "80×24"
  normalized = normalized.replace(/\b\d+[×x]\d+\b/g, "");

  // Strip parenthetical/bracket counts like "(2)" or "[3]"
  normalized = normalized.replace(/[(\[]\d+[)\]]/g, "");

  // Collapse whitespace
  normalized = normalized.replace(/\s+/g, " ").trim();

  return normalized;
}

// ---------------------------------------------------------------------------
// Context state
// ---------------------------------------------------------------------------

let lastApp = "";
let lastNormalizedTitle = "";

/**
 * Check if the context (app + normalized window title) has changed
 * since the last call.
 *
 * Returns true on the first call, and on every subsequent change.
 * Does NOT update the tracked state — call `updateContext()` for that.
 */
export function didContextChange(appName: string, windowTitle: string): boolean {
  const normalizedTitle = normalizeWindowTitle(windowTitle);

  if (lastApp === "" && lastNormalizedTitle === "") {
    // First call — always counts as a change
    return true;
  }

  return appName !== lastApp || normalizedTitle !== lastNormalizedTitle;
}

/**
 * Update the tracked context to the given app/title.
 * Call this after successfully distributing a frame.
 */
export function updateContext(appName: string, windowTitle: string): void {
  lastApp = appName;
  lastNormalizedTitle = normalizeWindowTitle(windowTitle);
}

/**
 * Get the current tracked context.
 */
export function getCurrentContext(): { app: string; title: string } {
  return { app: lastApp, title: lastNormalizedTitle };
}

/**
 * Reset the tracked context (e.g. when stopping monitoring).
 */
export function resetContext(): void {
  lastApp = "";
  lastNormalizedTitle = "";
}
