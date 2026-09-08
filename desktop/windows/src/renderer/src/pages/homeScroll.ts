// Pure helpers for the Home chat scroller, kept free of React/DOM so they can be
// unit-tested under node Vitest (the effectful scroll wiring lives in Home.tsx).

// The thread's top fade mask is shown only once the scroller actually overflows.
// Computing that with a single threshold makes it flicker while the open animation
// resizes the scroller back and forth across the boundary. Hysteresis fixes it:
// require a CLEAR overflow to switch the mask ON, and a clear NON-overflow to switch
// it OFF, so small oscillations around the threshold can't flip it.
const OVERFLOW_ON_PX = 24
const OVERFLOW_OFF_PX = 4

/**
 * Next value for the "thread overflows" flag, with hysteresis. `prev` is the
 * current flag; `overshoot` is `scrollHeight - clientHeight`. Once on, it stays on
 * until the content clearly fits again; once off, it needs a clear overflow to turn
 * on — so geometry jitter during the entrance animation doesn't toggle the mask.
 */
export function nextOverflowing(
  prev: boolean,
  scrollHeight: number,
  clientHeight: number
): boolean {
  const overshoot = scrollHeight - clientHeight
  return prev ? overshoot > OVERFLOW_OFF_PX : overshoot > OVERFLOW_ON_PX
}
