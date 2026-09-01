import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PanelReveal } from '@/components/ui/PanelReveal';

describe('PanelReveal', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'requestAnimationFrame',
      (cb: FrameRequestCallback) => window.setTimeout(() => cb(0), 0),
    );
    vi.stubGlobal('cancelAnimationFrame', (id: number) => window.clearTimeout(id));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('paints closed before opening so the CSS transition can run', () => {
    vi.useFakeTimers();
    const { container } = render(
      <PanelReveal>
        <p>Panel</p>
      </PanelReveal>,
    );
    const el = container.querySelector('.t-panel-slide');
    expect(el).toHaveAttribute('data-open', 'false');

    act(() => {
      vi.advanceTimersByTime(0);
    });
    expect(el).toHaveAttribute('data-open', 'true');
  });
});
