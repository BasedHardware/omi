import { describe, it, expect } from 'vitest';
import {
  buildTimelineDayGroups,
  conversationSignals,
  countTimelineItems,
  dayKeyOf,
  dayLabel,
  flattenTimelineItems,
  parseLocalDay,
} from '@/lib/conversationTimeline';
import type { Conversation } from '@/types/conversation';
import type { DailySummary } from '@/types/recap';

const NOW = new Date(2025, 0, 15, 12, 0, 0);

function conversation(id: string, startedAt: Date): Conversation {
  return {
    id,
    created_at: startedAt.toISOString(),
    started_at: startedAt.toISOString(),
    structured: { title: id, overview: '', emoji: '', category: 'other' },
  } as unknown as Conversation;
}

function recap(id: string, date: string): DailySummary {
  return {
    id,
    date,
    headline: id,
    day_emoji: '',
    overview: '',
    stats: {
      total_conversations: 0,
      total_duration_minutes: 0,
      action_items_count: 0,
    },
    highlights: [],
    action_items: [],
    unresolved_questions: [],
    decisions_made: [],
    knowledge_nuggets: [],
    locations: [],
    created_at: date,
  } as DailySummary;
}

describe('dayKeyOf / parseLocalDay', () => {
  it('keys a late-evening date to its local day, not the UTC day', () => {
    expect(dayKeyOf(new Date(2025, 0, 15, 23, 30))).toBe('2025-01-15');
  });

  it('round-trips a backend YYYY-MM-DD recap date through local time', () => {
    expect(dayKeyOf(parseLocalDay('2025-01-15'))).toBe('2025-01-15');
  });
});

describe('dayLabel', () => {
  it('names the current and previous day relatively', () => {
    expect(dayLabel(new Date(2025, 0, 15, 8, 0), NOW)).toBe('Today');
    expect(dayLabel(new Date(2025, 0, 14, 23, 0), NOW)).toBe('Yesterday');
  });

  it('falls back to a weekday date for older days', () => {
    expect(dayLabel(new Date(2025, 0, 13), NOW)).toBe('Mon, Jan 13');
  });
});

describe('conversationSignals', () => {
  it('counts distinct speakers across label and numeric id forms', () => {
    const subject = {
      id: 'c',
      created_at: NOW.toISOString(),
      started_at: NOW.toISOString(),
      structured: {
        title: 'Standup',
        overview: '  Planned the week.  ',
        category: 'business',
        action_items: [{ description: 'a' }, { description: 'b' }],
      },
      transcript_segments: [
        { speaker: 'SPEAKER_0', text: 'hi' },
        { speaker: 'SPEAKER_0', text: 'again' },
        { speaker: 'SPEAKER_1', text: 'yo' },
        { speaker: null, speaker_id: 4, text: 'hm' },
        { speaker: null, speaker_id: null, text: 'unattributed' },
      ],
    } as unknown as Conversation;

    expect(conversationSignals(subject)).toEqual({
      excerpt: 'Planned the week.',
      category: 'business',
      actionItemCount: 2,
      speakerCount: 3,
    });
  });

  it('drops the placeholder "other" category and tolerates a bare conversation', () => {
    const bare = {
      id: 'c',
      created_at: NOW.toISOString(),
      started_at: NOW.toISOString(),
      structured: { category: 'other' },
    } as unknown as Conversation;

    expect(conversationSignals(bare)).toEqual({
      excerpt: '',
      category: null,
      actionItemCount: 0,
      speakerCount: 0,
    });
  });
});

describe('buildTimelineDayGroups', () => {
  it('groups by local day, newest day first', () => {
    const groups = buildTimelineDayGroups({
      conversations: [
        conversation('older', new Date(2025, 0, 13, 9, 0)),
        conversation('newer', new Date(2025, 0, 15, 9, 0)),
      ],
      recaps: [],
      now: NOW,
    });

    expect(groups.map((g) => g.key)).toEqual(['2025-01-15', '2025-01-13']);
    expect(groups.map((g) => g.label)).toEqual(['Today', 'Mon, Jan 13']);
  });

  it('leads a day with its recap, then conversations newest first', () => {
    const groups = buildTimelineDayGroups({
      conversations: [
        conversation('morning', new Date(2025, 0, 15, 9, 0)),
        conversation('evening', new Date(2025, 0, 15, 20, 0)),
      ],
      recaps: [recap('recap-15', '2025-01-15')],
      now: NOW,
    });

    expect(groups).toHaveLength(1);
    expect(groups[0].items.map((item) => [item.kind, item.id])).toEqual([
      ['recap', 'recap-15'],
      ['conversation', 'evening'],
      ['conversation', 'morning'],
    ]);
  });

  it('opens a day group for a recap even with no conversations that day', () => {
    const groups = buildTimelineDayGroups({
      conversations: [conversation('a', new Date(2025, 0, 15, 9, 0))],
      recaps: [recap('recap-14', '2025-01-14')],
      now: NOW,
    });

    expect(groups.map((g) => g.key)).toEqual(['2025-01-15', '2025-01-14']);
    expect(groups[1].items).toHaveLength(1);
    expect(groups[1].items[0].kind).toBe('recap');
    expect(groups[1].label).toBe('Yesterday');
  });

  it('skips items with an unusable timestamp instead of producing a NaN group', () => {
    const broken = {
      id: 'broken',
      created_at: 'not-a-date',
      started_at: '',
      structured: { title: 'broken' },
    } as unknown as Conversation;

    const groups = buildTimelineDayGroups({
      conversations: [broken, conversation('ok', new Date(2025, 0, 15, 9, 0))],
      recaps: [recap('no-date', '')],
      now: NOW,
    });

    expect(groups).toHaveLength(1);
    expect(countTimelineItems(groups)).toBe(1);
  });

  it('returns no groups for empty input', () => {
    expect(buildTimelineDayGroups({ conversations: [], recaps: [], now: NOW })).toEqual(
      [],
    );
  });

  it('flattens back to one newest-first stream', () => {
    const groups = buildTimelineDayGroups({
      conversations: [
        conversation('older', new Date(2025, 0, 13, 9, 0)),
        conversation('newer', new Date(2025, 0, 15, 9, 0)),
      ],
      recaps: [recap('recap-15', '2025-01-15')],
      now: NOW,
    });

    expect(flattenTimelineItems(groups).map((item) => item.id)).toEqual([
      'recap-15',
      'newer',
      'older',
    ]);
  });
});
