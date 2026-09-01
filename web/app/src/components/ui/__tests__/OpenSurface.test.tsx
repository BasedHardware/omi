import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { OpenSurface } from '@/components/ui/OpenSurface';

describe('OpenSurface', () => {
  beforeEach(() => {
    document.documentElement.style.setProperty('--dropdown-close-dur', '150ms');
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({
        matches: false,
        media: '(prefers-reduced-motion: reduce)',
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
        onchange: null,
      })),
    );
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

  it('stays mounted through the close transition', () => {
    vi.useFakeTimers();
    const onExited = vi.fn();
    const { rerender } = render(
      <OpenSurface open className="t-dropdown" onExited={onExited}>
        Menu
      </OpenSurface>,
    );

    act(() => {
      vi.advanceTimersByTime(0);
    });
    expect(screen.getByText('Menu')).toHaveClass('is-open');

    rerender(
      <OpenSurface open={false} className="t-dropdown" onExited={onExited}>
        Menu
      </OpenSurface>,
    );
    expect(screen.getByText('Menu')).toHaveClass('is-closing');
    expect(onExited).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(screen.queryByText('Menu')).toBeNull();
    expect(onExited).toHaveBeenCalledTimes(1);
  });
});
