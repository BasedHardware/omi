import { render } from '@testing-library/react';
import { useLayoutEffect, useRef } from 'react';
import { describe, expect, it } from 'vitest';
import { PanelReveal } from '@/components/ui/PanelReveal';

describe('PanelReveal', () => {
  it('paints closed before opening so the CSS transition can run', () => {
    const firstLayout: string[] = [];

    function Probe() {
      const ref = useRef<HTMLSpanElement>(null);
      useLayoutEffect(() => {
        firstLayout.push(ref.current?.parentElement?.getAttribute('data-open') ?? '');
      }, []);
      return <span ref={ref}>Panel</span>;
    }

    const { container } = render(
      <PanelReveal>
        <Probe />
      </PanelReveal>,
    );

    expect(firstLayout[0]).toBe('false');
    expect(container.querySelector('.t-panel-slide')).toHaveAttribute('data-open', 'true');
  });
});
