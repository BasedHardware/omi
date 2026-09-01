import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PageSlide } from '@/components/ui/PageSlide';

describe('PageSlide', () => {
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
});
