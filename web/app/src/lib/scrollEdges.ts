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
