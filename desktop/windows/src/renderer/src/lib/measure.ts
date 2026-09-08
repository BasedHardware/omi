/**
 * Guard for ResizeObserver-driven size measurements.
 *
 * Pages in the shell are kept mounted and toggled with `display:none` when the
 * user navigates away (see MainViews' panelClass). A `display:none` ancestor
 * makes a ResizeObserver fire a 0×0 rect, and `offsetHeight`/`clientWidth` read
 * as 0. If that 0 is written into the cached measurement, the next time the page
 * is shown React paints with the stale 0 and then snaps to the real size a frame
 * later — an intermittent layout glitch (collapsed cards, timeline width jump).
 *
 * Accept the newly measured size only when it is a positive number; otherwise
 * keep the last real measurement so a re-shown panel renders correctly up front.
 */
export function keepLastPositive(previous: number, measured: number | undefined | null): number {
  return typeof measured === 'number' && measured > 0 ? measured : previous
}
