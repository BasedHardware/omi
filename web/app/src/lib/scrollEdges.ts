/**
 * Where a scroller is relative to its ends.
 *
 * Split out from the hook so the rule can be tested without a DOM: fades that
 * mark "there is more this way" have to be told when there isn't, and the
 * off-by-one at each end is exactly the part worth pinning down.
 */

export interface ScrollEdges {
  atTop: boolean;
  atBottom: boolean;
}

export interface ScrollMetrics {
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
}

/** Slack in pixels, so sub-pixel scroll offsets do not flicker the fades. */
export const SCROLL_EDGE_EPSILON = 4;

export function scrollEdgesOf({
  scrollTop,
  scrollHeight,
  clientHeight,
}: ScrollMetrics): ScrollEdges {
  return {
    atTop: scrollTop <= SCROLL_EDGE_EPSILON,
    atBottom: scrollTop + clientHeight >= scrollHeight - SCROLL_EDGE_EPSILON,
  };
}

/**
 * Whether a live transcript may move the scroller.
 *
 * `scrollIntoView` walks every overflow ancestor. On Home that ancestor is the
 * page scroller that also holds chat history, so following a stream while the
 * reader is in history snaps them back down. Follow only while they are already
 * at the live edge, or when they just opened this exchange.
 */
export function shouldFollowLiveEdge({
  pinnedToBottom,
  force,
}: {
  pinnedToBottom: boolean;
  force?: boolean;
}): boolean {
  return Boolean(force) || pinnedToBottom;
}

/** Closest ancestor that actually scrolls vertically, if there is one. */
export function nearestVerticalScroller(start: HTMLElement | null): HTMLElement | null {
  let node: HTMLElement | null = start;
  while (node) {
    const overflowY = window.getComputedStyle(node).overflowY;
    if (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay') {
      return node;
    }
    node = node.parentElement;
  }
  return null;
}
