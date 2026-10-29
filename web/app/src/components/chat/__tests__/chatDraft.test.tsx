import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { chatDraftKeys, readChatDraft } from '@/components/chat/chatDraft';
import type { ClientMessage } from '@/types/conversation';

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('@tschk/moonshine-next/navigation', () => ({ useRouter: () => ({ push }) }));

const sendMessage = vi.fn(async () => true);
const loadHistory = vi.fn(async () => undefined);
const mockMessages: ClientMessage[] = [];

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
      sendMessage,
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
  localStorage.clear();
  Element.prototype.scrollIntoView = vi.fn();
});

function typeDraft(text: string) {
  fireEvent.change(screen.getByPlaceholderText('Ask anything...'), {
    target: { value: text },
  });
}

describe('chat draft persistence', () => {
  it('restores a persisted draft when the panel opens', () => {
    localStorage.setItem(chatDraftKeys.panel, 'half-written question');
    render(<ChatPanel />);

    expect(screen.getByPlaceholderText('Ask anything...')).toHaveValue(
      'half-written question',
    );
  });

  it('persists the draft as it is typed and clears it on an accepted send', async () => {
    render(<ChatPanel />);
    typeDraft('delivered message');
    expect(readChatDraft(chatDraftKeys.panel)).toBe('delivered message');

    fireEvent.click(screen.getByRole('button', { name: /send/i }));

    await waitFor(() =>
      expect(sendMessage).toHaveBeenCalledWith('delivered message', [], undefined),
    );
    await waitFor(() => expect(readChatDraft(chatDraftKeys.panel)).toBe(''));
  });

  it('keeps the draft restorable when the send fails', async () => {
    sendMessage.mockResolvedValueOnce(false);
    render(<ChatPanel />);
    typeDraft('please keep this');
    fireEvent.click(screen.getByRole('button', { name: /send/i }));

    await waitFor(() => expect(sendMessage).toHaveBeenCalled());
    await waitFor(() =>
      expect(readChatDraft(chatDraftKeys.panel)).toBe('please keep this'),
    );
  });

  it('never clobbers a newer draft typed while a send is running', async () => {
    let resolveSend: (accepted: boolean) => void = () => {};
    sendMessage.mockReturnValueOnce(
      new Promise<boolean>((resolve) => {
        resolveSend = resolve;
      }),
    );
    render(<ChatPanel />);
    typeDraft('first message');
    fireEvent.click(screen.getByRole('button', { name: /send/i }));

    // The user starts a second draft while the first send is still running.
    typeDraft('second draft');
    expect(readChatDraft(chatDraftKeys.panel)).toBe('second draft');

    resolveSend(true);
    await waitFor(() => expect(sendMessage).toHaveBeenCalled());
    // The accepted first send must not erase the newer draft.
    await waitFor(() => expect(readChatDraft(chatDraftKeys.panel)).toBe('second draft'));
  });
});
