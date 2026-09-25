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

  it('does not treat a distant data-state ancestor as the close host', () => {
    render(
      <div data-state="closed">
        <div>
          <OpenSurface open className="t-dropdown">
            Menu
          </OpenSurface>
        </div>
      </div>,
    );
    expect(screen.getByText('Menu')).toHaveClass('is-open');
    expect(screen.getByText('Menu')).not.toHaveClass('is-closing');
  });
});
