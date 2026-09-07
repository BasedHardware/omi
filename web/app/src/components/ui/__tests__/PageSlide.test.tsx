import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PageSlide } from '@/components/ui/PageSlide';

describe('PageSlide', () => {
  beforeEach(() => {
    document.documentElement.style.setProperty('--page-slide-dur', '250ms');
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

  it('flips data-page so the incoming t-page can enter', () => {
    const { container, rerender } = render(
      <PageSlide pageKey="/home">
        <p>Home</p>
      </PageSlide>,
    );

    const slider = container.querySelector('.t-page-slide');
    expect(slider).not.toBeNull();
    expect(slider).toHaveAttribute('data-page', '2');
    expect(container.querySelector('.t-page')).toHaveAttribute('data-page-id', '2');

    rerender(
      <PageSlide pageKey="/conversations">
        <p>Conversations</p>
      </PageSlide>,
    );
    expect(container.querySelector('.t-page-slide')).toHaveAttribute('data-page', '2');
  });

  it('clears the page transform after the enter transition settles', () => {
    const { container } = render(
      <PageSlide pageKey="/home">
        <p>Home</p>
      </PageSlide>,
    );
    const slider = container.querySelector('.t-page-slide');
    expect(slider).not.toHaveAttribute('data-settled');

    act(() => {
      container.querySelector('.t-page')?.dispatchEvent(new Event('transitionend'));
    });
    expect(slider).toHaveAttribute('data-settled');
  });
});
