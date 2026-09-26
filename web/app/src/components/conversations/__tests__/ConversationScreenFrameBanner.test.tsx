import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ConversationScreenFrameBanner } from '@/components/conversations/ConversationScreenFrameBanner';
import type { ConversationScreenFrame } from '@/types/conversation';

vi.mock('@tschk/moonshine-next/image', () => ({
  default: (props: Record<string, unknown>) => {
    const { fill: _fill, ...rest } = props;
    // eslint-disable-next-line @next/next/no-img-element
    return <img {...rest} />;
  },
}));

function frame(
  overrides: Partial<ConversationScreenFrame> = {},
): ConversationScreenFrame {
  return {
    id: 'frame-1',
    captured_at: '2026-08-24T10:00:00Z',
    role: 'banner',
    rank: 0,
    caption: 'A whiteboard sketch',
    labels: [],
    source_badge: null,
    focal_region: null,
    width: 1600,
    height: 900,
    content_url: 'https://example.com/frame-1.jpg',
    thumbnail_url: 'https://example.com/frame-1_thumb.jpg',
    url_expires_at: '2026-08-24T11:00:00Z',
    // `ground` is required in the generated schema; individual tests override
    // it to exercise the specific-stops and defensive-fallback paths.
    ground: { stops: ['#101010', '#202020'], is_neutral: false },
    ...overrides,
  };
}

describe('ConversationScreenFrameBanner', () => {
  it('renders nothing when there is no banner frame', () => {
    const { container } = render(
      <ConversationScreenFrameBanner frame={null} title="Standup" />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the title, date, and the frame caption as alt text', () => {
    render(
      <ConversationScreenFrameBanner
        frame={frame()}
        title="Weekly Standup"
        dateLabel="Monday, August 24, 2026"
      />,
    );

    expect(screen.getByText('Weekly Standup')).toBeInTheDocument();
    expect(screen.getByText('Monday, August 24, 2026')).toBeInTheDocument();
    expect(screen.getByAltText('A whiteboard sketch')).toBeInTheDocument();
  });

  it('shows the source badge when present', () => {
    render(
      <ConversationScreenFrameBanner
        frame={frame({ source_badge: 'slides' })}
        title="Weekly Standup"
      />,
    );

    expect(screen.getByText('Slides')).toBeInTheDocument();
  });

  it('omits the badge when source_badge is null', () => {
    render(
      <ConversationScreenFrameBanner
        frame={frame({ source_badge: null })}
        title="Weekly Standup"
      />,
    );

    expect(screen.queryByText('Slides')).not.toBeInTheDocument();
    expect(screen.queryByText('Code')).not.toBeInTheDocument();
  });

  it('is not interactive when onClick is omitted', () => {
    render(<ConversationScreenFrameBanner frame={frame()} title="Weekly Standup" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('calls onClick when clicked', () => {
    const onClick = vi.fn();
    render(
      <ConversationScreenFrameBanner
        frame={frame()}
        title="Weekly Standup"
        onClick={onClick}
      />,
    );

    fireEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('calls onClick on Enter and Space', () => {
    const onClick = vi.fn();
    render(
      <ConversationScreenFrameBanner
        frame={frame()}
        title="Weekly Standup"
        onClick={onClick}
      />,
    );

    const banner = screen.getByRole('button');
    fireEvent.keyDown(banner, { key: 'Enter' });
    fireEvent.keyDown(banner, { key: ' ' });
    expect(onClick).toHaveBeenCalledTimes(2);
  });

  it('renders the server-provided gradient stops', () => {
    const { container } = render(
      <ConversationScreenFrameBanner
        frame={frame({ ground: { stops: ['#112233', '#445566'], is_neutral: false } })}
        title="Weekly Standup"
      />,
    );

    // jsdom's CSSOM normalizes hex to rgb() on the way back out, so assert
    // on the decimal channel values rather than the hex string we set.
    const ground = container.querySelector('[aria-hidden="true"]') as HTMLElement;
    expect(ground.style.backgroundImage).toContain('linear-gradient');
    expect(ground.style.backgroundImage).toContain('17, 34, 51');
    expect(ground.style.backgroundImage).toContain('68, 85, 102');
  });

  it('falls back to the neutral ground per-stop when stops are missing', () => {
    // The generated `ScreenFrameGround.stops` is a general string[], not a
    // fixed 2-tuple, so a malformed record with too few stops should still
    // render — defaulting each missing stop to the neutral ground value.
    const { container } = render(
      <ConversationScreenFrameBanner
        frame={frame({ ground: { stops: [], is_neutral: true } })}
        title="Weekly Standup"
      />,
    );

    const ground = container.querySelector('[aria-hidden="true"]') as HTMLElement;
    expect(ground.style.backgroundImage).toContain('linear-gradient');
    expect(ground.style.backgroundImage).toContain('90, 93, 102');
    expect(ground.style.backgroundImage).toContain('51, 54, 61');
  });
});
