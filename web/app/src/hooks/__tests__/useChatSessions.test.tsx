import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useChatSessions } from '@/hooks/useChatSessions';
import type { ChatSession } from '@/types/chatSessions';

vi.mock('@/lib/api', () => ({
  getChatSessions: vi.fn(),
  createChatSession: vi.fn(),
  updateChatSession: vi.fn(),
  deleteChatSession: vi.fn(),
}));

const api = await import('@/lib/api');

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

async function renderLoaded(initial: ChatSession[] = [session()]) {
  vi.mocked(api.getChatSessions).mockResolvedValue(initial);
  const view = renderHook(() => useChatSessions());
  await waitFor(() => expect(view.result.current.loading).toBe(false));
  return view;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('useChatSessions', () => {
  it('loads sessions on mount', async () => {
    const { result } = await renderLoaded();

    expect(result.current.sessions).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });

  it('surfaces a load failure', async () => {
    vi.mocked(api.getChatSessions).mockRejectedValue(new Error('offline'));
    const { result } = renderHook(() => useChatSessions());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('offline');
  });

  it('puts a new chat at the top of the list', async () => {
    const { result } = await renderLoaded();
    vi.mocked(api.createChatSession).mockResolvedValue(session({ id: 'sess-2' }));

    await act(async () => {
      await result.current.addSession();
    });

    expect(result.current.sessions.map((s) => s.id)).toEqual(['sess-2', 'sess-1']);
  });

  it('does not write an unchanged or blank rename', async () => {
    // The ported row calls onRename on every blur.
    const { result } = await renderLoaded();

    await act(async () => {
      await result.current.renameSession('sess-1', 'A chat');
      await result.current.renameSession('sess-1', '   ');
    });

    expect(api.updateChatSession).not.toHaveBeenCalled();
  });

  it('renames optimistically and rolls back on failure', async () => {
    const { result } = await renderLoaded();
    vi.mocked(api.updateChatSession).mockRejectedValue(new Error('nope'));

    await act(async () => {
      await result.current.renameSession('sess-1', 'Renamed');
    });

    expect(result.current.sessions[0].title).toBe('A chat');
    expect(result.current.error).toBe('nope');
  });

  it('toggles the star against the current value', async () => {
    const { result } = await renderLoaded([session({ starred: true })]);
    vi.mocked(api.updateChatSession).mockResolvedValue(session({ starred: false }));

    await act(async () => {
      await result.current.toggleStar('sess-1');
    });

    expect(api.updateChatSession).toHaveBeenCalledWith('sess-1', { starred: false });
  });

  it('re-throws a failed delete so the caller does not re-thread', async () => {
    // deleteAndRethread only switches threads when removeSession resolves.
    const { result } = await renderLoaded();
    vi.mocked(api.deleteChatSession).mockRejectedValue(new Error('offline'));

    await expect(
      act(async () => {
        await result.current.removeSession('sess-1');
      }),
    ).rejects.toThrow('offline');

    expect(result.current.sessions.map((s) => s.id)).toEqual(['sess-1']);
  });

  it('keeps a session removed when the delete succeeds', async () => {
    const { result } = await renderLoaded();
    vi.mocked(api.deleteChatSession).mockResolvedValue(undefined);

    await act(async () => {
      await result.current.removeSession('sess-1');
    });

    expect(result.current.sessions).toEqual([]);
  });
});
