import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  replaceConversation: vi.fn(),
  replaceSearchConversation: vi.fn(),
  toggleStarred: vi.fn(),
  reprocessConversation: vi.fn(),
  showToast: vi.fn(),
  setContext: vi.fn(),
  getHomeFailurePlacement: vi.fn(),
  getAttentionItems: vi.fn(),
  retryAttentionItem: vi.fn(),
  getFolders: vi.fn(),
  getRecapDetail: vi.fn(),
}));

vi.mock('@tschk/moonshine-next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: {
    div: ({
      children,
      role,
      'aria-label': label,
    }: React.HTMLAttributes<HTMLDivElement>) => (
      <div role={role} aria-label={label}>
        {children}
      </div>
    ),
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
    replaceConversation: harness.replaceConversation,
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
    replaceConversation: harness.replaceSearchConversation,
  }),
}));
vi.mock('@/components/layout/PageToolbar', () => ({
  PageToolbar: ({ controls }: { controls: React.ReactNode }) => <div>{controls}</div>,
}));
vi.mock('@/components/conversations/ConversationDetailPanel', () => ({
  ConversationDetailPanel: () => null,
}));
vi.mock('@/components/recaps/RecapDetailPanel', () => ({ RecapDetailPanel: () => null }));
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
  getHomeFailurePlacement: harness.getHomeFailurePlacement,
  getAttentionItems: harness.getAttentionItems,
  retryAttentionItem: harness.retryAttentionItem,
  getFolders: harness.getFolders,
  createFolder: vi.fn(),
  updateFolder: vi.fn(),
  deleteFolder: vi.fn(),
  bulkMoveConversationsToFolder: vi.fn(),
  mergeConversations: vi.fn(),
  toggleStarred: harness.toggleStarred,
  reprocessConversation: harness.reprocessConversation,
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
  harness.searchResults = [];
  harness.recaps = [];
  harness.replaceConversation.mockClear();
  harness.replaceSearchConversation.mockClear();
  harness.conversations = [conversation('team-sync', '2026-08-11T12:00:00Z')];
  harness.refresh.mockReset().mockResolvedValue(undefined);
  harness.toggleStarred.mockReset();
  harness.reprocessConversation.mockReset();
  harness.showToast.mockReset();
  harness.setContext.mockReset();
  harness.getHomeFailurePlacement.mockReset().mockResolvedValue(false);
  harness.getAttentionItems.mockReset().mockResolvedValue({ items: [] });
  harness.retryAttentionItem
    .mockReset()
    .mockResolvedValue({ operation_id: 'op', state: 'in_progress' });
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
    expect(screen.getByRole('button', { name: 'Star conversation' })).toBeInTheDocument();

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

describe('ConversationSplitView failed tile retry', () => {
  it('wires the gallery Retry to reprocessing and refreshes the feed', async () => {
    harness.conversations[0] = {
      ...harness.conversations[0],
      status: 'processing',
      home_step: 'failed',
    };
    const updated = {
      ...harness.conversations[0],
      status: 'completed',
      home_step: 'done',
    } as Conversation;
    harness.reprocessConversation.mockResolvedValue(updated);
    render(<ConversationSplitView />);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(harness.refresh).toHaveBeenCalledOnce());
    expect(harness.reprocessConversation).toHaveBeenCalledExactlyOnceWith('team-sync');
    expect(harness.replaceConversation).toHaveBeenCalledExactlyOnceWith(updated);
    expect(harness.replaceSearchConversation).toHaveBeenCalledExactlyOnceWith(updated);
  });
});

