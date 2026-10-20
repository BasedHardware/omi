import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatPanel } from '@/components/chat/ChatPanel';
import type { ClientMessage } from '@/types/conversation';

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('@tschk/moonshine-next/navigation', () => ({ useRouter: () => ({ push }) }));

const loadHistory = vi.fn(async () => undefined);
const defaultEvidenceMessage: ClientMessage = {
  id: 'ai-evidence',
  sender: 'ai',
  text: 'The panel answer remains authoritative.',
  type: 'text',
  created_at: '2026-08-23T12:00:00Z',
  evidence: {
    schema_version: 1,
    references: [
      {
        id: 'summary-1',
        kind: 'conversation_summary',
        state: 'available',
        title: 'Panel supporting conversation',
        conversation_id: 'conversation-1',
      },
    ],
  },
};
let mockMessages: ClientMessage[] = [defaultEvidenceMessage];

vi.mock('@/components/chat/ChatContext', () => ({
  useChat: () => ({
    isOpen: true,
    closeChat: vi.fn(),
    currentContext: undefined,
    selectedAppId: null,
    clearAppContext: vi.fn(),
    chat: {
      messages: mockMessages,
      isLoading: false,
      isStreaming: false,
      streamingText: '',
      currentThinking: '',
      error: null,
      sendMessage: vi.fn(async () => undefined),
      clearHistory: vi.fn(async () => undefined),
      loadHistory,
    },
  }),
}));

vi.mock('@/lib/api', () => ({
  uploadChatFiles: vi.fn(async () => []),
  getChatApps: vi.fn(async () => []),
}));

vi.mock('@/lib/analytics/posthog', () => ({
  PostHogManager: { track: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
  mockMessages = [defaultEvidenceMessage];
  Element.prototype.scrollIntoView = vi.fn();
});

describe('ChatPanel evidence', () => {
  it('renders supported evidence after the authoritative panel answer', () => {
    render(<ChatPanel />);

    const answer = screen.getByText('The panel answer remains authoritative.');
    const evidence = screen.getByText('Panel supporting conversation');
    expect(
      answer.compareDocumentPosition(evidence) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      screen.getByRole('region', { name: 'Supporting evidence' }),
    ).toBeInTheDocument();
  });

  it('renders clickable citation source cards when the server strips inline markers into memories', () => {
    mockMessages = [
      {
        id: 'ai-citations',
        sender: 'ai',
        text: 'I can name them.',
        type: 'text',
        created_at: '2026-10-12T07:58:37Z',
        memories: [
          {
            id: 'conversation/1',
            created_at: '2026-10-12T00:00:00Z',
            structured: { title: 'Conversation 1', emoji: '📝' },
          },
          {
            id: 'conversation-2',
            created_at: '2026-10-12T00:00:00Z',
            structured: { title: 'Conversation 2', emoji: '🧠' },
          },
        ],
      },
    ];

    render(<ChatPanel />);

    const answer = screen.getByText('I can name them.');
    const sourcesRegion = screen.getByRole('region', { name: 'Sources' });
    expect(
      answer.compareDocumentPosition(sourcesRegion) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    const links = screen.getAllByRole('link');
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/conversations?id=conversation%2F1',
      '/conversations?id=conversation-2',
    ]);
    fireEvent.click(links[1]);
    expect(push).toHaveBeenCalledWith('/conversations?id=conversation-2');
  });
});
