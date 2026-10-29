import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatPanel } from '@/components/chat/ChatPanel';
import {
  chatDraftKeys,
  clearChatDraft,
  decryptChatDraft,
  encryptChatDraft,
  readChatDraft,
  setChatDraftOwner,
  writeChatDraft,
} from '@/components/chat/chatDraft';
import type { ClientMessage } from '@/types/conversation';

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('@tschk/moonshine-next/navigation', () => ({ useRouter: () => ({ push }) }));

const sendMessage = vi.fn(async () => true);
const loadHistory = vi.fn(async () => undefined);
const mockMessages: ClientMessage[] = [];
let panelOpen = true;

vi.mock('@/components/chat/ChatContext', () => ({
  useChat: () => ({
    isOpen: panelOpen,
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
  setChatDraftOwner(null);
  clearChatDraft(chatDraftKeys.panel);
  clearChatDraft(chatDraftKeys.home);
  panelOpen = true;
  Element.prototype.scrollIntoView = vi.fn();
});

function typeDraft(text: string) {
  fireEvent.change(screen.getByPlaceholderText('Ask anything...'), {
    target: { value: text },
  });
}

describe('chat draft persistence', () => {
  it('uses the current-tab draft when the panel opens', () => {
    void writeChatDraft(chatDraftKeys.panel, 'half-written question');
    render(<ChatPanel />);

    expect(screen.getByPlaceholderText('Ask anything...')).toHaveValue(
      'half-written question',
    );
  });

  it('persists the draft as it is typed and clears it on an accepted send', async () => {
    render(<ChatPanel />);
    typeDraft('delivered message');
    await waitFor(() =>
      expect(readChatDraft(chatDraftKeys.panel)).toBe('delivered message'),
    );

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
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));

    // The user starts a second draft while the first send is still running.
    typeDraft('second draft');
    await waitFor(() => expect(readChatDraft(chatDraftKeys.panel)).toBe('second draft'));

    resolveSend(true);
    await waitFor(() => expect(sendMessage).toHaveBeenCalled());
    // The accepted first send must not erase the newer draft.
    await waitFor(() => expect(readChatDraft(chatDraftKeys.panel)).toBe('second draft'));
  });

  it('restores a failed send draft when the panel reopens without a refresh', async () => {
    sendMessage.mockResolvedValueOnce(false);
    panelOpen = true;
    const { rerender } = render(<ChatPanel />);
    typeDraft('reopen me');
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));

    await waitFor(() => expect(sendMessage).toHaveBeenCalled());
    await waitFor(() => expect(readChatDraft(chatDraftKeys.panel)).toBe('reopen me'));
    // The composer is empty after the failed send; the panel closes and opens
    // again without unmounting.
    await act(async () => {
      panelOpen = false;
      rerender(<ChatPanel />);
    });
    await act(async () => {
      panelOpen = true;
      rerender(<ChatPanel />);
    });

    await waitFor(() =>
      expect(screen.getByPlaceholderText('Ask anything...')).toHaveValue('reopen me'),
    );
  });

  it('never restores one account draft into another account composer', () => {
    setChatDraftOwner('uid-a');
    writeChatDraft(chatDraftKeys.panel, 'account a prompt');
    expect(readChatDraft(chatDraftKeys.panel)).toBe('account a prompt');

    // Account B signs in on the same browser: A's drafts are cleared, and the
    // panel restores nothing.
    setChatDraftOwner('uid-b');
    expect(readChatDraft(chatDraftKeys.panel)).toBe('');
    expect(localStorage.getItem(chatDraftKeys.panel)).toBeNull();
    expect(localStorage.getItem(`${chatDraftKeys.panel}:uid-a`)).toBeNull();
  });

  it('a send that outlives its account writes nothing under the new owner', async () => {
    setChatDraftOwner('uid-a');
    let resolveSend: (accepted: boolean) => void = () => {};
    sendMessage.mockReturnValueOnce(
      new Promise<boolean>((resolve) => {
        resolveSend = resolve;
      }),
    );
    render(<ChatPanel />);
    typeDraft('account a unsent');
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));

    // The account switches while the send is still running; the switch clears
    // A's drafts and rescopes the keys.
    setChatDraftOwner('uid-b');

    resolveSend(false);
    await waitFor(() => expect(sendMessage).toHaveBeenCalled());
    expect(readChatDraft(chatDraftKeys.panel)).toBe('');
    expect(localStorage.getItem(`${chatDraftKeys.panel}:uid-b`)).toBeNull();
    expect(localStorage.getItem(`${chatDraftKeys.panel}:uid-a`)).toBeNull();
  });
});

describe('encrypted chat draft storage', () => {
  it('stores an authenticated ciphertext envelope instead of the draft text', async () => {
    const key = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, [
      'encrypt',
      'decrypt',
    ]);
    const draft = 'my private unsent question';
    const envelope = await encryptChatDraft(draft, key, `${chatDraftKeys.panel}:uid-a`);

    expect(envelope).toMatch(/^v1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/);
    expect(envelope).not.toContain(draft);
    await expect(
      decryptChatDraft(envelope, key, `${chatDraftKeys.panel}:uid-a`),
    ).resolves.toBe(draft);
    await expect(
      decryptChatDraft(envelope, key, `${chatDraftKeys.panel}:uid-b`),
    ).rejects.toThrow();
  });

  it('rejects modified ciphertext', async () => {
    const key = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, [
      'encrypt',
      'decrypt',
    ]);
    const envelope = await encryptChatDraft('draft text', key, chatDraftKeys.panel);
    const [version, iv, ciphertext] = envelope.split('.');
    const altered = `${version}.${iv}.${ciphertext.slice(0, -1)}${
      ciphertext.endsWith('A') ? 'B' : 'A'
    }`;

    await expect(decryptChatDraft(altered, key, chatDraftKeys.panel)).rejects.toThrow();
  });
});
