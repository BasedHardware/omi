import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { ConversationSplitView } from '@/components/conversations/ConversationSplitView';
import type { GetConversationsParams } from '@/lib/api';
import type { Conversation } from '@/types/conversation';
import type { DailySummary } from '@/types/recap';

const harness = vi.hoisted(() => ({
  query: '',
  conversations: [] as Conversation[],
  conversationsLoading: false,
  conversationOptions: null as GetConversationsParams | null,
  recaps: [] as DailySummary[],
  recapsLoading: false,
  recapsError: null as string | null,
  refreshRecaps: vi.fn(),
  searchResults: [] as Conversation[],
  searchLoading: false,
  getRecapDetail: vi.fn(),
  performSearch: vi.fn(),
  clearSearch: vi.fn(),
  setContext: vi.fn(),
  getFolders: vi.fn(),
}));

vi.mock('@tschk/moonshine-next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(harness.query),
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
vi.mock('@/hooks/useConversations', () => ({
  useConversations: (options: GetConversationsParams) => {
    harness.conversationOptions = options;
    return {
      conversations: harness.conversations,
      loading: harness.conversationsLoading,
      error: null,
      hasMore: false,
      loadMore: vi.fn(),
      refresh: vi.fn(),
    };
  },
}));
vi.mock('@/hooks/useConversation', () => ({
  useConversation: (id: string | null) => ({
    conversation:
      harness.conversations.find((conversation) => conversation.id === id) ?? null,
    loading: false,
    update: vi.fn(),
  }),
}));
vi.mock('@/hooks/useRecaps', () => ({
  useRecaps: () => ({
    recaps: harness.recaps,
    loading: harness.recapsLoading,
    error: harness.recapsError,
    refresh: harness.refreshRecaps,
    hasMore: false,
    loadMore: vi.fn(),
    getRecapDetail: harness.getRecapDetail,
  }),
}));
vi.mock('@/hooks/useSearchConversations', () => ({
  useSearchConversations: () => ({
    results: harness.searchResults,
    loading: harness.searchLoading,
    search: harness.performSearch,
    clear: harness.clearSearch,
  }),
}));
vi.mock('@/components/layout/PageToolbar', () => ({
  PageToolbar: ({
    search,
    actions,
  }: {
    search: {
      value: string;
      onChange: (value: string) => void;
      onSubmit: (value: string) => void;
      placeholder: string;
    };
    actions?: React.ReactNode;
  }) => (
    <div>
      <input
        aria-label={search.placeholder}
        value={search.value}
        onChange={(event) => search.onChange(event.target.value)}
      />
      <button type="button" onClick={() => search.onSubmit(search.value)}>
        Submit search
      </button>
      {actions}
    </div>
  ),
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
vi.mock('@/components/recaps/GenerateRecapAction', () => ({
  GenerateRecapAction: () => null,
}));
vi.mock('@/components/recaps/RecapDetailPanel', () => ({
  RecapDetailPanel: ({
    recapId,
    recap,
  }: {
    recapId: string;
    recap?: DailySummary | null;
  }) => <div data-testid="recap-detail">{recap?.headline ?? `Loading ${recapId}`}</div>,
}));
vi.mock('@/components/conversations/FolderTabs', () => ({
  FOLDER_ALL: 'all',
  FOLDER_STARRED: 'starred',
  FolderTabs: () => null,
  FolderTabsSkeleton: () => null,
}));
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
  toggleStarred: vi.fn(),
  deleteConversation: vi.fn(),
}));

function conversation(id: string, startedAt: string): Conversation {
  return {
    id,
    created_at: startedAt,
    started_at: startedAt,
    structured: { title: id, overview: `${id} overview`, emoji: '', category: 'other' },
  } as unknown as Conversation;
}

function recap(id: string, date: string, headline = id): DailySummary {
  return {
    id,
    date,
    headline,
    day_emoji: '',
    overview: `${id} overview`,
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
    created_at: `${date}T23:59:00Z`,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

beforeEach(() => {
  harness.query = '';
  harness.conversations = [];
  harness.conversationsLoading = false;
  harness.conversationOptions = null;
  harness.recaps = [];
  harness.recapsLoading = false;
  harness.recapsError = null;
  harness.refreshRecaps.mockReset();
  harness.searchResults = [];
  harness.searchLoading = false;
  harness.getRecapDetail.mockReset().mockResolvedValue(null);
  harness.performSearch.mockReset().mockResolvedValue(undefined);
  harness.clearSearch.mockReset();
  harness.setContext.mockReset();
  harness.getFolders.mockReset().mockResolvedValue([]);
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: false,
      media: '(prefers-reduced-motion: reduce)',
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

describe('ConversationSplitView review regressions', () => {
  it('shows recap read failures with a retry instead of an empty account', async () => {
    harness.recapsError = 'API error: 500';
    render(<ConversationSplitView />);
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Daily Recaps couldn’t load. Try again.',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Retry recaps' }));
    expect(harness.refreshRecaps).toHaveBeenCalledOnce();
    expect(screen.queryByText('No conversations yet')).not.toBeInTheDocument();
  });

  it('clears a removed recap deep link without replacing it from the timeline', async () => {
    const listedRecap = recap('recap-a', '2026-08-11');
    harness.query = 'recap=recap-a';
    harness.recaps = [listedRecap];
    harness.getRecapDetail.mockResolvedValue(listedRecap);

    const { rerender } = render(<ConversationSplitView />);
    expect(screen.getByTestId('recap-detail')).toHaveTextContent('recap-a');

    harness.query = '';
    rerender(<ConversationSplitView />);

    await waitFor(() =>
      expect(screen.queryByTestId('recap-detail')).not.toBeInTheDocument(),
    );
    expect(screen.getByTestId('conversation-gallery')).toBeInTheDocument();
  });

  it('preserves a conversation deep link that replaces a recap deep link', async () => {
    const listedRecap = recap('recap-a', '2026-08-11');
    harness.query = 'recap=recap-a';
    harness.recaps = [listedRecap];
    harness.getRecapDetail.mockResolvedValue(listedRecap);

    const { rerender } = render(<ConversationSplitView />);
    harness.query = 'id=conversation-b';
    rerender(<ConversationSplitView />);

    await waitFor(() =>
      expect(screen.getByTestId('conversation-detail')).toHaveTextContent(
        'conversation-b',
      ),
    );
  });

  it('retains fetched recap context for an out-of-page deep link', async () => {
    const fullRecap = recap('remote-recap', '2026-08-10', 'Remote recap detail');
    harness.query = 'recap=remote-recap';
    harness.getRecapDetail.mockResolvedValue(fullRecap);

    render(<ConversationSplitView />);

    await waitFor(() =>
      expect(screen.getByTestId('recap-detail')).toHaveTextContent('Remote recap detail'),
    );
    await waitFor(() =>
      expect(harness.setContext).toHaveBeenCalledWith({
        type: 'recap',
        id: 'remote-recap',
        title: 'Remote recap detail',
        summary: 'remote-recap overview',
      }),
    );
  });

  it('ignores a stale recap response after the deep-link ID changes', async () => {
    const recapA = deferred<DailySummary | null>();
    const recapB = deferred<DailySummary | null>();
    harness.query = 'recap=recap-a';
    harness.getRecapDetail.mockImplementation((id: string) =>
      id === 'recap-a' ? recapA.promise : recapB.promise,
    );

    const { rerender } = render(<ConversationSplitView />);
    harness.query = 'recap=recap-b';
    rerender(<ConversationSplitView />);

    recapA.resolve(recap('recap-a', '2026-08-10', 'Stale recap'));
    recapB.resolve(recap('recap-b', '2026-08-11', 'Current recap'));

    await waitFor(() =>
      expect(screen.getByTestId('recap-detail')).toHaveTextContent('Current recap'),
    );
    expect(screen.getByTestId('recap-detail')).not.toHaveTextContent('Stale recap');
  });

  it('waits for recaps before auto-selecting the newest combined item', async () => {
    harness.conversations = [conversation('older-conversation', '2026-08-10T12:00:00Z')];
    harness.recapsLoading = true;

    const { rerender } = render(<ConversationSplitView />);
    expect(screen.queryByTestId('conversation-detail')).not.toBeInTheDocument();

    harness.recaps = [recap('newer-recap', '2026-08-11')];
    harness.recapsLoading = false;
    rerender(<ConversationSplitView />);

    await waitFor(() =>
      expect(screen.getByTestId('recap-detail')).toHaveTextContent('newer-recap'),
    );
  });

  it('leaves the detail pane width to the responsive layout', async () => {
    harness.conversations = [conversation('pane-conversation', '2026-08-11T12:00:00Z')];

    render(<ConversationSplitView />);

    await waitFor(() =>
      expect(screen.getByTestId('conversation-detail')).toBeInTheDocument(),
    );

    const pane = document.querySelector<HTMLElement>(
      '[style*="--conversation-detail-width"]',
    );
    expect(pane).not.toBeNull();
    // An inline `width` outranks every responsive class, which is how the pane
    // came to be 110px wide on a 390px phone with the rest of the row blank.
    expect(pane?.style.width).toBe('');
    expect(pane?.style.getPropertyValue('--conversation-detail-width')).toBe(
      'min(480px, calc(100% - 280px))',
    );
    expect(pane?.className).toContain('lg:w-[var(--conversation-detail-width)]');
  });

  it('keeps the timeline visible until the draft search is submitted', async () => {
    harness.conversations = [
      conversation('timeline-conversation', '2026-08-11T12:00:00Z'),
    ];

    render(<ConversationSplitView />);
    fireEvent.change(screen.getByRole('textbox', { name: 'Search conversations...' }), {
      target: { value: 'draft query' },
    });

    expect(screen.getByTestId('conversation-gallery')).toHaveTextContent(
      'timeline-conversation',
    );
    expect(screen.queryByText('No conversations found')).not.toBeInTheDocument();
    expect(harness.performSearch).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Submit search' }));

    await waitFor(() =>
      expect(harness.performSearch).toHaveBeenCalledWith('draft query'),
    );
    expect(screen.getByText('No conversations found')).toBeInTheDocument();

    fireEvent.change(screen.getByRole('textbox', { name: 'Search conversations...' }), {
      target: { value: '' },
    });

    await waitFor(() =>
      expect(screen.getByTestId('conversation-gallery')).toHaveTextContent(
        'timeline-conversation',
      ),
    );
    expect(harness.clearSearch).toHaveBeenCalledTimes(1);
  });

  it('closes the detail pane on entering selection mode instead of re-selecting the newest tile', async () => {
    harness.conversations = [
      conversation('older-conversation', '2026-08-10T12:00:00Z'),
      conversation('newest-conversation', '2026-08-11T12:00:00Z'),
    ];

    render(<ConversationSplitView />);

    await waitFor(() =>
      expect(screen.getByTestId('conversation-detail')).toHaveTextContent(
        'newest-conversation',
      ),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Select' }));

    expect(screen.queryByTestId('conversation-detail')).not.toBeInTheDocument();
    expect(screen.getByTestId('conversation-gallery')).toBeInTheDocument();
  });
});

describe('ConversationSplitView date presets', () => {
  // Pinned behind UTC so the bounds are checked as local days. CI runs in UTC,
  // where a local day and a UTC day are the same.
  const hostTimezone = process.env.TZ;
  beforeAll(() => {
    process.env.TZ = 'America/Los_Angeles';
  });
  afterAll(() => {
    if (hostTimezone === undefined) delete process.env.TZ;
    else process.env.TZ = hostTimezone;
  });

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    // Monday 19 October 2026, 09:30 in Los Angeles (PDT, UTC-7).
    vi.setSystemTime(new Date('2026-10-19T16:30:00Z'));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function choosePreset(label: string) {
    fireEvent.click(screen.getByRole('button', { name: /All dates/ }));
    fireEvent.click(screen.getByRole('button', { name: label }));
  }

  it('lists all of Last 7 days, not only the day it starts on', () => {
    render(<ConversationSplitView />);
    choosePreset('Last 7 days');

    // Tuesday 13 October 00:00 through Monday 19 October 23:59:59.999, local.
    expect(harness.conversationOptions?.startDate?.toISOString()).toBe(
      '2026-10-13T07:00:00.000Z',
    );
    expect(harness.conversationOptions?.endDate?.toISOString()).toBe(
      '2026-10-20T06:59:59.999Z',
    );
    expect(screen.getByRole('button', { name: /Oct 13 – Oct 19/ })).toBeInTheDocument();
  });

  it('lists This week from Sunday through today', () => {
    render(<ConversationSplitView />);
    choosePreset('This week');

    // Sunday 18 October 00:00 through Monday 19 October 23:59:59.999, local.
    expect(harness.conversationOptions?.startDate?.toISOString()).toBe(
      '2026-10-18T07:00:00.000Z',
    );
    expect(harness.conversationOptions?.endDate?.toISOString()).toBe(
      '2026-10-20T06:59:59.999Z',
    );
  });
});
