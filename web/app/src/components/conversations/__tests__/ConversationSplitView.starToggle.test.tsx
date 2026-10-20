import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ConversationSplitView } from '@/components/conversations/ConversationSplitView';
import type { Conversation } from '@/types/conversation';
import type { DailySummary } from '@/types/recap';

// The real ConversationGallery and ConversationTile render here, so a click on
// the star runs the tile's optimistic update and the page's star request.
const harness = vi.hoisted(() => ({
  conversations: [] as Conversation[],
  recaps: [] as DailySummary[],
  searchResults: [] as Conversation[],
  refresh: vi.fn(),
  toggleStarred: vi.fn(),
  showToast: vi.fn(),
  setContext: vi.fn(),
  getFolders: vi.fn(),
  getRecapDetail: vi.fn(),
}));

vi.mock('@tschk/moonshine-next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: {
    div: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  },
}));
vi.mock('@/lib/analytics/posthog', () => ({
  PostHogManager: { track: vi.fn() },
}));
vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => ({ user: { displayName: 'Ada' } }),
}));
vi.mock('@/components/chat/ChatContext', () => ({
  useChat: () => ({ setContext: harness.setContext }),
}));
vi.mock('@/components/ui/Toast', () => ({
  useToast: () => ({ showToast: harness.showToast }),
}));
vi.mock('@/hooks/useLocalStorage', () => ({
  useLocalStorage: () => [480, vi.fn()],
}));
vi.mock('@/hooks/useConversations', () => ({
  useConversations: () => ({
    conversations: harness.conversations,
    loading: false,
    error: null,
    hasMore: false,
    loadMore: vi.fn(),
    refresh: harness.refresh,
  }),
}));
vi.mock('@/hooks/useConversation', () => ({
  useConversation: () => ({ conversation: null, loading: false, update: vi.fn() }),
}));
vi.mock('@/hooks/useRecaps', () => ({
  useRecaps: () => ({
    recaps: harness.recaps,
    loading: false,
    error: null,
    refresh: vi.fn(),
    hasMore: false,
    loadMore: vi.fn(),
    getRecapDetail: harness.getRecapDetail,
  }),
}));
vi.mock('@/hooks/useSearchConversations', () => ({
  useSearchConversations: () => ({
    results: harness.searchResults,
    loading: false,
    search: vi.fn(),
    clear: vi.fn(),
  }),
}));
vi.mock('@/components/layout/PageToolbar', () => ({ PageToolbar: () => null }));
vi.mock('@/components/conversations/ConversationDetailPanel', () => ({
  ConversationDetailPanel: () => null,
}));
vi.mock('@/components/recaps/RecapDetailPanel', () => ({ RecapDetailPanel: () => null }));
vi.mock('@/components/conversations/FolderTabs', () => ({
  FOLDER_ALL: 'all',
  FOLDER_STARRED: 'starred',
  FolderTabs: () => null,
  FolderTabsSkeleton: () => null,
}));
vi.mock('@/components/conversations/DateFilter', () => ({ DateFilter: () => null }));
vi.mock('@/components/conversations/MergeActionBar', () => ({
  MergeActionBar: () => null,
}));
vi.mock('@/components/conversations/MergeConfirmationDialog', () => ({
  MergeConfirmationDialog: () => null,
}));
vi.mock('@/components/conversations/DeleteConversationsDialog', () => ({
  DeleteConversationsDialog: () => null,
}));
vi.mock('@/components/conversations/FolderDialog', () => ({
  FolderDialog: () => null,
  DeleteFolderDialog: () => null,
}));
vi.mock('@/components/conversations/MoveFolderDialog', () => ({
  MoveFolderDialog: () => null,
}));
vi.mock('@/components/ui/ResizeHandle', () => ({ ResizeHandle: () => null }));
vi.mock('@/lib/api', () => ({
  getFolders: harness.getFolders,
  createFolder: vi.fn(),
  updateFolder: vi.fn(),
  deleteFolder: vi.fn(),
  bulkMoveConversationsToFolder: vi.fn(),
  mergeConversations: vi.fn(),
  toggleStarred: harness.toggleStarred,
  deleteConversation: vi.fn(),
}));

