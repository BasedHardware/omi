import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatPanel } from '@/components/chat/ChatPanel';

const loadHistory = vi.fn(async () => undefined);

vi.mock('@/components/chat/ChatContext', () => ({
  useChat: () => ({
    isOpen: true,
    closeChat: vi.fn(),
    currentContext: undefined,
    selectedAppId: null,
    clearAppContext: vi.fn(),
    chat: {
      messages: [
        {
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
        },
      ],
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

vi.mock('@/lib/analytics/mixpanel', () => ({
  MixpanelManager: { track: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
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
});
