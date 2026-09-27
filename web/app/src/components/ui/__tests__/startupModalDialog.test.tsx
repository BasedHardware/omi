import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BetaWelcomeModal } from '@/components/ui/BetaWelcomeModal';
import { WhatsNewModal } from '@/components/ui/WhatsNewModal';

/**
 * The startup dialogs animated `transform: 'none'`, which framer-motion
 * interpolates as an all-zero matrix: the dialog collapsed to 0×0 while its
 * backdrop still covered the screen, so a signed-in user landed on a dimmed
 * page they could not read or click. These tests pin the properties framer can
 * actually interpolate, and the ways out of the dialog.
 */

const mocks = vi.hoisted(() => ({
  confetti: vi.fn(),
  reducedMotion: false,
  motionProps: [] as Array<Record<string, unknown>>,
}));

vi.mock('canvas-confetti', () => ({ default: mocks.confetti }));

vi.mock('framer-motion', async () => {
  const ReactModule = await import('react');
  const MotionDiv = ReactModule.forwardRef<
    HTMLDivElement,
    React.HTMLAttributes<HTMLDivElement> & {
      initial?: unknown;
      animate?: unknown;
      exit?: unknown;
      transition?: unknown;
    }
  >(({ initial, animate, exit, transition, ...props }, ref) => {
    mocks.motionProps.push({ initial, animate, exit, transition });
    return <div ref={ref} {...props} />;
  });

  return {
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    motion: { div: MotionDiv },
    useReducedMotion: () => mocks.reducedMotion,
  };
});

/** Every animated value across the props the dialogs passed to motion.div. */
function animatedValues(): string[] {
  return mocks.motionProps.flatMap((props) =>
    [props.initial, props.animate, props.exit].map((value) => JSON.stringify(value ?? null)),
  );
}

beforeEach(() => {
  mocks.confetti.mockClear();
  mocks.motionProps.length = 0;
  mocks.reducedMotion = false;
});

afterEach(() => {
  cleanup();
});

describe.each([
  ['BetaWelcomeModal', BetaWelcomeModal],
  ['WhatsNewModal', WhatsNewModal],
] as const)('%s', (_name, Modal) => {
  it('animates with offsets framer can interpolate', () => {
    render(<Modal onDismiss={vi.fn()} />);

    // `transform: 'none'` is the bug: it resolves to matrix(0,0,0,0,0,0).
    for (const value of animatedValues()) {
      expect(value).not.toContain('transform');
    }

    const dialog = mocks.motionProps.find(
      (props) => typeof props.animate === 'object' && props.animate !== null && 'scale' in props.animate,
    );
    expect(dialog?.animate).toMatchObject({ opacity: 1, y: 0, scale: 1 });
  });

  it('caps the dialog height so the action stays reachable on a phone', () => {
    const { container } = render(<Modal onDismiss={vi.fn()} />);

    const dialog = container.querySelector('div.fixed.inset-0 > div');
    expect(dialog?.className).toContain('max-h-[calc(100dvh-2rem)]');
    expect(dialog?.className).toContain('overflow-y-auto');
  });

  it('dismisses from the close button, the backdrop and Escape', () => {
    const onDismiss = vi.fn();
    const { container } = render(<Modal onDismiss={onDismiss} />);

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onDismiss).toHaveBeenCalledTimes(1);

    const backdrop = container.querySelector('div.fixed.inset-0') as HTMLElement;
    fireEvent.click(backdrop);
    expect(onDismiss).toHaveBeenCalledTimes(2);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onDismiss).toHaveBeenCalledTimes(3);
  });

  it('stays open when the dialog itself is clicked', () => {
    const onDismiss = vi.fn();
    render(<Modal onDismiss={onDismiss} />);

    fireEvent.click(screen.getByRole('heading', { level: 2 }));

    expect(onDismiss).not.toHaveBeenCalled();
  });
});
