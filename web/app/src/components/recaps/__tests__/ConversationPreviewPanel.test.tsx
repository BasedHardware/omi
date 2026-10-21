import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ConversationPreviewPanel } from '@/components/recaps/ConversationPreviewPanel';
import type { Conversation } from '@/types/conversation';

const harness = vi.hoisted(() => ({
  getConversation: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  getConversation: harness.getConversation,
}));

vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: {
    div: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    button: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  },
}));

function conversation(overrides: Partial<Conversation>): Conversation {
  return {
    id: 'conversation-1',
    created_at: '2026-09-17T00:00:00.000Z',
    started_at: '2026-09-17T00:00:00.000Z',
    finished_at: null,
    structured: {
      title: 'Meeting',
      emoji: '💬',
      overview: 'Legacy overview',
      sections: [],
    },
    apps_results: [],
    ...overrides,
  } as Conversation;
}

describe('ConversationPreviewPanel summary selection', () => {
  beforeEach(() => {
    harness.getConversation.mockReset();
  });

  it('shows the selected app result instead of repeating the overview', async () => {
    harness.getConversation.mockResolvedValue(
      conversation({
        apps_results: [{ app_id: 'app-1', content: 'App summary' }],
      }),
    );

    render(
      <ConversationPreviewPanel
        conversationIds={['conversation-1']}
        isOpen
        onClose={vi.fn()}
        onOpenFull={vi.fn()}
      />,
    );

    expect(await screen.findByText('App summary')).toBeInTheDocument();
    expect(screen.queryByText('Legacy overview')).not.toBeInTheDocument();
  });

  it('shows the deterministic sections projection when overview is absent', async () => {
    harness.getConversation.mockResolvedValue(
      conversation({
        structured: {
          title: 'Meeting',
          emoji: '💬',
          overview: '',
          sections: [{ heading: 'Decisions', body_markdown: 'Section body' }],
        },
      }),
    );

    render(
      <ConversationPreviewPanel
        conversationIds={['conversation-1']}
        isOpen
        onClose={vi.fn()}
        onOpenFull={vi.fn()}
      />,
    );

    expect(await screen.findByText(/Section body/)).toBeInTheDocument();
    expect(screen.queryByText('Legacy overview')).not.toBeInTheDocument();
  });
});
