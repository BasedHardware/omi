import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BetaWelcomeModal } from '@/components/ui/BetaWelcomeModal';
import { StartupModals } from '@/components/ui/StartupModals';

const mocks = vi.hoisted(() => ({
  confetti: vi.fn(),
  reducedMotion: false,
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
  >(
    (
      {
        initial: _initial,
        animate: _animate,
        exit: _exit,
        transition: _transition,
        ...props
      },
      ref,
    ) => <div ref={ref} {...props} />,
  );

  return {
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    motion: { div: MotionDiv },
    useReducedMotion: () => mocks.reducedMotion,
  };
});

describe('StartupModals', () => {
  beforeEach(() => {
    localStorage.clear();
    mocks.confetti.mockClear();
    mocks.reducedMotion = false;
    vi.useFakeTimers();
    vi.stubGlobal(
      'requestAnimationFrame',
      vi.fn(() => 1),
    );
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('shows eligible startup modals one at a time', () => {
    render(<StartupModals />);

    act(() => vi.advanceTimersByTime(500));

    expect(
      screen.getByRole('heading', { name: 'Welcome to Omi Web Beta' }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: "What's New" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: "Got it, let's go!" }));

    expect(
      screen.queryByRole('heading', { name: 'Welcome to Omi Web Beta' }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: "What's New" })).toBeInTheDocument();
    expect(localStorage.getItem('omi_beta_welcome_seen')).toBe('true');

    fireEvent.click(screen.getByRole('button', { name: 'Got it!' }));

    expect(screen.queryByRole('heading', { name: "What's New" })).not.toBeInTheDocument();
    expect(localStorage.getItem('omi_whats_new_version')).toBe('1');
  });

  it('keeps the original whats-new delay when welcome was already seen', () => {
    localStorage.setItem('omi_beta_welcome_seen', 'true');
    render(<StartupModals />);

    act(() => vi.advanceTimersByTime(799));
    expect(screen.queryByRole('heading')).not.toBeInTheDocument();

    act(() => vi.advanceTimersByTime(1));
    expect(screen.getByRole('heading', { name: "What's New" })).toBeInTheDocument();
  });

  it('shows nothing when both startup messages were seen', () => {
    localStorage.setItem('omi_beta_welcome_seen', 'true');
    localStorage.setItem('omi_whats_new_version', '1');
    render(<StartupModals />);

    act(() => vi.runAllTimers());

    expect(screen.queryByRole('heading')).not.toBeInTheDocument();
  });

  it('uses a short neutral celebration', () => {
    render(<BetaWelcomeModal onDismiss={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: "Got it, let's go!" }));

    expect(mocks.confetti).toHaveBeenCalledTimes(2);
    for (const [options] of mocks.confetti.mock.calls) {
      expect(options.colors).toEqual(['#FFFFFF', '#E5E5E5', '#B0B0B0', '#737373']);
      expect(options.particleCount).toBe(2);
    }
  });

  it('omits celebration movement when reduced motion is preferred', () => {
    mocks.reducedMotion = true;
    render(<BetaWelcomeModal onDismiss={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: "Got it, let's go!" }));

    expect(mocks.confetti).not.toHaveBeenCalled();
  });
});
