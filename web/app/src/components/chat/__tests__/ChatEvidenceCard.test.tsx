import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ChatEvidenceCard } from '@/components/chat/ChatEvidenceCard';
import { parseChatEvidenceEnvelope } from '@/lib/chatEvidence';

describe('ChatEvidenceCard', () => {
  it('renders supplemental status for every supported state without actions', () => {
    const envelope = parseChatEvidenceEnvelope({
      references: [
        {
          id: 'available',
          kind: 'conversation_summary',
          state: 'available',
          title: 'Recent conversation',
          summary: 'A bounded summary shown below the answer.',
          conversation_id: 'conversation-1',
        },
        {
          id: 'loading',
          kind: 'conversation_segment',
          state: 'loading',
          conversation_id: 'conversation-1',
          segment_id: 'segment-1',
        },
        {
          id: 'offline',
          kind: 'conversation_summary',
          state: 'offline',
          conversation_id: 'conversation-1',
        },
        {
          id: 'pruned',
          kind: 'conversation_summary',
          state: 'pruned',
          conversation_id: 'conversation-1',
        },
        {
          id: 'failed',
          kind: 'conversation_summary',
          state: 'failed',
          conversation_id: 'conversation-1',
          error_message: 'The source was unavailable.',
        },
      ],
    });

    render(<ChatEvidenceCard envelope={envelope} />);

    expect(
      screen.getByRole('region', { name: 'Supporting evidence' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Recent conversation')).toBeInTheDocument();
    expect(
      screen.getByText('A bounded summary shown below the answer.'),
    ).toBeInTheDocument();
    for (const label of [
      'Available',
      'Loading',
      'Unavailable offline',
      'No longer available',
      'Failed to load',
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.queryByText('The source was unavailable.')).not.toBeInTheDocument();
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.queryAllByRole('link')).toHaveLength(0);
  });

  it('renders nothing for an empty or unsupported envelope', () => {
    const { rerender } = render(
      <ChatEvidenceCard envelope={{ schemaVersion: 1, references: [] }} />,
    );
    expect(
      screen.queryByRole('region', { name: 'Supporting evidence' }),
    ).not.toBeInTheDocument();

    rerender(<ChatEvidenceCard envelope={null} />);
    expect(
      screen.queryByRole('region', { name: 'Supporting evidence' }),
    ).not.toBeInTheDocument();
  });
});
