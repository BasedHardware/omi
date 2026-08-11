import { act, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatComposer } from '@/components/chat/ChatComposer';

vi.mock('@/lib/api', () => ({
  transcribeVoiceMessage: vi.fn(),
  uploadChatFiles: vi.fn(),
}));

const makeMediaQuery = (matches: boolean): MediaQueryList =>
  ({
    matches,
    media: '(prefers-reduced-motion: reduce)',
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }) as unknown as MediaQueryList;

const geometry = (circles: SVGCircleElement[]) =>
  circles.map((circle) => [
    circle.getAttribute('cx'),
    circle.getAttribute('cy'),
    circle.getAttribute('r'),
  ]);

describe('ChatComposer recording control', () => {
  const frames: FrameRequestCallback[] = [];

  beforeEach(() => {
    frames.length = 0;
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => makeMediaQuery(false)),
    );
    vi.stubGlobal(
      'requestAnimationFrame',
      vi.fn((callback: FrameRequestCallback) => {
        frames.push(callback);
        return frames.length;
      }),
    );
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('keeps one dot ring while listening and pulses without changing its geometry', () => {
    const onStart = vi.fn();
    const onStop = vi.fn();
    const { rerender } = render(
      <ChatComposer
        onSend={vi.fn(async () => {})}
        isStreaming={false}
        recording={{ isActive: false, level: 0, onStart, onStop }}
      />,
    );

    const idleButton = screen.getByRole('button', { name: 'Start a live conversation' });
    const idleOrb = within(idleButton).getByRole('img', { name: 'Omi' });
    const idleCircles = Array.from(idleOrb.querySelectorAll('circle'));
    const idleGeometry = geometry(idleCircles);

    expect(idleCircles).toHaveLength(8);
    expect(frames).toHaveLength(0);

    rerender(
      <ChatComposer
        onSend={vi.fn(async () => {})}
        isStreaming={false}
        recording={{ isActive: true, level: 1, onStart, onStop }}
      />,
    );

    const listeningButton = screen.getByRole('button', { name: 'Stop conversation' });
    const listeningOrb = within(listeningButton).getByRole('img', { name: 'Omi' });
    const listeningCircles = Array.from(listeningOrb.querySelectorAll('circle'));
    const initialStyles = listeningCircles.map((circle) => circle.style.cssText);

    expect(geometry(listeningCircles)).toEqual(idleGeometry);
    expect(frames).toHaveLength(1);

    act(() => frames.shift()?.(16));
    act(() => frames.shift()?.(300));

    expect(geometry(listeningCircles)).toEqual(idleGeometry);
    expect(listeningCircles.map((circle) => circle.style.cssText)).not.toEqual(
      initialStyles,
    );
    expect(
      listeningCircles.every(
        (circle) => circle.style.transform !== '' && circle.style.opacity !== '',
      ),
    ).toBe(true);
  });

  it('does not schedule listening movement when reduced motion is enabled', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => makeMediaQuery(true)),
    );

    render(
      <ChatComposer
        onSend={vi.fn(async () => {})}
        isStreaming={false}
        recording={{
          isActive: true,
          level: 1,
          onStart: vi.fn(),
          onStop: vi.fn(),
        }}
      />,
    );

    const button = screen.getByRole('button', { name: 'Stop conversation' });
    expect(
      within(button).getByRole('img', { name: 'Omi' }).querySelectorAll('circle'),
    ).toHaveLength(8);
    expect(requestAnimationFrame).not.toHaveBeenCalled();
  });
});
