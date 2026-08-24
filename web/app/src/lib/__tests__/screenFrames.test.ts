import { describe, expect, it } from 'vitest';
import {
  BANNER_LIGHTBOX_INDEX,
  buildLightboxFrames,
  findFrameIndex,
  isFrameSetEmpty,
  resolveIndexAfterRemoval,
  stepFrameIndex,
  stripFrameLightboxIndex,
} from '@/lib/screenFrames';
import type {
  ConversationScreenFrame,
  ConversationScreenFrameSet,
} from '@/types/conversation';

function frame(id: string): ConversationScreenFrame {
  return {
    id,
    captured_at: '2026-08-24T10:00:00Z',
    role: 'strip',
    rank: 0,
    caption: `caption-${id}`,
    labels: [],
    source_badge: null,
    focal_region: null,
    width: 1600,
    height: 900,
    content_url: `https://example.com/${id}.jpg`,
    thumbnail_url: `https://example.com/${id}_thumb.jpg`,
    url_expires_at: '2026-08-24T11:00:00Z',
    ground: { stops: ['#101010', '#202020'], is_neutral: false },
  };
}

function frameSet(
  overrides: Partial<ConversationScreenFrameSet> = {},
): ConversationScreenFrameSet {
  return { revision: 1, banner: null, strip: [], ...overrides };
}

describe('stepFrameIndex', () => {
  it('steps forward within bounds', () => {
    expect(stepFrameIndex(0, 3, 1)).toBe(1);
  });

  it('steps backward within bounds', () => {
    expect(stepFrameIndex(1, 3, -1)).toBe(0);
  });

  it('wraps forward past the last index back to 0', () => {
    expect(stepFrameIndex(2, 3, 1)).toBe(0);
  });

  it('wraps backward past 0 to the last index', () => {
    expect(stepFrameIndex(0, 3, -1)).toBe(2);
  });

  it('returns 0 for an empty strip regardless of direction', () => {
    expect(stepFrameIndex(0, 0, 1)).toBe(0);
    expect(stepFrameIndex(0, 0, -1)).toBe(0);
  });

  it('is a no-op wraparound on a single-frame strip', () => {
    expect(stepFrameIndex(0, 1, 1)).toBe(0);
    expect(stepFrameIndex(0, 1, -1)).toBe(0);
  });
});

describe('resolveIndexAfterRemoval', () => {
  it('closes the lightbox (null) when the strip is now empty', () => {
    expect(resolveIndexAfterRemoval(0, 0)).toBeNull();
  });

  it('keeps the same index when a later frame was removed', () => {
    // Was showing index 0 of 3; a later frame was deleted, strip is now 2 long.
    expect(resolveIndexAfterRemoval(0, 2)).toBe(0);
  });

  it('clamps to the new last index when the deleted frame was last', () => {
    // Was showing index 2 (the last of 3); that frame was deleted, strip is now 2 long.
    expect(resolveIndexAfterRemoval(2, 2)).toBe(1);
  });
});

describe('findFrameIndex', () => {
  it('finds a frame by id', () => {
    const strip = [frame('a'), frame('b'), frame('c')];
    expect(findFrameIndex(strip, 'b')).toBe(1);
  });

  it('returns -1 when the id is not present', () => {
    const strip = [frame('a'), frame('b')];
    expect(findFrameIndex(strip, 'missing')).toBe(-1);
  });
});

describe('isFrameSetEmpty', () => {
  it('is true for null/undefined', () => {
    expect(isFrameSetEmpty(null)).toBe(true);
    expect(isFrameSetEmpty(undefined)).toBe(true);
  });

  it('is true when there is no banner and an empty strip', () => {
    expect(isFrameSetEmpty(frameSet())).toBe(true);
  });

  it('is false when there is a banner but an empty strip', () => {
    expect(isFrameSetEmpty(frameSet({ banner: frame('banner-1') }))).toBe(false);
  });

  it('is false when there is no banner but the strip has frames', () => {
    expect(isFrameSetEmpty(frameSet({ strip: [frame('a')] }))).toBe(false);
  });
});

describe('buildLightboxFrames', () => {
  it('returns an empty list for null/undefined', () => {
    expect(buildLightboxFrames(null)).toEqual([]);
    expect(buildLightboxFrames(undefined)).toEqual([]);
  });

  it('returns just the strip when there is no banner', () => {
    const strip = [frame('a'), frame('b')];
    expect(buildLightboxFrames(frameSet({ strip }))).toEqual(strip);
  });

  it('puts the banner first, then the strip in rank order', () => {
    const banner = frame('banner-1');
    const strip = [frame('a'), frame('b')];
    expect(buildLightboxFrames(frameSet({ banner, strip }))).toEqual([banner, ...strip]);
  });

  it('is just the banner when the strip is empty', () => {
    const banner = frame('banner-1');
    expect(buildLightboxFrames(frameSet({ banner }))).toEqual([banner]);
  });
});

describe('stripFrameLightboxIndex', () => {
  it('is unchanged when there is no banner', () => {
    expect(stripFrameLightboxIndex(frameSet({ strip: [frame('a')] }), 0)).toBe(0);
  });

  it('is offset by one when a banner occupies slot 0', () => {
    expect(stripFrameLightboxIndex(frameSet({ banner: frame('banner-1') }), 0)).toBe(1);
    expect(stripFrameLightboxIndex(frameSet({ banner: frame('banner-1') }), 2)).toBe(3);
  });

  it('treats a missing frame set as bannerless', () => {
    expect(stripFrameLightboxIndex(null, 1)).toBe(1);
    expect(stripFrameLightboxIndex(undefined, 1)).toBe(1);
  });
});

describe('BANNER_LIGHTBOX_INDEX', () => {
  it('is 0 — the banner always occupies the first lightbox slot', () => {
    expect(BANNER_LIGHTBOX_INDEX).toBe(0);
  });
});
