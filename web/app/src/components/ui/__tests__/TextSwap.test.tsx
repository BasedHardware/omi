import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TextSwap } from '@/components/ui/TextSwap';

describe('TextSwap', () => {
  beforeEach(() => {
    document.documentElement.style.setProperty('--text-swap-dur', '150ms');
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

  it('swaps text through the t-text-swap exit/enter classes', () => {
    vi.useFakeTimers();
    const { rerender } = render(<TextSwap text="Select" />);
    const el = screen.getByText('Select');
    expect(el).toHaveClass('t-text-swap');

    rerender(<TextSwap text="Cancel" />);
    expect(el).toHaveClass('is-exit');

    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  it('returns to idle when the text reverses before the exit finishes', () => {
    vi.useFakeTimers();
    const { rerender } = render(<TextSwap text="Select" />);
    const el = screen.getByText('Select');

    rerender(<TextSwap text="Cancel" />);
    expect(el).toHaveClass('is-exit');

    rerender(<TextSwap text="Select" />);
    expect(el).not.toHaveClass('is-exit');
    expect(el).toHaveTextContent('Select');
  });

  it('swaps immediately when reduced motion is requested', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({
        matches: true,
        media: '(prefers-reduced-motion: reduce)',
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
        onchange: null,
      })),
    );
    const { rerender } = render(<TextSwap text="Select" />);
    rerender(<TextSwap text="Cancel" />);
    const el = screen.getByText('Cancel');
    expect(el).not.toHaveClass('is-exit');
  });
});
