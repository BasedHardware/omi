import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createEvent, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatCitationCards } from '@/components/chat/ChatCitationCards';
import { ChatTranscript } from '@/components/chat/ChatTranscript';
import { parseStreamLine } from '@/lib/api';
import { normalizeChatCitations } from '@/lib/chatCitationLinks';

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('@tschk/moonshine-next/navigation', () => ({ useRouter: () => ({ push }) }));

beforeEach(() => {
  vi.clearAllMocks();
  Element.prototype.scrollIntoView = () => undefined;
});

describe('normalizeChatCitations', () => {
  it('repairs legacy citation debris in card titles and keeps ordinary brackets', () => {
    expect(
      normalizeChatCitations([
        { id: 'a', structured: { title: 'Speaker_00 kickoff [s01234]', emoji: '📝' } },
        { id: 'b', structured: { title: 'Project [Q3]', emoji: '📝' } },
        { id: 'c', structured: { title: '[s01234]', emoji: '📝' } },
      ]).map((source) => source.title),
    ).toEqual(['kickoff', 'Project [Q3]', 'Untitled conversation']);
  });

  it('preserves server first-mention order, deduplicates ids, and fills defaults', () => {
    expect(
      normalizeChatCitations([
        {
          id: '  conversation/8  ',
          structured: { title: '  Board resolutions  ', emoji: '📝' },
        },
        {
          id: 'conversation-7',
          structured: { title: '', emoji: '' },
        },
        {
          id: 'conversation/8',
          structured: { title: 'Duplicate', emoji: '🔁' },
        },
        {
          id: '   ',
          structured: { title: 'Blank id', emoji: '📝' },
        },
        null,
      ]),
    ).toEqual([
      {
        id: 'conversation/8',
        title: 'Board resolutions',
        emoji: '📝',
        href: '/conversations?id=conversation%2F8',
      },
      {
        id: 'conversation-7',
        title: 'Untitled conversation',
        emoji: '📝',
        href: '/conversations?id=conversation-7',
      },
    ]);
  });

  it('returns an empty list for absent or non-array inputs', () => {
    expect(normalizeChatCitations(undefined)).toEqual([]);
    expect(normalizeChatCitations(null)).toEqual([]);
  });
});

describe('ChatCitationCards', () => {
  it('renders nothing when a message has no resolved citation memories', () => {
    const { container, rerender } = render(<ChatCitationCards memories={[]} />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole('region', { name: 'Sources' })).not.toBeInTheDocument();

    rerender(<ChatCitationCards memories={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders clickable conversation source cards and navigates on plain click', () => {
    render(
      <ChatCitationCards
        memories={[
          {
            id: 'conversation-1',
            created_at: '2026-10-12T00:00:00Z',
            structured: { title: 'Conversation 1', emoji: '📝' },
          },
          {
            id: 'conversation-2',
            created_at: '2026-10-12T00:00:00Z',
            structured: { title: 'Conversation 2', emoji: '🚀' },
          },
        ]}
      />,
    );

    expect(screen.getByRole('region', { name: 'Sources' })).toBeInTheDocument();
    expect(screen.getByTestId('chat-citation-list')).toBeInTheDocument();

    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute('href', '/conversations?id=conversation-1');
    expect(links[1]).toHaveAttribute('href', '/conversations?id=conversation-2');

    // Modifier clicks preserve default browser new-tab behavior.
    const metaClick = createEvent.click(links[0], { metaKey: true });
    const preventDefaultSpy = vi.spyOn(metaClick, 'preventDefault');
    metaClick.preventDefault();
    preventDefaultSpy.mockClear();
    fireEvent(links[0], metaClick);
    expect(preventDefaultSpy).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();

    fireEvent.click(links[0]);
    expect(push).toHaveBeenCalledWith('/conversations?id=conversation-1');
  });

  it('renders the tracked backend /v2/messages SSE citation fixture as working links', () => {
    const fixturePath = resolve(
      process.cwd(),
      '../../backend/tests/fixtures/chat_app_citations_pre_21240.sse.json',
    );
    const rawSse = JSON.parse(readFileSync(fixturePath, 'utf-8')) as string;
    const chunks = rawSse
      .split('\n')
      .map((line) => parseStreamLine(line))
      .filter((chunk) => chunk !== null);

    const doneChunk = chunks.find((chunk) => chunk.type === 'done');
    expect(doneChunk?.message).toBeDefined();
    expect(doneChunk?.message?.text).toBe('I can name them.');

    render(
      <ChatTranscript
        messages={[doneChunk!.message!]}
        isLoading={false}
        isStreaming={false}
        streamingText=""
        currentThinking=""
        autoScroll={false}
      />,
    );

    expect(screen.getByText('I can name them.')).toBeInTheDocument();
    const links = screen.getAllByRole('link');
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/conversations?id=conversation-1',
      '/conversations?id=conversation-2',
      '/conversations?id=conversation-4',
      '/conversations?id=conversation-6',
      '/conversations?id=conversation-7',
    ]);

    fireEvent.click(links[2]);
    expect(push).toHaveBeenCalledWith('/conversations?id=conversation-4');
  });
});
