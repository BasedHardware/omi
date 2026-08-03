import { describe, expect, it, vi } from 'vitest';
import { deleteAndRethread } from '@/lib/chatSessionDelete';
import { filterSessions, groupSessionsByDate, toEpochMs } from '@/lib/chatSessionsView';
import type { ChatSession } from '@/types/chatSessions';

/**
 * Locks the behaviour ported from the Electron desktop app
 * (`lib/chatSessionsView.ts`, `components/chat/chatSessionDelete.ts`), which
 * itself ports macOS `ChatProvider.computeGroupedSessions()`. The buckets and
 * their order must match across clients.
 */

function session(overrides: Partial<ChatSession> = {}): ChatSession {
  return {
    id: 'sess-1',
    title: 'A chat',
    createdAt: '2026-08-01T00:00:00Z',
    updatedAt: '2026-08-01T00:00:00Z',
    messageCount: 2,
    starred: false,
    ...overrides,
  };
}

describe('toEpochMs', () => {
  it('accepts epoch numbers and ISO strings', () => {
    expect(toEpochMs(1000)).toBe(1000);
    expect(toEpochMs('2026-08-01T00:00:00Z')).toBe(Date.parse('2026-08-01T00:00:00Z'));
  });

  it('returns 0 for unparseable input so a bad row sorts last, never NaN', () => {
    expect(toEpochMs('not a date')).toBe(0);
    expect(toEpochMs(undefined)).toBe(0);
    expect(toEpochMs(Number.NaN)).toBe(0);
  });
});

describe('filterSessions', () => {
  const sessions = [
    session({ id: 'a', title: 'Trip planning', preview: 'flights to Lisbon' }),
    session({ id: 'b', title: 'Standup notes', preview: 'sprint goals' }),
  ];

  it('matches the title case-insensitively', () => {
    expect(filterSessions(sessions, 'TRIP').map((s) => s.id)).toEqual(['a']);
  });

  it('matches the preview, so searching message text works', () => {
    expect(filterSessions(sessions, 'lisbon').map((s) => s.id)).toEqual(['a']);
  });

  it('returns everything for an empty or whitespace query', () => {
    expect(filterSessions(sessions, '')).toHaveLength(2);
    expect(filterSessions(sessions, '   ')).toHaveLength(2);
  });
});

describe('groupSessionsByDate', () => {
  const now = new Date('2026-08-03T12:00:00').getTime();
  const at = (iso: string) => session({ id: iso, updatedAt: iso });

  it('buckets into Today, Yesterday, This Week, Older in that fixed order', () => {
    const groups = groupSessionsByDate(
      [
        at('2026-06-01T09:00:00'),
        at('2026-08-03T09:00:00'),
        at('2026-07-30T09:00:00'),
        at('2026-08-02T09:00:00'),
      ],
      now,
    );

    expect(groups.map((g) => g.label)).toEqual([
      'Today',
      'Yesterday',
      'This Week',
      'Older',
    ]);
  });

  it('omits empty buckets', () => {
    const groups = groupSessionsByDate([at('2026-08-03T09:00:00')], now);

    expect(groups.map((g) => g.label)).toEqual(['Today']);
  });

  it('keeps server order within a bucket', () => {
    const groups = groupSessionsByDate(
      [at('2026-08-03T11:00:00'), at('2026-08-03T08:00:00')],
      now,
    );

    expect(groups[0].sessions.map((s) => s.updatedAt)).toEqual([
      '2026-08-03T11:00:00',
      '2026-08-03T08:00:00',
    ]);
  });

  it('puts an unparseable timestamp in Older rather than dropping it', () => {
    const groups = groupSessionsByDate([session({ updatedAt: 'nonsense' })], now);

    expect(groups.map((g) => g.label)).toEqual(['Older']);
  });
});

describe('deleteAndRethread', () => {
  it('re-threads to the shared thread when the active session is deleted', async () => {
    const remove = vi.fn().mockResolvedValue(undefined);
    const switchThread = vi.fn();

    await deleteAndRethread(remove, 'sess-1', switchThread, 'sess-1');

    expect(remove).toHaveBeenCalledWith('sess-1');
    expect(switchThread).toHaveBeenCalledWith(null);
  });

  it('leaves the reader in place when a different session is deleted', async () => {
    const remove = vi.fn().mockResolvedValue(undefined);
    const switchThread = vi.fn();

    await deleteAndRethread(remove, 'sess-1', switchThread, 'sess-2');

    expect(switchThread).not.toHaveBeenCalled();
  });

  it('does not re-thread when the delete fails', async () => {
    // Otherwise a failed delete moves the reader off a session that still
    // exists, and the transcript on screen no longer matches the selection.
    const remove = vi.fn().mockRejectedValue(new Error('offline'));
    const switchThread = vi.fn();

    await deleteAndRethread(remove, 'sess-1', switchThread, 'sess-1');

    expect(switchThread).not.toHaveBeenCalled();
  });
});
