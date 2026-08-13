import { describe, expect, it } from 'vitest';

import {
  applyLiveTranscriptSegment,
  DEFAULT_MAX_LIVE_SEGMENTS,
  trimTranscriptSegments,
  upsertTranscriptSegment,
} from './transcriptSegments';

function seg(id: string, text = id): { id: string; text: string; speaker: number; isUser: boolean; timestamp: number } {
  return { id, text, speaker: 0, isUser: false, timestamp: 0 };
}

describe('upsertTranscriptSegment (#5399)', () => {
  it('appends a new segment', () => {
    const next = upsertTranscriptSegment([seg('a')], seg('b', 'hello'));
    expect(next.map((s) => s.id)).toEqual(['a', 'b']);
    expect(next[1].text).toBe('hello');
  });

  it('updates an existing segment in place', () => {
    const next = upsertTranscriptSegment([seg('a', 'old'), seg('b')], seg('a', 'new'));
    expect(next).toHaveLength(2);
    expect(next[0].text).toBe('new');
    expect(next[1].id).toBe('b');
  });

  it('keeps length 1 across many partial updates of the same id', () => {
    let segments = [seg('only', 'v0')];
    for (let i = 1; i <= 1000; i++) {
      segments = upsertTranscriptSegment(segments, seg('only', `v${i}`));
    }
    expect(segments).toHaveLength(1);
    expect(segments[0].text).toBe('v1000');
  });
});

describe('trimTranscriptSegments (#5399)', () => {
  it('keeps the most recent N segments', () => {
    const segments = [seg('1'), seg('2'), seg('3'), seg('4'), seg('5')];
    expect(trimTranscriptSegments(segments, 3).map((s) => s.id)).toEqual(['3', '4', '5']);
  });

  it('returns the same reference when under budget', () => {
    const segments = [seg('1'), seg('2')];
    expect(trimTranscriptSegments(segments, 10)).toBe(segments);
  });

  it('preserves an older in-flight segment when trimming', () => {
    const segments = [seg('old'), seg('2'), seg('3'), seg('4')];
    const trimmed = trimTranscriptSegments(segments, 2, 'old');
    expect(trimmed.map((s) => s.id)).toEqual(['old', '4']);
  });
});

describe('applyLiveTranscriptSegment (#5399)', () => {
  it('upserts then trims to the default budget', () => {
    expect(DEFAULT_MAX_LIVE_SEGMENTS).toBe(400);
    let segments: ReturnType<typeof seg>[] = [];
    for (let i = 0; i < 450; i++) {
      segments = applyLiveTranscriptSegment(segments, seg(`s${i}`));
    }
    expect(segments).toHaveLength(DEFAULT_MAX_LIVE_SEGMENTS);
    expect(segments[0].id).toBe('s50');
    expect(segments[segments.length - 1].id).toBe('s449');
  });

  it('does not drop the segment currently being updated', () => {
    const early = Array.from({ length: 5 }, (_, i) => seg(`s${i}`));
    const next = applyLiveTranscriptSegment(early, seg('s0', 'refined'), 3);
    expect(next.some((s) => s.id === 's0' && s.text === 'refined')).toBe(true);
    expect(next).toHaveLength(3);
  });
});
