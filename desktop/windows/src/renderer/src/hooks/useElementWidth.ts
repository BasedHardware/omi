import { useEffect, useState, type RefObject } from 'react'
import { keepLastPositive } from '../lib/measure'

/**
 * Track an element's content width via ResizeObserver. Needed because reading
 * `ref.current.clientWidth` during render is 0/stale on first paint — without a
 * state-backed measurement the timeline lays out wrong until something else
 * forces a re-render (e.g. a click).
 */
export function useElementWidth<T extends HTMLElement>(ref: RefObject<T | null>): number {
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      // Ignore 0-width reads via keepLastPositive: a hidden ancestor (e.g. a
      // display:none page panel the user navigated away from) makes the observer
      // report width 0. Writing that would clobber the cached width and, on
      // return, force a layout snap (the timeline briefly falls back to its
      // default width). Keep the last real measurement so re-shown panels paint
      // at the correct width up front.
      const w = entries[0]?.contentRect.width
      setWidth((prev) => keepLastPositive(prev, w))
    })
    ro.observe(el)
    setWidth((prev) => keepLastPositive(prev, el.clientWidth))
    return () => ro.disconnect()
  }, [ref])
  return width
}