describe('failed conversation Activity placement', () => {
  it('ignores an old successful confirmation after a newer failed read', async () => {
    harness.conversations = [
      {
        ...conversation('failed-notes', '2026-11-10T08:00:00Z'),
        home_step: 'failed' as const,
      },
    ];
    let finish!: (confirmed: boolean) => void;
    harness.getHomeFailurePlacement.mockReturnValueOnce(
      new Promise<boolean>((resolve) => {
        finish = resolve;
      }),
    );
    render(<ConversationSplitView />);
    await waitFor(() => expect(harness.getHomeFailurePlacement).toHaveBeenCalledOnce());
    harness.getHomeFailurePlacement.mockRejectedValueOnce(new Error('offline'));
    fireEvent(window, new Event('focus'));
    await waitFor(() => expect(harness.getHomeFailurePlacement).toHaveBeenCalledTimes(2));
    await act(async () => finish(true));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Conversation:/ })).toBeInTheDocument(),
    );
    expect(screen.queryByRole('button', { name: 'Activity' })).not.toBeInTheDocument();
  });

  it('hides failure from All, exposes Activity retry, and restores previous Home on read failure', async () => {
    const failed = {
      ...conversation('failed-notes', '2026-11-10T08:00:00Z'),
      home_step: 'failed' as const,
    };
    harness.conversations = [failed];
    harness.getHomeFailurePlacement.mockResolvedValue(true);
    render(<ConversationSplitView />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Activity' })).toBeInTheDocument(),
    );
    expect(
      screen.queryByRole('button', { name: /Conversation:/ }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Activity' }));
    expect(screen.getByRole('button', { name: /Conversation:/ })).toBeInTheDocument();
    harness.reprocessConversation.mockResolvedValue({
      ...failed,
      home_step: 'ready',
      status: 'completed',
    });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() =>
      expect(harness.reprocessConversation).toHaveBeenCalledExactlyOnceWith(
        'failed-notes',
      ),
    );
    harness.getHomeFailurePlacement.mockRejectedValueOnce(new Error('offline'));
    fireEvent(window, new Event('focus'));
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Activity' })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole('button', { name: /Conversation:/ })).toBeInTheDocument();
  });
});

