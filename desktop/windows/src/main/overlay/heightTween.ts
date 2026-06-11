/** easeOutCubic — fast start, gentle settle, matching the macOS feel. */
function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3)
}

/**
 * Build an eased sequence of integer heights from `from` to `to` over `steps`
 * frames. The sequence excludes the starting height (we are already there) and
 * always lands exactly on `to`. Monotonic in whichever direction we're moving.
 */
export function tweenHeights(from: number, to: number, steps: number): number[] {
  if (from === to) return [to]
  if (steps <= 1) return [to]

  const out: number[] = []
  for (let i = 1; i <= steps; i++) {
    const t = easeOutCubic(i / steps)
    out.push(Math.round(from + (to - from) * t))
  }
  out[out.length - 1] = to
  return out
}
