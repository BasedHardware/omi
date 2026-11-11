import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { RecordingStage } from '@/components/chat/RecordingStage';
import type { TranscriptSegment } from '@/components/recording/RecordingContext';

const reducedMotion = vi.hoisted(() => ({ value: false }));

vi.mock('framer-motion', async (importOriginal) => ({
  ...(await importOriginal<typeof import('framer-motion')>()),
  useReducedMotion: () => reducedMotion.value,
}));

function segment(id: string, text: string): TranscriptSegment {
  return { id, text, speaker: 0, isUser: true, timestamp: 0 };
}

function renderStage(props: Partial<Parameters<typeof RecordingStage>[0]> = {}) {
  const handlers = {
    onPause: vi.fn(),
    onResume: vi.fn(),
    onStop: vi.fn(),
  };
  const result = render(
    <RecordingStage
      segments={[]}
      duration={0}
      level={0}
      isPaused={false}
      {...handlers}
      {...props}
    />,
  );
  return { ...result, ...handlers };
}

beforeEach(() => {
  reducedMotion.value = false;
  // jsdom has no layout, so the anchor's scroll call has to be stubbed for the
  // component to be renderable at all.
  Element.prototype.scrollIntoView = vi.fn();
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
});

describe('RecordingStage during startup', () => {
  // Both handlers no-op until capture actually starts, so a stage that offers
  // them is a capture the user cannot cancel.
  it('disables pause and stop and says it is starting', () => {
    renderStage({ isInitializing: true });

    expect(screen.getByRole('button', { name: 'Pause recording' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Stop recording' })).toBeDisabled();
    expect(screen.getByText('Starting...')).toBeInTheDocument();
    expect(screen.queryByText('Listening')).not.toBeInTheDocument();
  });

  it('enables the controls once capture is running', () => {
    renderStage();

    expect(screen.getByRole('button', { name: 'Pause recording' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Stop recording' })).toBeEnabled();
    expect(screen.getByText('Listening')).toBeInTheDocument();
  });
});

describe('RecordingStage transcript', () => {
  // The transcript is height-capped; without an anchor it keeps showing the
  // oldest lines while speech is appended out of view below.
  it('scrolls the newest line into view as segments arrive', () => {
    const { rerender } = renderStage({ segments: [segment('1', 'first')] });
    const scrollIntoView = Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>;
    const initialCalls = scrollIntoView.mock.calls.length;
    expect(initialCalls).toBeGreaterThan(0);

    rerender(
      <RecordingStage
        segments={[segment('1', 'first'), segment('2', 'second')]}
        duration={0}
        level={0}
        isPaused={false}
        onPause={vi.fn()}
        onResume={vi.fn()}
        onStop={vi.fn()}
      />,
    );

    expect(scrollIntoView.mock.calls.length).toBeGreaterThan(initialCalls);
    expect(screen.getByTestId('transcript-end')).toBeInTheDocument();
  });

  it('replaces a partial segment live without duplicating it', () => {
    const { rerender } = renderStage({ segments: [segment('live', 'Hello')] });

    rerender(
      <RecordingStage
        segments={[segment('live', 'Hello from the live transcript')]}
        duration={1}
        level={0.8}
        isPaused={false}
        onPause={vi.fn()}
        onResume={vi.fn()}
        onStop={vi.fn()}
      />,
    );

    expect(screen.queryByText('Hello')).not.toBeInTheDocument();
    expect(screen.getByText('Hello from the live transcript')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite');
  });
});

describe('RecordingStage Omi mark', () => {
  function geometry() {
    return Array.from(
      screen.getByRole('img', { name: 'Omi live' }).querySelectorAll('circle'),
    ).map((circle) => [
      circle.getAttribute('cx'),
      circle.getAttribute('cy'),
      circle.getAttribute('r'),
    ]);
  }

  it('keeps the canonical eight-dot mark while starting, listening, and paused', () => {
    const { rerender } = renderStage({ isInitializing: true, level: 0 });
    const starting = geometry();

    rerender(
      <RecordingStage
        segments={[]}
        duration={1}
        level={1}
        isPaused={false}
        onPause={vi.fn()}
        onResume={vi.fn()}
        onStop={vi.fn()}
      />,
    );
    const listening = geometry();

    rerender(
      <RecordingStage
        segments={[]}
        duration={1}
        level={0}
        isPaused
        onPause={vi.fn()}
        onResume={vi.fn()}
        onStop={vi.fn()}
      />,
    );

    expect(listening).toEqual(starting);
    expect(geometry()).toEqual(starting);
    expect(starting).toHaveLength(8);
    expect(new Set(starting.map((dot) => dot[2]))).toEqual(new Set(['17.2']));
    expect(
      screen
        .getByRole('img', { name: 'Omi live' })
        .querySelectorAll('path, line, polyline, polygon, rect, ellipse'),
    ).toHaveLength(0);
  });

  it('pulses only the whole mark while preserving its geometry', () => {
    const { rerender } = renderStage({ level: 0 });
    const resting = geometry();

    expect(screen.getByTestId('omi-live-mark')).toHaveAttribute('data-pulse-min', '0.94');
    expect(screen.getByTestId('omi-live-mark')).toHaveAttribute('data-pulse-max', '1.02');

    rerender(
      <RecordingStage
        segments={[]}
        duration={1}
        level={1}
        isPaused={false}
        onPause={vi.fn()}
        onResume={vi.fn()}
        onStop={vi.fn()}
      />,
    );

    expect(screen.getByTestId('omi-live-mark')).toHaveAttribute('data-pulse-max', '1.07');
    expect(geometry()).toEqual(resting);
  });

  it('keeps the mark stationary with reduced motion', () => {
    reducedMotion.value = true;
    const { rerender } = renderStage({ level: 0 });
    const resting = geometry();

    rerender(
      <RecordingStage
        segments={[]}
        duration={1}
        level={1}
        isPaused={false}
        onPause={vi.fn()}
        onResume={vi.fn()}
        onStop={vi.fn()}
      />,
    );

    expect(screen.getByTestId('omi-live-mark')).toHaveAttribute('data-pulse-min', '1');
    expect(screen.getByTestId('omi-live-mark')).toHaveAttribute('data-pulse-max', '1');
    expect(geometry()).toEqual(resting);
  });
});
