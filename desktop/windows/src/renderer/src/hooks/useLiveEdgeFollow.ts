import { useCallback, useLayoutEffect, useRef, type RefObject } from 'react'

// Within this many px of the bottom counts as "at the live edge".
const EDGE_PX = 8

/**
 * Pin a chat scroller to the live edge while the assistant streams, and let go the
 * moment the reader scrolls away from it.
 *
 * RevealMarkdown grows the streaming reply's text WITHOUT a history change, so
 * watching the message array alone lags the reveal by a chunk — this observes the
 * content box and re-pins on every size change.
 *
 * Releasing follow is the part that has to be right. Watching `wheel` alone (what
 * the three chat surfaces each did before) only catches the mouse wheel and the
 * trackpad: dragging the scrollbar thumb, PageUp/Home/arrow keys and touch drags
 * left `following` engaged, so the next streamed chunk yanked the reader straight
 * back to the bottom and they could not read earlier messages during generation
 * (#10505). So the release decision is made from the scroll POSITION instead:
 * any upward movement is reader intent, whatever moved the viewport.
 *
 * Direction — rather than LegacyHome's is-this-scroll-programmatic flag — is what
 * makes that safe under streaming. A pin only ever moves the viewport DOWN (to the
 * max), and growing content does not move `scrollTop` at all, so neither can be
 * mistaken for the reader scrolling up. A flag cleared on the next frame cannot
 * make that distinction while the reply grows every frame: it would be set almost
 * continuously and would swallow the very scrollbar drag this fixes.
 *
 * The `wheel` handler is kept for the one case position can't see yet: an upward
 * wheel while already AT the bottom releases before the browser applies the delta,
 * so the reader never sees a frame of yank.
 */
export function useLiveEdgeFollow(
  scrollRef: RefObject<HTMLElement | null>,
  contentRef: RefObject<HTMLElement | null>,
  opts: { enabled?: boolean; resetKey?: unknown } = {}
): { resumeFollow: () => void } {
  const { enabled = true, resetKey } = opts
  const followRef = useRef(true)
  // Last position we know about, so a scroll event can be read as up or down.
  const lastTopRef = useRef(0)

  // Re-engage following on demand — the reader's own send is an explicit ask to
  // be taken back to the live edge, wherever they had scrolled to.
  const resumeFollow = useCallback((): void => {
    followRef.current = true
    const el = scrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
    lastTopRef.current = el.scrollTop
  }, [scrollRef])

  useLayoutEffect(() => {
    if (!enabled) return
    const el = scrollRef.current
    const content = contentRef.current
    if (!el || !content) return

    lastTopRef.current = el.scrollTop
    const pin = (): void => {
      if (!followRef.current) return
      el.scrollTop = el.scrollHeight
      lastTopRef.current = el.scrollTop
    }
    pin()

    const ro = new ResizeObserver(pin)
    ro.observe(content)

    const onWheel = (e: WheelEvent): void => {
      if (e.deltaY < 0 && el.scrollHeight > el.clientHeight + EDGE_PX) followRef.current = false
    }
    const onScroll = (): void => {
      const top = el.scrollTop
      // >1px, so sub-pixel jitter on fractional-scale displays isn't a scroll up.
      const movedUp = top < lastTopRef.current - 1
      lastTopRef.current = top
      // At the edge always follows — including when the viewport lands there
      // because the thread SHRANK (a cleared or switched thread clamps scrollTop
      // down, which looks like an upward scroll but leaves us at the bottom).
      if (el.scrollHeight - top - el.clientHeight <= EDGE_PX) followRef.current = true
      else if (movedUp) followRef.current = false
    }
    el.addEventListener('wheel', onWheel, { passive: true })
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      ro.disconnect()
      el.removeEventListener('wheel', onWheel)
      el.removeEventListener('scroll', onScroll)
    }
  }, [scrollRef, contentRef, enabled, resetKey])

  return { resumeFollow }
}
