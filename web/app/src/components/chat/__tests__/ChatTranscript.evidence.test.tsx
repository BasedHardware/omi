import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatTranscript } from '@/components/chat/ChatTranscript';
import type { ClientMessage } from '@/types/conversation';

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('@tschk/moonshine-next/navigation', () => ({ useRouter: () => ({ push }) }));

function aiMessage(
  evidence?: ClientMessage['evidence'],
  memories?: ClientMessage['memories'],
  text = 'The answer remains authoritative.',
): ClientMessage {
  return {
    id: 'message-1',
    created_at: '2026-08-23T12:00:00Z',
    sender: 'ai',
    text,
    type: 'text',
    evidence,
    memories,
  };
}

function renderTranscript(messages: ClientMessage[]) {
  return render(
    <ChatTranscript
      messages={messages}
      isLoading={false}
      isStreaming={false}
      streamingText=""
      currentThinking=""
      autoScroll={false}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  Element.prototype.scrollIntoView = () => undefined;
});

describe('ChatTranscript evidence', () => {
  it('keeps answer text authoritative and renders admitted conversation evidence after it', () => {
    renderTranscript([
      aiMessage({
        schema_version: 1,
        references: [
          {
            id: 'summary-1',
            kind: 'conversation_summary',
            state: 'available',
            title: 'Supporting conversation',
            summary: 'This is supplemental context.',
            conversation_id: 'conversation-1',
          },
        ],
      }),
    ]);

    expect(screen.getByText('The answer remains authoritative.')).toBeInTheDocument();
    expect(screen.getByText('Supporting conversation')).toBeInTheDocument();
    expect(
      screen.getByRole('region', { name: 'Supporting evidence' }),
    ).toBeInTheDocument();
  });

  it('keeps unsupported and future evidence inert while still rendering the answer', () => {
    renderTranscript([
      aiMessage({
        schema_version: 99,
        references: [
          {
            id: 'screen-1',
            kind: 'screen',
            state: 'available',
            frame_id: 'frame-1',
            title: 'Current screen',
          },
        ],
      }),
    ]);

    expect(screen.getByText('The answer remains authoritative.')).toBeInTheDocument();
    expect(
      screen.queryByRole('region', { name: 'Supporting evidence' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText('Current screen')).not.toBeInTheDocument();
  });

  it('renders clickable citation source cards in first-mention order when prose markers were stripped by the server', () => {
    renderTranscript([
      aiMessage(
        undefined,
        [
          {
            id: 'conversation-8',
            created_at: '2026-10-12T00:00:00Z',
            structured: { title: 'Board resolutions', emoji: '📝' },
          },
          {
            id: 'conversation-7',
            created_at: '2026-10-12T00:00:00Z',
            structured: { title: 'Dinner plans', emoji: '🍽️' },
          },
        ],
        'I can name them.',
      ),
    ]);

    const answer = screen.getByText('I can name them.');
    const sourcesRegion = screen.getByRole('region', { name: 'Sources' });
    expect(
      answer.compareDocumentPosition(sourcesRegion) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    const links = screen.getAllByRole('link');
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/conversations?id=conversation-8',
      '/conversations?id=conversation-7',
    ]);
    expect(screen.getByTestId('chat-citation-conversation-8')).toHaveTextContent(
      'Board resolutions',
    );
    expect(screen.getByTestId('chat-citation-conversation-7')).toHaveTextContent(
      'Dinner plans',
    );

    fireEvent.click(links[0]);
    expect(push).toHaveBeenCalledWith('/conversations?id=conversation-8');
  });
});
