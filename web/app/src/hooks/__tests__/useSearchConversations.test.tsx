import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Conversation } from '@/types/conversation';
import { useSearchConversations } from '../useSearchConversations';
import { searchConversations } from '@/lib/api';
import { useActivityFailures } from '@/hooks/useActivityFailures';
import { isConversationProcessing } from '@/lib/conversationHome';

vi.mock('@/lib/api', () => ({ searchConversations: vi.fn() }));
beforeEach(() => vi.resetAllMocks());

describe('search retry response replacement', () => {
  it('clears a search-only failure when retry returns processing without home_step', async () => {
    const failed = {
      id: 'search-only',
      home_step: 'failed',
      status: 'processing',
    } as Conversation;
    vi.mocked(searchConversations).mockResolvedValueOnce({
      items: [failed],
      current_page: 1,
      total_pages: 1,
    } as never);
    const empty: Conversation[] = [];
    const { result } = renderHook(() => {
      const search = useSearchConversations();
      const activity = useActivityFailures(empty, search.results, 'owner');
      return { ...search, failures: activity.failures };
    });
    await act(async () => result.current.search('planning'));
    expect(result.current.failures).toEqual([failed]);
    const processing = { id: failed.id, status: 'processing' } as Conversation;
    act(() => result.current.replaceConversation(processing));
    expect(result.current.results).toEqual([processing]);
    expect(result.current.failures).toEqual([]);
    expect(isConversationProcessing(result.current.results[0])).toBe(true);
  });

  it('ignores a search response started before retry completion', async () => {
    const failed = {
      id: 'search-only',
      home_step: 'failed',
      status: 'processing',
    } as Conversation;
    const response = { items: [failed], current_page: 1, total_pages: 1 };
    vi.mocked(searchConversations).mockResolvedValueOnce(response as never);
    const { result } = renderHook(useSearchConversations);
    await act(async () => result.current.search('planning'));
    let finish!: (value: never) => void;
    vi.mocked(searchConversations).mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.search('planning');
    });
    const completed = {
      ...failed,
      home_step: 'done',
      status: 'completed',
    } as Conversation;
    act(() => result.current.replaceConversation(completed));
    await act(async () => {
      finish(response as never);
      await pending;
    });
    expect(result.current.results).toEqual([completed]);
  });

  it('removes a completed failure even when the follow-up search fails', async () => {
    const failed = {
      id: 'search-only',
      home_step: 'failed',
      status: 'processing',
    } as Conversation;
    vi.mocked(searchConversations).mockResolvedValueOnce({
      items: [failed],
      current_page: 1,
      total_pages: 1,
    } as never);
    const { result } = renderHook(useSearchConversations);
    await act(async () => result.current.search('planning'));
    const completed = {
      ...failed,
      home_step: 'done',
      status: 'completed',
    } as Conversation;
    act(() => result.current.replaceConversation(completed));
    vi.mocked(searchConversations).mockRejectedValueOnce(new Error('offline'));
    await act(async () => result.current.search('planning'));
    expect(result.current.results).toEqual([completed]);
    act(() => result.current.replaceConversation({ ...completed, id: 'other-query' }));
    expect(result.current.results).toEqual([completed]);
  });
});
