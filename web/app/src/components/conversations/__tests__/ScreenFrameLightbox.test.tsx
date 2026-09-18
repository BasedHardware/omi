import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ScreenFrameLightbox } from '@/components/conversations/ScreenFrameLightbox';
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

describe('ScreenFrameLightbox', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <ScreenFrameLightbox
        open={false}
        frames={[frame('a')]}
        index={0}
        onIndexChange={vi.fn()}
        onClose={vi.fn()}
        onRequestDeleteFrame={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the full-size image at content_url with the caption as alt text', () => {
    render(
      <ScreenFrameLightbox
        open
        frames={[frame('a', 'Terminal output')]}
        index={0}
        onIndexChange={vi.fn()}
        onClose={vi.fn()}
        onRequestDeleteFrame={vi.fn()}
      />,
    );

    const img = screen.getByAltText('Terminal output');
    expect(img).toHaveAttribute('src', 'https://example.com/a.jpg');
  });

  it('steps forward with wraparound on ArrowRight', () => {
    const onIndexChange = vi.fn();
    render(
      <ScreenFrameLightbox
        open
        frames={[frame('a'), frame('b'), frame('c')]}
        index={2}
        onIndexChange={onIndexChange}
        onClose={vi.fn()}
        onRequestDeleteFrame={vi.fn()}
      />,
    );

    fireEvent.keyDown(window, { key: 'ArrowRight' });
    expect(onIndexChange).toHaveBeenCalledWith(0);
  });

  it('steps backward with wraparound on ArrowLeft', () => {
    const onIndexChange = vi.fn();
    render(
      <ScreenFrameLightbox
        open
        frames={[frame('a'), frame('b'), frame('c')]}
        index={0}
        onIndexChange={onIndexChange}
        onClose={vi.fn()}
        onRequestDeleteFrame={vi.fn()}
      />,
    );

    fireEvent.keyDown(window, { key: 'ArrowLeft' });
    expect(onIndexChange).toHaveBeenCalledWith(2);
  });

  it('does not step on a single-frame strip', () => {
    const onIndexChange = vi.fn();
    render(
      <ScreenFrameLightbox
        open
        frames={[frame('a')]}
        index={0}
        onIndexChange={onIndexChange}
        onClose={vi.fn()}
        onRequestDeleteFrame={vi.fn()}
      />,
    );

    fireEvent.keyDown(window, { key: 'ArrowRight' });
    expect(onIndexChange).not.toHaveBeenCalled();
  });

  it('requests deletion of the currently displayed frame', () => {
    const onRequestDeleteFrame = vi.fn();
    render(
      <ScreenFrameLightbox
        open
        frames={[frame('a'), frame('b')]}
        index={1}
        onIndexChange={vi.fn()}
        onClose={vi.fn()}
        onRequestDeleteFrame={onRequestDeleteFrame}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /delete/i }));
    expect(onRequestDeleteFrame).toHaveBeenCalledWith('b');
  });

  it('closes on Escape, deferring to Radix Dialog default behaviour', () => {
    const onClose = vi.fn();
    render(
      <ScreenFrameLightbox
        open
        frames={[frame('a')]}
        index={0}
        onIndexChange={vi.fn()}
        onClose={onClose}
        onRequestDeleteFrame={vi.fn()}
      />,
    );

    fireEvent.keyDown(document.body, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
