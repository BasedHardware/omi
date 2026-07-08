import { useEffect, useState, type RefObject } from 'react'

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
      const w = entries[0]?.contentRect.width
      if (typeof w === 'number') setWidth(w)
    })
    ro.observe(el)
    setWidth(el.clientWidth)
    return () => ro.disconnect()
  }, [ref])
  return width
}
