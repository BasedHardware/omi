import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ConversationSplitView } from '@/components/conversations/ConversationSplitView';
import type { Conversation } from '@/types/conversation';
import type { DailySummary } from '@/types/recap';
import type { Folder } from '@/types/folder';

// The real MergeActionBar and MoveFolderDialog render here, so the test presses
// Move and picks a folder the way a user does, and the page's move handler runs.
const harness = vi.hoisted(() => ({
  conversations: [] as Conversation[],
  recaps: [] as DailySummary[],
  searchResults: [] as Conversation[],
  refresh: vi.fn(),
  bulkMoveConversationsToFolder: vi.fn(),
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
// The selection bar, with its Move button, renders in the toolbar's `below` slot.
vi.mock('@/components/layout/PageToolbar', () => ({
  PageToolbar: ({ below }: { below?: React.ReactNode }) => <div>{below}</div>,
}));
// A double-click on a tile enters selection mode with that conversation selected.
vi.mock('@/components/conversations/ConversationGallery', () => ({
  ConversationGallery: ({
    groups,
    onEnterSelectionMode,
  }: {
    groups: Array<{ items: Array<{ id: string }> }>;
    onEnterSelectionMode?: (id: string) => void;
  }) => (
    <div>
      {groups
        .flatMap((group) => group.items)
        .map((item) => (
          <button
            key={item.id}
            type="button"
            onDoubleClick={() => onEnterSelectionMode?.(item.id)}
          >
            {item.id}
          </button>
        ))}
    </div>
  ),
  ConversationGallerySkeleton: () => null,
}));
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
vi.mock('@/components/ui/ResizeHandle', () => ({ ResizeHandle: () => null }));
vi.mock('@/lib/api', () => ({
  getFolders: harness.getFolders,
  createFolder: vi.fn(),
  updateFolder: vi.fn(),
  deleteFolder: vi.fn(),
  bulkMoveConversationsToFolder: harness.bulkMoveConversationsToFolder,
  mergeConversations: vi.fn(),
  toggleStarred: vi.fn(),
  deleteConversation: vi.fn(),
}));

const workFolder: Folder = {
  id: 'folder-work',
  name: 'Work',
  created_at: '2026-08-01T00:00:00Z',
};

function conversation(id: string, startedAt: string): Conversation {
  return {
    id,
    created_at: startedAt,
    started_at: startedAt,
    structured: { title: id, overview: `${id} overview`, emoji: '', category: 'other' },
  } as unknown as Conversation;
}

// Select the conversation, press Move and pick the Work folder in the dialog.
async function moveSelectionToWorkFolder() {
  render(<ConversationSplitView />);
  fireEvent.doubleClick(screen.getByRole('button', { name: 'team-sync' }));
  fireEvent.click(screen.getByRole('button', { name: 'Move' }));
  fireEvent.click(await screen.findByRole('button', { name: /Work/ }));
}

beforeEach(() => {
  harness.conversations = [conversation('team-sync', '2026-08-11T12:00:00Z')];
  harness.refresh.mockReset().mockResolvedValue(undefined);
  harness.bulkMoveConversationsToFolder.mockReset();
  harness.showToast.mockReset();
  harness.setContext.mockReset();
  harness.getFolders.mockReset().mockResolvedValue([workFolder]);
  harness.getRecapDetail.mockReset().mockResolvedValue(null);
});

describe('ConversationSplitView move to folder', () => {
  it('tells the user when the conversations could not be moved', async () => {
    harness.bulkMoveConversationsToFolder.mockRejectedValue(
      new Error('API error: 500 Internal Server Error'),
    );

    await moveSelectionToWorkFolder();

    await waitFor(() =>
      expect(harness.showToast).toHaveBeenCalledWith(
        'Failed to move conversations. Please try again.',
        'error',
      ),
    );
    expect(harness.bulkMoveConversationsToFolder).toHaveBeenCalledWith('folder-work', [
      'team-sync',
    ]);
    // The dialog stays open with its folders usable again, so the move can be retried.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Work/ })).toBeEnabled(),
    );
    expect(harness.refresh).not.toHaveBeenCalled();
  });

  it('closes the dialog without an error once the conversations have moved', async () => {
    harness.bulkMoveConversationsToFolder.mockResolvedValue(undefined);

    await moveSelectionToWorkFolder();

    await waitFor(() => expect(harness.refresh).toHaveBeenCalledOnce());
    expect(harness.bulkMoveConversationsToFolder).toHaveBeenCalledWith('folder-work', [
      'team-sync',
    ]);
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /Work/ })).not.toBeInTheDocument(),
    );
    expect(harness.showToast).not.toHaveBeenCalled();
  });
});