function conversation(id: string, startedAt: string): Conversation {
  return {
    id,
    created_at: startedAt,
    started_at: startedAt,
    starred: false,
    structured: { title: id, overview: `${id} overview`, emoji: '', category: 'other' },
  } as unknown as Conversation;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  harness.conversations = [conversation('team-sync', '2026-08-11T12:00:00Z')];
  harness.refresh.mockReset().mockResolvedValue(undefined);
  harness.toggleStarred.mockReset();
  harness.showToast.mockReset();
  harness.setContext.mockReset();
  harness.getFolders.mockReset().mockResolvedValue([]);
  harness.getRecapDetail.mockReset().mockResolvedValue(null);
});

describe('ConversationSplitView star toggle', () => {
  it('takes the star back when the server does not save it', async () => {
    harness.toggleStarred.mockRejectedValue(
      new Error('API error: 500 Internal Server Error'),
    );
    render(<ConversationSplitView />);

    fireEvent.click(screen.getByRole('button', { name: 'Star conversation' }));

    // The tile shows the star before the server answers...
    expect(
      screen.getByRole('button', { name: 'Unstar conversation' }),
    ).toBeInTheDocument();
    // ...and must not keep showing it once the server has refused it.
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Star conversation' }),
      ).toBeInTheDocument(),
    );
    expect(harness.toggleStarred).toHaveBeenCalledWith('team-sync', true);
    expect(harness.showToast).toHaveBeenCalledWith(
      'Failed to update starred status. Please try again.',
      'error',
    );
    expect(harness.refresh).not.toHaveBeenCalled();
  });

  it('keeps the star once the server has saved it', async () => {
    harness.toggleStarred.mockResolvedValue(undefined);
    render(<ConversationSplitView />);

    fireEvent.click(screen.getByRole('button', { name: 'Star conversation' }));

    await waitFor(() => expect(harness.refresh).toHaveBeenCalledOnce());
    expect(
      screen.getByRole('button', { name: 'Unstar conversation' }),
    ).toBeInTheDocument();
    expect(harness.toggleStarred).toHaveBeenCalledWith('team-sync', true);
    expect(harness.showToast).not.toHaveBeenCalled();
  });

  it('sends one star request at a time, so a failure restores the right value', async () => {
    const firstRequest = deferred<void>();
    harness.toggleStarred
      .mockReturnValueOnce(firstRequest.promise)
      .mockResolvedValue(undefined);
    render(<ConversationSplitView />);

    fireEvent.click(screen.getByRole('button', { name: 'Star conversation' }));
    // A second click while the first request is in flight is ignored. If both
    // were sent and both failed, each would restore a different value.
    fireEvent.click(screen.getByRole('button', { name: 'Unstar conversation' }));
    expect(harness.toggleStarred).toHaveBeenCalledTimes(1);

    firstRequest.reject(new Error('API error: 503 Service Unavailable'));
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Star conversation' }),
      ).toBeInTheDocument(),
    );

    // Once that request has settled, the star responds again.
    fireEvent.click(screen.getByRole('button', { name: 'Star conversation' }));
    expect(harness.toggleStarred).toHaveBeenCalledTimes(2);
    expect(harness.toggleStarred).toHaveBeenLastCalledWith('team-sync', true);
    await waitFor(() => expect(harness.refresh).toHaveBeenCalledOnce());
    expect(
      screen.getByRole('button', { name: 'Unstar conversation' }),
    ).toBeInTheDocument();
  });

  it('updates the tile star when a refetch changes conversation.starred', async () => {
    const { rerender } = render(<ConversationSplitView />);
    expect(
      screen.getByRole('button', { name: 'Star conversation' }),
    ).toBeInTheDocument();

    harness.conversations = [
      { ...conversation('team-sync', '2026-08-11T12:00:00Z'), starred: true },
    ];
    rerender(<ConversationSplitView />);

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Unstar conversation' }),
      ).toBeInTheDocument(),
    );
  });
});
