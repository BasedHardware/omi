import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DailySummary } from '@/types/recap';
import { clearAllCache } from '@/lib/cache';

vi.mock('@/features/conversations/api', () => ({
  getDailySummaries: vi.fn(),
  getDailySummary: vi.fn(),
  deleteDailySummary: vi.fn(),
  generateTestDailySummary: vi.fn(),
}));

const api = await import('@/features/conversations/api');
const { useRecaps } = await import('@/features/conversations/useRecaps');

function recap(id: string, date = '2025-01-15'): DailySummary {
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
    created_at: '2025-01-15T00:00:00Z',
  };
}

async function renderLoaded(initial: DailySummary[] = [recap('r1')]) {
  vi.mocked(api.getDailySummaries).mockResolvedValue(initial);
  const view = renderHook(() => useRecaps());
  await waitFor(() => expect(view.result.current.loading).toBe(false));
  return view;
}

beforeEach(() => {
  vi.clearAllMocks();
  clearAllCache();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('useRecaps', () => {
  it('loads recaps on mount', async () => {
    const { result } = await renderLoaded();
    expect(result.current.recaps.map((entry) => entry.id)).toEqual(['r1']);
  });

  it('puts a recap back when delete fails', async () => {
    const { result } = await renderLoaded();
    vi.mocked(api.deleteDailySummary).mockRejectedValue(new Error('locked'));

    let succeeded = true;
    await act(async () => {
      succeeded = await result.current.removeRecap('r1');
    });

    expect(succeeded).toBe(false);
    expect(result.current.recaps.map((entry) => entry.id)).toEqual(['r1']);
    expect(result.current.error).toBe('locked');
  });
});
