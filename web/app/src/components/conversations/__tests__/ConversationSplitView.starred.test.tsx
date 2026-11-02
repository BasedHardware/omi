import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ConversationSplitView } from '@/components/conversations/ConversationSplitView';
import type { GetConversationsParams } from '@/lib/api';
import { clearAllCache } from '@/lib/cache';
import type { Conversation } from '@/types/conversation';
import type { DailySummary } from '@/types/recap';

// The real useConversations hook, cache and FolderTabs run here; only the API
// module is replaced, so the test sees exactly what the Starred tab requests.
const harness = vi.hoisted(() => ({
  getConversations: vi.fn(),
  getFolders: vi.fn(),
  recaps: [] as DailySummary[],
  refreshRecaps: vi.fn(),
  getRecapDetail: vi.fn(),
  searchResults: [] as Conversation[],
  performSearch: vi.fn(),
  clearSearch: vi.fn(),
  setContext: vi.fn(),
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
vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => ({ user: { displayName: 'Ada' } }),
}));
vi.mock('@/components/chat/ChatContext', () => ({
  useChat: () => ({ setContext: harness.setContext }),
}));
vi.mock('@/components/ui/Toast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));
vi.mock('@/hooks/useLocalStorage', () => ({
  useLocalStorage: () => [480, vi.fn()],
}));
vi.mock('@/hooks/useConversation', () => ({
  useConversation: () => ({ conversation: null, loading: false, update: vi.fn() }),
}));
vi.mock('@/hooks/useRecaps', () => ({
  useRecaps: () => ({
    recaps: harness.recaps,
    loading: false,
    error: null,
    refresh: harness.refreshRecaps,
    hasMore: false,
    loadMore: vi.fn(),
    getRecapDetail: harness.getRecapDetail,
  }),
}));
vi.mock('@/hooks/useSearchConversations', () => ({
  useSearchConversations: () => ({
    results: harness.searchResults,
    loading: false,
    search: harness.performSearch,
    clear: harness.clearSearch,
  }),
}));
vi.mock('@/components/layout/PageToolbar', () => ({
  PageToolbar: ({ controls }: { controls?: React.ReactNode }) => <div>{controls}</div>,
}));
vi.mock('@/components/conversations/ConversationGallery', () => ({
  ConversationGallery: ({
    groups,
  }: {
    groups: Array<{ items: Array<{ id: string }> }>;
  }) => (
    <div data-testid="conversation-gallery">
      {groups
        .flatMap((group) => group.items)
        .map((item) => (
          <span key={item.id}>{item.id}</span>
        ))}
    </div>
  ),
  ConversationGallerySkeleton: () => <div>Loading timeline</div>,
}));
vi.mock('@/components/conversations/ConversationDetailPanel', () => ({
  ConversationDetailPanel: ({ conversationId }: { conversationId: string }) => (
    <div data-testid="conversation-detail">{conversationId}</div>
  ),
}));
vi.mock('@/components/recaps/RecapDetailPanel', () => ({
  RecapDetailPanel: () => null,
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
  getConversations: harness.getConversations,
  getFolders: harness.getFolders,
  createFolder: vi.fn(),
  updateFolder: vi.fn(),
  deleteFolder: vi.fn(),
  bulkMoveConversationsToFolder: vi.fn(),
  mergeConversations: vi.fn(),
  toggleStarred: vi.fn(),
  deleteConversation: vi.fn(),
}));

function conversation(id: string, startedAt: string, starred = false): Conversation {
  return {
    id,
    created_at: startedAt,
    started_at: startedAt,
    starred,
    structured: { title: id, overview: `${id} overview`, emoji: '', category: 'other' },
  } as unknown as Conversation;
}

// The first page of All: the 50 newest conversations, none of them starred.
const firstPage = Array.from({ length: 50 }, (_, index) =>
  conversation(
    `recent-${index}`,
    new Date(Date.UTC(2026, 9, 18, 12) - index * 3_600_000).toISOString(),
  ),
);
// Starred months ago, so it is only on a later page of All.
const starredInMay = conversation('starred-in-may', '2026-05-04T10:00:00Z', true);

beforeEach(() => {
  clearAllCache();
  harness.getFolders.mockReset().mockResolvedValue([]);
  harness.getConversations
    .mockReset()
    .mockImplementation(async (params?: GetConversationsParams) =>
      params?.starred ? [starredInMay] : firstPage,
    );
  harness.refreshRecaps.mockReset();
  harness.getRecapDetail.mockReset().mockResolvedValue(null);
  harness.performSearch.mockReset().mockResolvedValue(undefined);
  harness.clearSearch.mockReset();
  harness.setContext.mockReset();
});

describe('ConversationSplitView Starred tab', () => {
  it('loads starred conversations from the server, not from the page loaded for All', async () => {
    render(<ConversationSplitView />);
    await waitFor(() =>
      expect(screen.getByTestId('conversation-gallery')).toHaveTextContent('recent-0'),
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Starred' }));

    await waitFor(() =>
      expect(screen.getByTestId('conversation-gallery')).toHaveTextContent(
        'starred-in-may',
      ),
    );
    expect(screen.getByTestId('conversation-gallery')).not.toHaveTextContent('recent-');
    expect(harness.getConversations).toHaveBeenLastCalledWith(
      expect.objectContaining({ offset: 0, starred: true }),
    );

    // All keeps its own list rather than the starred one.
    fireEvent.click(screen.getByRole('button', { name: 'All' }));

    await waitFor(() =>
      expect(screen.getByTestId('conversation-gallery')).toHaveTextContent('recent-0'),
    );
    expect(screen.getByTestId('conversation-gallery')).not.toHaveTextContent(
      'starred-in-may',
    );
  });
});
