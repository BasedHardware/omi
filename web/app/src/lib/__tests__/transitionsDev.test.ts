import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { prefersReducedMotion, readDurationToken, replayErrorShake } from '@/lib/transitionsDev';

describe('transitionsDev helpers', () => {
  beforeEach(() => {
    document.documentElement.style.setProperty('--text-swap-dur', '150ms');
    document.documentElement.style.setProperty('--shake-dur-a', '80ms');
    document.documentElement.style.setProperty('--shake-dur-b', '60ms');
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

  it('reads duration tokens from :root', () => {
    document.documentElement.style.setProperty('--text-swap-dur', '180ms');
    expect(readDurationToken('--text-swap-dur', 200)).toBe(180);
    expect(readDurationToken('--missing-token', 42)).toBe(42);
  });

  it('detects prefers-reduced-motion', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({
        matches: query.includes('prefers-reduced-motion'),
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
        onchange: null,
      })),
    );
    expect(prefersReducedMotion()).toBe(true);
  });

  it('replays the error shake class through a reflow', () => {
    vi.useFakeTimers();
    const input = document.createElement('div');
    input.classList.add('t-input');
    document.body.appendChild(input);

    replayErrorShake(input);
    expect(input.classList.contains('is-shaking')).toBe(true);

    vi.advanceTimersByTime(300);
    expect(input.classList.contains('is-shaking')).toBe(false);

    replayErrorShake(input);
    expect(input.classList.contains('is-shaking')).toBe(true);
    input.remove();
  });

  it('cancels an in-flight error shake', () => {
    const input = document.createElement('div');
    const stop = replayErrorShake(input);
    expect(input.classList.contains('is-shaking')).toBe(true);
    stop();
    expect(input.classList.contains('is-shaking')).toBe(false);
  });

  it('skips the error shake when reduced motion is requested', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({
        matches: query.includes('prefers-reduced-motion'),
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
        onchange: null,
      })),
    );
    const input = document.createElement('div');
    replayErrorShake(input);
    expect(input.classList.contains('is-shaking')).toBe(false);
  });
});
