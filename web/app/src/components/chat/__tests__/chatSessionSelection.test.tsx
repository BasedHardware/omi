import { act, render, waitFor } from '@testing-library/react';
import { useEffect } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({
  getMessages: vi.fn().mockResolvedValue([]),
  sendMessageStream: vi.fn().mockResolvedValue(undefined),
  clearMessages: vi.fn().mockResolvedValue(undefined),
  uploadChatFiles: vi.fn().mockResolvedValue([]),
  getChatApps: vi.fn().mockResolvedValue([]),
}));
vi.mock('@/lib/analytics/mixpanel', () => ({ MixpanelManager: {} }));

const { getMessages } = await import('@/lib/api');
const { ChatProvider, useChat: useChatContext } =
  await import('@/components/chat/ChatContext');
const { ChatPanel } = await import('@/components/chat/ChatPanel');

function OpenWithSession({ sessionId }: { sessionId: string | null }) {
  const { openChat, selectChatSession } = useChatContext();
  useEffect(() => {
    selectChatSession(sessionId);
    openChat();
  }, [openChat, selectChatSession, sessionId]);
  return null;
}

beforeEach(() => {
  vi.clearAllMocks();
  // jsdom has no layout, so the panel's scroll-to-bottom effect needs a stub.
  Element.prototype.scrollIntoView = vi.fn();
});

describe('chat session selection', () => {
  it('reads the transcript of the session the reader selected', async () => {
    await act(async () => {
      render(
        <ChatProvider>
          <OpenWithSession sessionId="sess-9" />
          <ChatPanel />
        </ChatProvider>,
      );
    });

    await waitFor(() => expect(getMessages).toHaveBeenCalled());
    expect(getMessages).toHaveBeenCalledWith(undefined, 'sess-9');
  });

  it('stays on the shared thread when nothing is selected', async () => {
    await act(async () => {
      render(
        <ChatProvider>
          <OpenWithSession sessionId={null} />
          <ChatPanel />
        </ChatProvider>,
      );
    });

    await waitFor(() => expect(getMessages).toHaveBeenCalled());
    expect(getMessages).toHaveBeenCalledWith(undefined, null);
  });

  it('loads history after switching from an already loaded session', async () => {
    const view = render(
      <ChatProvider>
        <OpenWithSession sessionId="sess-a" />
        <ChatPanel />
      </ChatProvider>,
    );

    await waitFor(() => expect(getMessages).toHaveBeenCalledWith(undefined, 'sess-a'));
    vi.mocked(getMessages).mockClear();

    view.rerender(
      <ChatProvider>
        <OpenWithSession sessionId="sess-b" />
        <ChatPanel />
      </ChatProvider>,
    );

    await waitFor(() => expect(getMessages).toHaveBeenCalledWith(undefined, 'sess-b'));
  });
});
