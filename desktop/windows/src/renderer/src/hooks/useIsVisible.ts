import { useEffect, useState } from 'react'

// True while the referenced element is actually displayed. Backed by an
// IntersectionObserver, so it flips ONLY when that element shows/hides — not on
// unrelated navigations (unlike a route compare, which would re-render a
// mounted-hidden panel on every tab switch and defeat the manifest's panel memo).
//
// This is the signal the mounted-hidden panel grid (layout/MainViews.tsx) needs
// to pause background work: every panel stays mounted (display:none when
// inactive), so a hook has no other way to know its own panel is off-screen. A
// `display:none` ancestor gives the target no box, which the observer reports as
// not-intersecting; showing it fires an intersecting notification. Starts false
// and is corrected on the observer's first (async, next-frame) callback, so a
// hidden panel never does a frame of visible-only work before pausing.
//
// Fail-open: where IntersectionObserver is unavailable (jsdom/SSR) it returns
// true, so gated work runs rather than being silently suppressed.
export function useIsVisible(ref: React.RefObject<Element | null>): boolean {
  // Starts hidden where an observer exists (a mounted-hidden panel is off-screen
  // until shown); starts visible where IntersectionObserver is unavailable
  // (jsdom/SSR) so gated work fails open. Initializing here — rather than
  // setState-ing the fallback in the effect — keeps the effect free of a
  // synchronous cascading render.
  const [visible, setVisible] = useState(() => typeof IntersectionObserver === 'undefined')
  useEffect(() => {
    // Observes ref.current as it is at mount (refs are attached before effects run,
    // so it is non-null here for a rendered element). Keyed on the ref OBJECT, whose
    // identity is stable, so it does NOT re-observe if the underlying element is
    // later swapped — fine for a stable page root, which is the only intended use.
    const el = ref.current
    if (!el || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver((entries) => {
      setVisible(entries.some((e) => e.isIntersecting))
    })
    io.observe(el)
    return () => io.disconnect()
  }, [ref])
  return visible
}
