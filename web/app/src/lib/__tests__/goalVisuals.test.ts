import { describe, expect, it } from 'vitest';
import {
  isCompleted,
  progressColor,
  progressLabel,
  progressPct,
} from '@/lib/goalVisuals';
import { DEFAULT_GOAL_EMOJI, goalEmoji } from '@/lib/goalEmoji';

/**
 * These lock the behaviour ported from the desktop apps
 * (`desktop/windows/src/renderer/src/lib/goalVisuals.ts` and `goalEmoji.ts`,
 * themselves ports of the macOS `GoalsWidget`). A goal must read the same on
 * web, Electron, and macOS, so a divergence here should fail rather than
 * quietly re-tune web on its own.
 */

describe('progressColor', () => {
  it('is a five-stage threshold ramp, not a continuous gradient', () => {
    expect(progressColor(1)).toBe('#22C55E');
    expect(progressColor(0.8)).toBe('#22C55E');
    expect(progressColor(0.79)).toBe('#84CC16');
    expect(progressColor(0.6)).toBe('#84CC16');
    expect(progressColor(0.59)).toBe('#FBBF24');
    expect(progressColor(0.4)).toBe('#FBBF24');
    expect(progressColor(0.39)).toBe('#F97316');
    expect(progressColor(0.2)).toBe('#F97316');
    expect(progressColor(0.19)).toBe('rgba(255, 255, 255, 0.3)');
    expect(progressColor(0)).toBe('rgba(255, 255, 255, 0.3)');
  });
});

describe('isCompleted', () => {
  it('treats a server-archived goal as done regardless of value', () => {
    expect(isCompleted({ is_active: false, current_value: 0, target_value: 10 })).toBe(
      true,
    );
  });

  it('is done once the value reaches the target', () => {
    expect(isCompleted({ current_value: 9, target_value: 10 })).toBe(false);
    expect(isCompleted({ current_value: 10, target_value: 10 })).toBe(true);
  });

  it('is never done without a positive target', () => {
    expect(isCompleted({ current_value: 5, target_value: 0 })).toBe(false);
    expect(isCompleted({ current_value: 5 })).toBe(false);
  });
});

describe('progressPct', () => {
  it('measures current over target, not from a floor', () => {
    // Desktop reads a 40->80 goal sitting at 40 as 50%, not 0%.
    expect(progressPct({ current_value: 40, target_value: 80 })).toBe(50);
  });

  it('clamps and rounds', () => {
    expect(progressPct({ current_value: -5, target_value: 10 })).toBe(0);
    expect(progressPct({ current_value: 1, target_value: 3 })).toBe(33);
  });

  it('reports an archived goal as complete', () => {
    expect(progressPct({ is_active: false, current_value: 0, target_value: 10 })).toBe(
      100,
    );
  });

  it('is zero without a target', () => {
    expect(progressPct({ current_value: 7, target_value: 0 })).toBe(0);
  });
});

describe('progressLabel', () => {
  it('shows current over target with the unit', () => {
    expect(progressLabel({ current_value: 3, target_value: 10, unit: 'books' })).toBe(
      '3 / 10 books',
    );
  });

  it('falls back to a percentage when there is no target', () => {
    expect(progressLabel({ current_value: 3, target_value: 0 })).toBe('0%');
  });
});

describe('goalEmoji', () => {
  it('matches the first bucket containing any keyword', () => {
    expect(goalEmoji('Hit $10k MRR')).toBe('💰');
    expect(goalEmoji('Read 12 books')).toBe('📚');
    expect(goalEmoji('Run a marathon')).toBe('🏃');
    expect(goalEmoji('Meditate daily')).toBe('🧘');
  });

  it('keeps bucket order load-bearing: growth resolves before grow', () => {
    expect(goalEmoji('growth')).toBe('🚀');
    expect(goalEmoji('grow the garden')).toBe('🌱');
  });

  it('is case-insensitive', () => {
    expect(goalEmoji('READ MORE')).toBe('📚');
  });

  it('falls back to the default target glyph', () => {
    expect(goalEmoji('qqqq')).toBe(DEFAULT_GOAL_EMOJI);
  });
});
