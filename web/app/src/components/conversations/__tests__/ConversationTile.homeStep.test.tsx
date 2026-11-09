import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ConversationTile } from '@/components/conversations/ConversationTile';
import type { Conversation } from '@/types/conversation';

vi.mock('@/lib/analytics/posthog', () => ({ PostHogManager: { track: vi.fn() } }));

function conversation(home_step?: string | null): Conversation {
  return {
    id: 'expired',
    created_at: '2026-11-08T10:00:00Z',
    status: 'processing',
    home_step,
    structured: { title: 'Planning', overview: '', emoji: '', category: 'other' },
  } as Conversation;
}

describe('ConversationTile Home projection', () => {
  it('does not badge a failed projection as Processing', () => {
    render(<ConversationTile conversation={conversation('failed')} />);
    expect(screen.getByText('Planning')).toBeInTheDocument();
    expect(screen.queryByText('Processing')).not.toBeInTheDocument();
  });

  it.each([undefined, null, 'processing'])(
    'retains the Processing badge for home_step=%s',
    (homeStep) => {
      render(<ConversationTile conversation={conversation(homeStep)} />);
      expect(screen.getByText('Processing')).toBeInTheDocument();
    },
  );
});
