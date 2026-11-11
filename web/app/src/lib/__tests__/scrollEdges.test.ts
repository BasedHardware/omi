import { describe, it, expect } from 'vitest';
import { scrollEdgesOf, shouldFollowLiveEdge } from '@/lib/scrollEdges';

describe('scrollEdgesOf', () => {
  it('reports both ends for content that does not fill the scroller', () => {
    // Nothing is hidden in either direction, so neither fade should show.
    expect(scrollEdgesOf({ scrollTop: 0, scrollHeight: 300, clientHeight: 800 })).toEqual(
      {
        atTop: true,
        atBottom: true,
      },
    );
  });

  it('reports the top only, at the top of a long transcript', () => {
    expect(
      scrollEdgesOf({ scrollTop: 0, scrollHeight: 2000, clientHeight: 800 }),
    ).toEqual({ atTop: true, atBottom: false });
  });

  it('reports the bottom only, scrolled to the end', () => {
    expect(
      scrollEdgesOf({ scrollTop: 1200, scrollHeight: 2000, clientHeight: 800 }),
    ).toEqual({ atTop: false, atBottom: true });
  });

  it('reports neither end in the middle, so both fades show', () => {
    expect(
      scrollEdgesOf({ scrollTop: 600, scrollHeight: 2000, clientHeight: 800 }),
    ).toEqual({ atTop: false, atBottom: false });
  });

  it('tolerates the sub-pixel offsets a fractional layout produces', () => {
    // A scroller one third of a pixel from each end is at that end; without the
    // slack the fades flicker on every wheel tick.
    expect(
      scrollEdgesOf({ scrollTop: 0.34, scrollHeight: 2000, clientHeight: 800 }),
    ).toMatchObject({ atTop: true });
    expect(
      scrollEdgesOf({ scrollTop: 1199.66, scrollHeight: 2000, clientHeight: 800 }),
    ).toMatchObject({ atBottom: true });
  });
});

describe('shouldFollowLiveEdge', () => {
  it('follows while the scroller is already at the live edge', () => {
    expect(shouldFollowLiveEdge({ pinnedToBottom: true })).toBe(true);
  });

  it('does not steal the viewport once the reader has left the live edge', () => {
    expect(shouldFollowLiveEdge({ pinnedToBottom: false })).toBe(false);
  });

  it('places a newly opened exchange even if the scroller is not at the bottom yet', () => {
    expect(shouldFollowLiveEdge({ pinnedToBottom: false, force: true })).toBe(true);
  });
});
