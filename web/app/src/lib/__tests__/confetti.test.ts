import { describe, it, expect } from 'vitest';
import { confettiParticles } from '@/lib/confetti';

/**
 * The layout is deterministic on purpose: `Math.random` would differ between
 * the server and client render and React would throw the markup away as a
 * hydration mismatch.
 */
describe('confettiParticles', () => {
  it('is deterministic for a given seed', () => {
    expect(confettiParticles(12, 3)).toEqual(confettiParticles(12, 3));
  });

  it('lays out a different burst for a different seed', () => {
    expect(confettiParticles(12, 1)).not.toEqual(confettiParticles(12, 2));
  });

  it('produces the requested number of pieces', () => {
    expect(confettiParticles(22)).toHaveLength(22);
  });

  it('scatters around the origin rather than clumping on one side', () => {
    // Every piece taking the same direction is the failure mode a purely
    // random angle produces at small counts; the arc share prevents it.
    const pieces = confettiParticles(16);
    expect(pieces.some((p) => p.x > 0)).toBe(true);
    expect(pieces.some((p) => p.x < 0)).toBe(true);
    expect(pieces.some((p) => p.y > 0)).toBe(true);
    expect(pieces.some((p) => p.y < 0)).toBe(true);
  });

  it('keeps every piece within reach of the surface it burst from', () => {
    for (const p of confettiParticles(40, 7)) {
      expect(Math.hypot(p.x, p.y)).toBeLessThan(110);
      expect(p.size).toBeGreaterThan(0);
      expect(p.duration).toBeGreaterThan(0);
    }
  });
});
