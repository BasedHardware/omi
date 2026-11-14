import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ConversationTile } from '@/components/conversations/ConversationTile';
import { reprocessConversation } from '@/lib/api';
import type { Conversation } from '@/types/conversation';

vi.mock('@/lib/analytics/posthog', () => ({ PostHogManager: { track: vi.fn() } }));
vi.mock('@/lib/api', () => ({ reprocessConversation: vi.fn() }));
beforeEach(() => vi.mocked(reprocessConversation).mockReset());

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
  it('keeps a status-only failed Activity row retryable', () => {
    render(
      <ConversationTile
        showFailedStatus
        conversation={{ ...conversation(), status: 'failed' }}
      />,
    );
    expect(screen.getByRole('button', { name: 'Retry' })).toBeEnabled();
    expect(screen.queryByText('Processing')).not.toBeInTheDocument();
  });

  it('retains the previous status-only Home tile when placement is off', () => {
    render(<ConversationTile conversation={{ ...conversation(), status: 'failed' }} />);
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
  });

  it('labels a failed projection and keeps it openable without Processing', () => {
    const open = vi.fn();
    render(<ConversationTile conversation={conversation('failed')} onClick={open} />);
    fireEvent.click(screen.getByRole('button', { name: 'Conversation: Planning' }));
    expect(open).toHaveBeenCalledOnce();
    expect(
      screen.getByRole('heading', { name: "Omi couldn't finish" }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(screen.queryByText('Processing')).not.toBeInTheDocument();
  });

  it.each([undefined, null, 'processing'])(
    'retains the Processing badge for home_step=%s',
    (homeStep) => {
      render(<ConversationTile conversation={conversation(homeStep)} />);
      expect(screen.getByText('Processing')).toBeInTheDocument();
      expect(screen.getByText('Planning')).toBeInTheDocument();
      expect(screen.queryByText("Omi couldn't finish")).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
    },
  );

  it('retries once through the existing API and passes on its authoritative result', async () => {
    let resolve!: (result: Conversation) => void;
    vi.mocked(reprocessConversation).mockReturnValue(
      new Promise((result) => {
        resolve = result;
      }),
    );
    const updated = { ...conversation(), status: 'completed' } as Conversation;
    const onUpdate = vi.fn();
    const open = vi.fn();
    const { rerender } = render(
      <ConversationTile
        conversation={conversation('failed')}
        onClick={open}
        onConversationUpdate={onUpdate}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    fireEvent.click(screen.getByRole('button', { name: 'Retrying…' }));
    expect(reprocessConversation).toHaveBeenCalledExactlyOnceWith('expired');
    expect(open).not.toHaveBeenCalled();
    expect(screen.queryByText('Processing')).not.toBeInTheDocument();
    resolve(updated);
    await waitFor(() => expect(onUpdate).toHaveBeenCalledExactlyOnceWith(updated));
    rerender(<ConversationTile conversation={updated} />);
    expect(screen.queryByText("Omi couldn't finish")).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
  });

  it('keeps a failed row reachable and retryable when reprocessing fails', async () => {
    vi.mocked(reprocessConversation).mockRejectedValueOnce(new Error('Unavailable'));
    const open = vi.fn();
    render(<ConversationTile conversation={conversation('failed')} onClick={open} />);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Retry failed. Please try again.',
    );
    expect(screen.getByRole('button', { name: 'Retry' })).toBeEnabled();
    expect(screen.getByText("Omi couldn't finish")).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Conversation: Planning' }));
    expect(open).toHaveBeenCalledOnce();
  });
});
