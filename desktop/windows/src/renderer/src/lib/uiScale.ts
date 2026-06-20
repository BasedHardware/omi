// Global UI scale: one knob that grows/shrinks the whole app and the floating
// bar. The MAIN window applies it via CSS `zoom` on the document root, which
// scales EVERYTHING uniformly — rem-based text, padding, AND the ~30 hardcoded
// `text-[Npx]` literals (a root `font-size` change would leave those fixed). The
// floating-bar window scales itself separately (see OverlayApp), because its
// window width is fixed in main and its height is measured from the DOM.

// Discrete scale levels shared by the App and Floating-bar size sliders. Symmetric
// around 1 so 100% (the default) is the CENTER stop: two smaller, two larger.
export const UI_SCALE_LEVELS = [0.8, 0.9, 1, 1.1, 1.2]

export const DEFAULT_UI_SCALE = 1

/** Format a scale as a whole-percent string, e.g. 1.25 → "125%". */
export function scalePercent(scale: number): string {
  return `${Math.round(scale * 100)}%`
}

/** Clamp to the supported range so a stale/garbage stored value can't zoom the UI
 *  into uselessness. */
export function clampUiScale(scale: number): number {
  if (!Number.isFinite(scale)) return DEFAULT_UI_SCALE
  return Math.min(1.6, Math.max(0.8, scale))
}

/** Apply the scale to the MAIN app window by CSS-zooming the document root. */
export function applyAppScale(scale: number): void {
  // `zoom` isn't in the standard CSSStyleDeclaration type but is supported in
  // Chromium (and is exactly how the floating bar already scales itself).
  const style = document.documentElement.style as CSSStyleDeclaration & { zoom?: string }
  style.zoom = String(clampUiScale(scale))
}
