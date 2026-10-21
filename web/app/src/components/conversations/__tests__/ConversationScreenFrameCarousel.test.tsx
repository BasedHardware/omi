import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ConversationScreenFrameCarousel } from '@/components/conversations/ConversationScreenFrameCarousel';
import type { ConversationScreenFrame } from '@/types/conversation';

vi.mock('@tschk/moonshine-next/image', () => ({
  default: (props: Record<string, unknown>) => {
    const { fill: _fill, ...rest } = props;
    // eslint-disable-next-line @next/next/no-img-element
    return <img {...rest} />;
  },
}));

function frame(id: string, caption = `caption-${id}`): ConversationScreenFrame {
  return {
    id,
    captured_at: '2026-08-24T10:00:00Z',
    role: 'strip',
    rank: 0,
    caption,
    labels: [],
    source_badge: null,
    focal_region: null,
    width: 1600,
    height: 900,
    content_url: `https://example.com/${id}.jpg`,
    thumbnail_url: `https://example.com/${id}_thumb.jpg`,
    url_expires_at: '2026-08-24T11:00:00Z',
    ground: { stops: ['#101010', '#202020'], is_neutral: false },
  };
}

describe('ConversationScreenFrameCarousel', () => {
  it('renders nothing when there are no frames', () => {
    const { container } = render(
      <ConversationScreenFrameCarousel
        frames={[]}
        onFrameClick={vi.fn()}
        onRequestDeleteFrame={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('opens the lightbox at the clicked thumbnail index, not the deleted frame', () => {
    const onFrameClick = vi.fn();
    render(
      <ConversationScreenFrameCarousel
        frames={[frame('a'), frame('b'), frame('c')]}
        onFrameClick={onFrameClick}
        onRequestDeleteFrame={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByLabelText('caption-b'));
    expect(onFrameClick).toHaveBeenCalledWith(1);
  });

  it('requests deletion of the hovered frame, not a click-through to the lightbox', () => {
    const onFrameClick = vi.fn();
    const onRequestDeleteFrame = vi.fn();
    render(
      <ConversationScreenFrameCarousel
        frames={[frame('a'), frame('b')]}
        onFrameClick={onFrameClick}
        onRequestDeleteFrame={onRequestDeleteFrame}
      />,
    );

    fireEvent.click(screen.getAllByLabelText('Delete screenshot')[0]);

    expect(onRequestDeleteFrame).toHaveBeenCalledWith('a');
    expect(onFrameClick).not.toHaveBeenCalled();
  });

  it('shows a spinner instead of the delete affordance for the frame being deleted', () => {
    render(
      <ConversationScreenFrameCarousel
        frames={[frame('a'), frame('b')]}
        onFrameClick={vi.fn()}
        onRequestDeleteFrame={vi.fn()}
        deletingFrameId="a"
      />,
    );

    // Only frame "b" still exposes a delete button; "a" is mid-delete.
    expect(screen.getAllByLabelText('Delete screenshot')).toHaveLength(1);
  });

  it('requests deleting everything via the "Clear all" affordance', () => {
    const onRequestDeleteAll = vi.fn();
    render(
      <ConversationScreenFrameCarousel
        frames={[frame('a')]}
        onFrameClick={vi.fn()}
        onRequestDeleteFrame={vi.fn()}
        onRequestDeleteAll={onRequestDeleteAll}
      />,
    );

    fireEvent.click(screen.getByText('Clear all'));
    expect(onRequestDeleteAll).toHaveBeenCalledTimes(1);
  });

  it('omits "Clear all" when no handler is given', () => {
    render(
      <ConversationScreenFrameCarousel
        frames={[frame('a')]}
        onFrameClick={vi.fn()}
        onRequestDeleteFrame={vi.fn()}
      />,
    );

    expect(screen.queryByText('Clear all')).not.toBeInTheDocument();
  });
});
