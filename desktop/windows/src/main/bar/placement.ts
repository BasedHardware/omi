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

/** The trigger strip: 1px tall, spanning the display's top edge. */
export function computeStripBounds(display: DisplayLike): Rect {
  const b = display.bounds
  return { x: b.x, y: b.y, width: b.width, height: 1 }
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
export function displayForPoint(displays: DisplayLike[], pt: { x: number; y: number }): DisplayLike {
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

/**
 * Fullscreen-foreground suppression decision. `rect` is the foreground window's
 * rect in PHYSICAL pixels (Win32 GetWindowRect); display bounds are DIPs, so
 * compare against bounds × scaleFactor with a small tolerance. The Windows
 * shell's own fullscreen-sized surfaces (desktop/wallpaper hosts) must NOT
 * suppress, nor should our own process.
 */
export function shouldSuppressStrips(
  fg: { rect: Rect | null; className: string | null; exePath: string | null },
  display: DisplayLike,
  selfExePath: string,
  tolerancePx = 2
): boolean {
  if (!fg.rect) return false
  const shellClasses = ['Progman', 'WorkerW', 'Shell_TrayWnd', 'Shell_SecondaryTrayWnd']
  if (fg.className && shellClasses.includes(fg.className)) return false
  if (fg.exePath && selfExePath && fg.exePath.toLowerCase() === selfExePath.toLowerCase()) {
    return false
  }
  const s = display.scaleFactor
  const b = display.bounds
  const px = { x: b.x * s, y: b.y * s, width: b.width * s, height: b.height * s }
  const r = fg.rect
  return (
    r.x <= px.x + tolerancePx &&
    r.y <= px.y + tolerancePx &&
    r.x + r.width >= px.x + px.width - tolerancePx &&
    r.y + r.height >= px.y + px.height - tolerancePx
  )
}
