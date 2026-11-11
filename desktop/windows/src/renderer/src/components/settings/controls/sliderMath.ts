// Pure value <-> position math for the settings Slider primitive. Kept
// framework-free (no React, no DOM) so the snapping/clamping rules are unit
// testable in isolation — the component is a thin pointer/keyboard shell over
// these functions.

/** Clamp `value` into the inclusive [min, max] range. */
export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

/** Decimal places implied by `step` (0.05 -> 2, 1 -> 0). Used to kill the float
 *  drift that `min + steps * step` accumulates (e.g. 1.0500000000000003). */
function stepDecimals(step: number): number {
  if (!Number.isFinite(step) || step <= 0) return 0
  const s = String(step)
  const dot = s.indexOf('.')
  return dot < 0 ? 0 : s.length - dot - 1
}

/**
 * Snap `value` to the nearest `min + k*step` and clamp into [min, max]. The
 * result is rounded to the step's precision so it stays a clean multiple (no
 * 1.9500000000000002). `step <= 0` disables snapping (just clamps).
 */
export function snapToStep(value: number, min: number, max: number, step: number): number {
  const clamped = clamp(value, min, max)
  if (!Number.isFinite(step) || step <= 0) return clamped
  const steps = Math.round((clamped - min) / step)
  const snapped = min + steps * step
  const fixed = Number(snapped.toFixed(stepDecimals(step)))
  return clamp(fixed, min, max)
}

/** Position of `value` on the track as a 0..1 fraction (0 = min, 1 = max). */
export function valueToFraction(value: number, min: number, max: number): number {
  if (max <= min) return 0
  return clamp((value - min) / (max - min), 0, 1)
}

/** Inverse of {@link valueToFraction}: a 0..1 track fraction -> snapped value. */
export function fractionToValue(fraction: number, min: number, max: number, step: number): number {
  const raw = min + clamp(fraction, 0, 1) * (max - min)
  return snapToStep(raw, min, max, step)
}
