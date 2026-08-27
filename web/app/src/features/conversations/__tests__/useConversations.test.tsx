import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Conversation } from '@/types/conversation';
import { clearAllCache } from '@/lib/cache';

vi.mock('@/features/conversations/api', () => ({
  getConversations: vi.fn(),
}));

const api = await import('@/features/conversations/api');
const { useConversations } = await import('@/features/conversations/useConversations');

function conversation(id: string): Conversation {
  return {
    id,
    created_at: '2026-01-01T00:00:00Z',
    started_at: '2026-01-01T00:00:00Z',
    structured: { title: id, overview: '', emoji: '', category: 'other' },
  } as unknown as Conversation;
}

beforeEach(() => {
  vi.clearAllMocks();
  clearAllCache();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('useConversations', () => {
  it('loads conversations on mount', async () => {
    vi.mocked(api.getConversations).mockResolvedValue([conversation('c1')]);
    const { result } = renderHook(() => useConversations());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.conversations.map((entry) => entry.id)).toEqual(['c1']);
    expect(result.current.error).toBeNull();
  });

  it('surfaces a load failure', async () => {
    vi.mocked(api.getConversations).mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useConversations());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('network down');
    expect(result.current.conversations).toEqual([]);
  });
});
