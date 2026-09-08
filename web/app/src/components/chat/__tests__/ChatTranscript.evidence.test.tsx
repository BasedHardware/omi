import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { ChatTranscript } from '@/components/chat/ChatTranscript';
import type { ClientMessage } from '@/types/conversation';

function aiMessage(evidence?: ClientMessage['evidence']): ClientMessage {
  return {
    id: 'message-1',
    created_at: '2026-08-23T12:00:00Z',
    sender: 'ai',
    text: 'The answer remains authoritative.',
    type: 'text',
    evidence,
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
});
