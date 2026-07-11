// Pure placement math for the top-edge bar + its 1px trigger strips. All units
// are DIPs (Electron display coordinates). No Electron imports — unit-tested.

export type Rect = { x: number; y: number; width: number; height: number }
export type DisplayLike = { id: number; bounds: Rect; workArea: Rect; scaleFactor: number }

/** Bar window width (DIP). Fits the expanded ask panel (336) with margin for
 *  the collapsed pill's slide/genesis motion and the morph overshoot. */
export const BAR_WINDOW_WIDTH = 560

/** Hard cap on the bar window height (DIP); the work-area fraction below also
 *  applies. Content scrolls internally past this. */
export const BAR_WINDOW_MAX_HEIGHT = 640
export const BAR_MAX_HEIGHT_FRACTION = 0.7

/** Region that keeps a summoned (peek) bar open: the bar's visible
 *  top-center footprint (pill + aim margin, a little taller than the pill).
 *  Cursor ANYWHERE else — including other top-edge positions like the screen
 *  corners — must start the retract grace timer. (Live bug: hovering the
 *  top-left/right corners kept the bar open indefinitely because DOM
 *  mouseleave never fires once the cursor exits a forwarded-events window.) */
export const PEEK_FOOTPRINT_WIDTH = 320
export const PEEK_FOOTPRINT_HEIGHT = 72

export function isCursorInPeekFootprint(
  cursor: { x: number; y: number },
  display: DisplayLike
): boolean {
  const b = display.bounds
  const width = Math.min(PEEK_FOOTPRINT_WIDTH, b.width)
  const x0 = b.x + (b.width - width) / 2
  return (
    cursor.x >= x0 &&
    cursor.x <= x0 + width &&
    cursor.y >= b.y &&
    cursor.y <= b.y + PEEK_FOOTPRINT_HEIGHT
  )
}

/** The ACTUAL visible collapsed-pill rect (148×36, top-center) plus a small aim
 *  margin — the ONLY region that should ever eat clicks while the bar is peeked.
 *  Distinct from the (larger) peek footprint that merely keeps the bar open:
 *  the dead space between the pill and the footprint edge must stay click-through
 *  so a control right under the top-center band (e.g. a browser's new-tab "+")
 *  is still clickable. (Merge-blocker: the whole 560×… window ate clicks whenever
 *  the interactive flag stuck on, because DOM mouseleave never fires once the
 *  cursor exits a forwarded-events window.) */
export const PILL_HIT_WIDTH = 160
export const PILL_HIT_HEIGHT = 44

export function isCursorOverPill(cursor: { x: number; y: number }, display: DisplayLike): boolean {
  const b = display.bounds
  const width = Math.min(PILL_HIT_WIDTH, b.width)
  const x0 = b.x + (b.width - width) / 2
  return (
    cursor.x >= x0 && cursor.x <= x0 + width && cursor.y >= b.y && cursor.y <= b.y + PILL_HIT_HEIGHT
  )
}

/**
 * The bar window rect for a display: fixed size, horizontally centered, hugging
 * the physical top edge (bounds, not workArea — it floats above a top-docked
 * taskbar like the Mac notch hugs the notch). The window is intentionally
 * larger than the visible bar: reveal/expand/morph animate via CSS transforms
 * INSIDE this static window — bounds are never animated.
 */
export function computeBarBounds(display: DisplayLike): Rect {
  const b = display.bounds
  const width = Math.min(BAR_WINDOW_WIDTH, b.width)
  const height = Math.min(
    BAR_WINDOW_MAX_HEIGHT,
    Math.max(1, Math.round(display.workArea.height * BAR_MAX_HEIGHT_FRACTION))
  )
  const x = Math.round(b.x + (b.width - width) / 2)
  return { x, y: b.y, width, height }
}

/** The display whose bounds contain the point, else the nearest by center
 *  distance (mirrors screen.getDisplayNearestPoint for unit tests). */
export function displayForPoint(
  displays: DisplayLike[],
  pt: { x: number; y: number }
): DisplayLike {
  for (const d of displays) {
    const b = d.bounds
    if (pt.x >= b.x && pt.x < b.x + b.width && pt.y >= b.y && pt.y < b.y + b.height) return d
  }
  let best = displays[0]
  let bestDist = Infinity
  for (const d of displays) {
    const cx = d.bounds.x + d.bounds.width / 2
    const cy = d.bounds.y + d.bounds.height / 2
    const dist = (cx - pt.x) ** 2 + (cy - pt.y) ** 2
    if (dist < bestDist) {
      bestDist = dist
      best = d
    }
  }
  return best
}
