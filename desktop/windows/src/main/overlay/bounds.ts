/** Fixed window width in px. The renderer renders the panel at 70% scale
 *  (overlay.css `.overlay-zoom` lays out at 480px then zooms to 0.7), so the window
 *  is 0.7 × 480 ≈ 336px and the panel fills it edge-to-edge. Keep this == 480×zoom. */
export const OVERLAY_WIDTH = 336

/** Top edge sits this many px below the top of the work area — the overlay spawns
 *  at the top of the screen (just clear of the work-area edge / taskbar). */
export const TOP_MARGIN = 12

/** Window height never exceeds this fraction of the work area; past it the
 *  renderer's reply area scrolls internally. */
export const MAX_HEIGHT_FRACTION = 0.7

export type WorkArea = { x: number; y: number; width: number; height: number }
export type Bounds = { x: number; y: number; width: number; height: number }

/**
 * Compute the overlay window rect for a given display work area and the
 * renderer's current measured content height. Centered horizontally, anchored
 * near the top (TOP_MARGIN px down), height clamped to 70% of the work area, and
 * nudged up so it never runs off the bottom edge of the display.
 */
export function computeOverlayBounds(workArea: WorkArea, contentHeight: number): Bounds {
  const width = OVERLAY_WIDTH
  const x = Math.round(workArea.x + (workArea.width - width) / 2)

  const maxHeight = Math.round(workArea.height * MAX_HEIGHT_FRACTION)
  const height = Math.max(1, Math.min(Math.round(contentHeight), maxHeight))

  let y = Math.round(workArea.y + TOP_MARGIN)
  const bottomLimit = workArea.y + workArea.height
  if (y + height > bottomLimit) y = bottomLimit - height
  if (y < workArea.y) y = workArea.y

  return { x, y, width, height }
}
