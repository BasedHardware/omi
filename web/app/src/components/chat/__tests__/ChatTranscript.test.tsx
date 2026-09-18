import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatTranscript } from '@/components/chat/ChatTranscript';
import type { ClientMessage } from '@/types/conversation';

vi.mock('@tschk/moonshine-next/image', () => ({
  default: ({ alt }: React.ComponentProps<'img'>) => <img alt={alt} />,
}));
vi.mock('@/components/chat/ChatMarkdown', () => ({
  ChatMarkdown: ({ children }: { children: string }) => <div>{children}</div>,
}));

function message(id: string, text: string): ClientMessage {
  return {
    id,
    sender: 'ai',
    text,
    created_at: '2026-08-11T00:00:00Z',
    type: 'text',
    from_external_integration: false,
    files: [],
    memories: [],
    ask_for_nps: false,
  };
}

function Scroller({
  children,
  scrollTop,
}: {
  children: React.ReactNode;
  scrollTop: number;
}) {
  return (
    <div
      data-testid="scroller"
      style={{ overflowY: 'auto', height: 800 }}
      ref={(node) => {
        if (!node) return;
        Object.defineProperty(node, 'scrollHeight', { value: 2000, configurable: true });
        Object.defineProperty(node, 'clientHeight', { value: 800, configurable: true });
        node.scrollTop = scrollTop;
      }}
    >
      {children}
    </div>
  );
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

describe('ChatTranscript live-edge following', () => {
  it('places a new exchange even when the scroller is not yet at the bottom', () => {
    render(
      <Scroller scrollTop={100}>
        <ChatTranscript
          messages={[message('ai-1', 'Hello')]}
          isLoading={false}
          isStreaming={false}
          streamingText=""
          currentThinking=""
        />
      </Scroller>,
    );

    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it('does not follow a stream once the reader has left the live edge', () => {
    const { rerender } = render(
      <Scroller scrollTop={100}>
        <ChatTranscript
          messages={[message('ai-1', 'Hello')]}
          isLoading={false}
          isStreaming
          streamingText=""
          currentThinking=""
        />
      </Scroller>,
    );

    const scrollIntoView = Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>;
    scrollIntoView.mockClear();

    rerender(
      <Scroller scrollTop={100}>
        <ChatTranscript
          messages={[message('ai-1', 'Hello')]}
          isLoading={false}
          isStreaming
          streamingText="Hello there"
          currentThinking=""
        />
      </Scroller>,
    );

    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it('keeps following while the scroller stays pinned to the live edge', () => {
    const { rerender } = render(
      <Scroller scrollTop={1200}>
        <ChatTranscript
          messages={[message('ai-1', 'Hello')]}
          isLoading={false}
          isStreaming
          streamingText=""
          currentThinking=""
        />
      </Scroller>,
    );

    const scrollIntoView = Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>;
    scrollIntoView.mockClear();

    rerender(
      <Scroller scrollTop={1200}>
        <ChatTranscript
          messages={[message('ai-1', 'Hello')]}
          isLoading={false}
          isStreaming
          streamingText="Hello there"
          currentThinking=""
        />
      </Scroller>,
    );

    expect(scrollIntoView).toHaveBeenCalled();
  });
});
