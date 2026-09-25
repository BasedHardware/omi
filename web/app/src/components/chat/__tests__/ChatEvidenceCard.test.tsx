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

  it('renders screen, keyframe, and request as inert supplemental status cards', () => {
    const envelope = parseChatEvidenceEnvelope({
      references: [
        {
          id: 'screen',
          kind: 'screen',
          state: 'available',
          frame_id: 'frame-1',
        },
        {
          id: 'keyframe',
          kind: 'keyframe',
          state: 'offline',
          frame_id: 'frame-2',
        },
        {
          id: 'request',
          kind: 'request',
          state: 'pruned',
          request_id: 'request-1',
        },
        {
          id: 'request-failed',
          kind: 'request',
          state: 'failed',
          request_id: 'request-2',
        },
        {
          id: 'request-loading',
          kind: 'request',
          state: 'loading',
          request_id: 'request-3',
        },
        {
          id: 'request-unknown',
          kind: 'request',
          state: 'future-state',
          request_id: 'request-4',
        },
      ],
    });

    render(<ChatEvidenceCard envelope={envelope} />);

    for (const label of ['Screen', 'Keyframe', 'Request']) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
    for (const label of [
      'Available',
      'Loading',
      'Unavailable offline',
      'No longer available',
      'Failed to load',
      'Unavailable',
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.queryAllByRole('link')).toHaveLength(0);
  });

  it('fails closed for future schema evidence without rendering cards', () => {
    const envelope = parseChatEvidenceEnvelope({
      schema_version: 2,
      references: [
        {
          id: 'screen',
          kind: 'screen',
          state: 'available',
          frame_id: 'frame-1',
        },
      ],
    });

    render(<ChatEvidenceCard envelope={envelope} />);

    expect(
      screen.queryByRole('region', { name: 'Supporting evidence' }),
    ).not.toBeInTheDocument();
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
