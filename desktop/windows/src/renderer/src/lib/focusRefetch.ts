import { useEffect, useRef } from 'react'

// Window-focus revalidation, throttled.
//
// Three always-mounted surfaces refetch on window focus: the Memories page (a full
// `/v3/memories` page-through), the Apps page (three requests), and the Home goals
// chips (one). `components/layout/MainViews.tsx` mounts every panel 1.8s after launch
// and never unmounts them, so all three listeners are live no matter which tab the
// user is on — one focus event costs six-plus backend requests for surfaces that are
// not on screen.
//
// The trigger is not rare. It is any alt-tab back into the main window, and the app
// blurs its own main window every time the floating bar, the orb, or the capture
// window takes focus — so ordinary voice use pays this repeatedly per minute.
//
// Revalidating on focus is still the right behavior; doing it on EVERY focus is not.
// A minimum interval keeps the freshness guarantee (a user coming back to a surface
// after real time away gets fresh data) and drops the burst (flicking between windows
// costs nothing after the first).
export const FOCUS_REFETCH_MIN_INTERVAL_MS = 60_000

/**
 * Run `handler` on window focus, at most once per `minIntervalMs`.
 *
 * The FIRST focus of a session always runs: these surfaces revalidate on focus so a
 * change made in another window shows up, and deferring that would be a visible
 * behavior change rather than a cost fix. Only the repeats are dropped, which is where
 * the waste actually is.
 *
 * Call sites pass a fresh closure each render (they all close over `loading`/`refresh`),
 * so the listener is re-subscribed on re-render exactly as it was before. The throttle
 * clock lives in a ref, so re-subscribing does not reopen the window.
 */
export function useThrottledWindowFocus(
  handler: () => void,
  minIntervalMs: number = FOCUS_REFETCH_MIN_INTERVAL_MS
): void {
  // When the handler last ran (0 = never, so the first focus is never throttled).
  const lastRunAtRef = useRef(0)

  useEffect(() => {
    const onFocus = (): void => {
      const now = Date.now()
      if (now - lastRunAtRef.current < minIntervalMs) return
      lastRunAtRef.current = now
      handler()
    }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [handler, minIntervalMs])
}