describe('notes ledger inside Activity', () => {
  it('dedupes a projected failed row, routes retry through the ledger, and preserves saved outputs', async () => {
    const saved = {
      ...conversation('kept-outputs', '2026-11-10T12:00:00Z'),
      home_step: 'failed',
      status: 'processing',
    } as Conversation;
    saved.structured.action_items = [
      { description: 'Follow up', completed: false },
    ] as never;
    const before = JSON.stringify(saved);
    harness.conversations = [saved];
    harness.getHomeFailurePlacement.mockResolvedValue(true);
    harness.getAttentionItems.mockResolvedValue({
      items: [
        {
          id: 'notes-item',
          kind: 'conversation_notes_failed_with_outputs',
          conversation_id: saved.id,
          retryable: true,
          retry: { state: 'none', operation_id: null },
          title: 'Notes need another try',
        },
      ],
    });
    render(<ConversationSplitView />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Activity' })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Activity' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Re-run notes' })).toBeInTheDocument(),
    );
    expect(screen.queryByText('kept-outputs')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Re-run notes' }));
    await waitFor(() =>
      expect(
        screen.queryByRole('button', { name: 'Re-run notes' }),
      ).not.toBeInTheDocument(),
    );
    expect(harness.retryAttentionItem).toHaveBeenCalledWith(
      'notes-item',
      expect.any(String),
    );
    expect(harness.reprocessConversation).not.toHaveBeenCalled();
    expect(JSON.stringify(saved)).toBe(before);
    expect(screen.queryByText('kept-outputs')).not.toBeInTheDocument();
  });
});

describe('off-page remembered Activity retry', () => {
  async function offPageFailure() {
    const failed = {
      ...conversation('old-search', '2026-11-08T08:00:00Z'),
      home_step: 'failed',
      status: 'processing',
    } as Conversation;
    harness.searchResults = [failed];
    harness.conversations = [];
    harness.getHomeFailurePlacement.mockResolvedValue(true);
    const view = render(<ConversationSplitView />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Activity' })).toBeInTheDocument(),
    );
    harness.searchResults = [];
    view.rerender(<ConversationSplitView />);
    fireEvent.click(screen.getByRole('button', { name: 'Activity' }));
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    return { failed, view };
  }

  it.each(['processing', 'completed'] as const)(
    'removes a remembered search failure after %s retry',
    async (status) => {
      const { failed } = await offPageFailure();
      harness.reprocessConversation.mockResolvedValue({
        ...failed,
        home_step: undefined,
        status,
      });
      fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
      await waitFor(() =>
        expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument(),
      );
      expect(screen.getByText('No failed conversations')).toBeInTheDocument();
      expect(harness.replaceConversation).toHaveBeenCalled();
    },
  );

  it('removes a remembered search failure after an explicit terminal conflict', async () => {
    await offPageFailure();
    harness.reprocessConversation.mockRejectedValue(
      Object.assign(new Error('not retryable'), { status: 409, state: 'not_retryable' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument(),
    );
    expect(harness.replaceConversation).not.toHaveBeenCalled();
  });

  it.each(['transport', 'generic-conflict', 'failed-result'])(
    'keeps a remembered search failure on %s',
    async (failure) => {
      const { failed } = await offPageFailure();
      if (failure === 'failed-result')
        harness.reprocessConversation.mockResolvedValue(failed);
      else
        harness.reprocessConversation.mockRejectedValue(
          Object.assign(
            new Error('offline'),
            failure === 'generic-conflict' ? { status: 409 } : {},
          ),
        );
      fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
      await waitFor(() => expect(harness.reprocessConversation).toHaveBeenCalledOnce());
      await waitFor(() =>
        expect(screen.getByRole('button', { name: 'Retry' })).toBeEnabled(),
      );
      expect(screen.queryByText('No failed conversations')).not.toBeInTheDocument();
      expect(screen.getByText('Retry failed. Please try again.')).toBeInTheDocument();
    },
  );
});

describe('notes-only retries reconcile remembered failures', () => {
  it.each(['in_progress', 'not_retryable', 'transport'])(
    'handles an off-page notes retry with %s',
    async (state) => {
      const failed = {
        ...conversation('old-notes-search', '2026-11-08T08:00:00Z'),
        home_step: 'failed',
        status: 'processing',
      } as Conversation;
      const notes = {
        id: 'notes-offpage',
        kind: 'conversation_notes_failed_with_outputs',
        conversation_id: failed.id,
        retryable: true,
        retry: { state: 'none', operation_id: null },
      };
      harness.conversations = [];
      harness.searchResults = [failed];
      harness.getHomeFailurePlacement.mockResolvedValue(true);
      harness.getAttentionItems.mockResolvedValue({ items: [notes] });
      if (state === 'not_retryable')
        harness.retryAttentionItem.mockRejectedValueOnce(
          Object.assign(new Error('terminal'), { status: 409, state }),
        );
      else if (state === 'transport')
        harness.retryAttentionItem.mockRejectedValueOnce(new Error('offline'));
      const view = render(<ConversationSplitView />);
      await waitFor(() =>
        expect(screen.getByRole('button', { name: 'Activity' })).toBeInTheDocument(),
      );
      harness.searchResults = [];
      view.rerender(<ConversationSplitView />);
      fireEvent.click(screen.getByRole('button', { name: 'Activity' }));
      await waitFor(() =>
        expect(screen.getByRole('button', { name: 'Re-run notes' })).toBeInTheDocument(),
      );
      fireEvent.click(screen.getByRole('button', { name: 'Re-run notes' }));
      await waitFor(() => expect(harness.retryAttentionItem).toHaveBeenCalledOnce());
      if (state !== 'in_progress') {
        await waitFor(() =>
          expect(screen.getByRole('button', { name: 'Re-run notes' })).toBeEnabled(),
        );
      }
      // The next ledger read no longer contains the item. Its old search-only
      // projection must not become a second Retry tile after acknowledgement.
      harness.getAttentionItems.mockResolvedValue({ items: [] });
      fireEvent(window, new Event('focus'));
      await waitFor(() =>
        expect(
          screen.queryByRole('button', { name: 'Re-run notes' }),
        ).not.toBeInTheDocument(),
      );
      if (state === 'transport')
        expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
      else
        expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
      expect(harness.reprocessConversation).not.toHaveBeenCalled();
    },
  );
});
