/**
 * Where the pieces of a confetti burst go.
 *
 * Deterministic from a seed rather than `Math.random`, so a burst renders the
 * same on the server and the client — a random layout would differ between the
 * two and React would discard the markup as a hydration mismatch. It also
 * makes the spread testable.
 */

export interface ConfettiParticle {
  /** Offset from the burst origin, in pixels. */
  x: number;
  y: number;
  size: number;
  /** Height as a multiple of width; confetti is rectangular, not square. */
  aspect: number;
  rotate: number;
  duration: number;
  color: string;
}

/**
 * Neutral palette. The brand accent is white (INV-UI-1), so the pieces are
 * white and greys at varying weight rather than a rainbow — the burst reads as
 * the surface breaking up, not as a party favour from another product.
 */
const COLORS = ['#FFFFFF', '#E5E5E5', '#B0B0B0', '#888888', '#35343B'];

/** Deterministic unit noise for index `i`. Cheap, and good enough for scatter. */
function noise(i: number, salt: number): number {
  const x = Math.sin((i + 1) * 12.9898 + salt * 78.233) * 43758.5453;
  return x - Math.floor(x);
}

export function confettiParticles(count: number, seed = 0): ConfettiParticle[] {
  return Array.from({ length: count }, (_, i) => {
    // Spread around the full circle by index so the pieces cannot clump, with
    // the noise only jittering each one off its share of the arc.
    const angle = (i / count) * Math.PI * 2 + (noise(i, seed) - 0.5) * 0.6;
    const distance = 26 + noise(i, seed + 1) * 46;

    return {
      x: Math.cos(angle) * distance,
      // Biased upward: confetti thrown from a point reads better rising than
      // sinking, and the banner it replaces sits at the bottom of the rail.
      y: Math.sin(angle) * distance - 12,
      size: 3 + noise(i, seed + 2) * 4,
      aspect: 1.6 + noise(i, seed + 3),
      rotate: (noise(i, seed + 4) - 0.5) * 540,
      duration: 0.5 + noise(i, seed + 5) * 0.35,
      color: COLORS[i % COLORS.length],
    };
  });
}
