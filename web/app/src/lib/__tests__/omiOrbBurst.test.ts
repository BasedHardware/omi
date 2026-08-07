import { describe, expect, it } from 'vitest';
import {
  OmiMarkGeometry,
  omiBurstForTurn,
  omiDotPlacement,
  omiOrbPlacements,
} from '@/lib/omiOrb';

/** How far dot `i` sits from the ring centre. */
function radius(offset: { x: number; y: number }): number {
  return Math.hypot(offset.x, offset.y);
}

describe('omiBurstForTurn', () => {
  it('advances the scatter across the lap for successBurst', () => {
    expect(omiBurstForTurn('successBurst', 0)).toBe(0);
    expect(omiBurstForTurn('successBurst', 0.5)).toBeCloseTo(0.5);
    expect(omiBurstForTurn('successBurst', 1)).toBe(1);
  });

  it('leaves every other motion on the settled default', () => {
    expect(omiBurstForTurn('mark', 0.5)).toBe(1);
    expect(omiBurstForTurn('sine', 0.25)).toBe(1);
  });

  // The bug: the renderer omitted `burst`, so every frame used the settled
  // default and the ring sat at its rest radius for the whole "burst".
  it('drives dots off the rest radius mid-lap, unlike the settled default', () => {
    const rest = OmiMarkGeometry.radiusOf(0);

    const settled = omiDotPlacement({ motion: 'successBurst', index: 0, turn: 0.5 });
    expect(radius(settled.offset)).toBeCloseTo(rest);

    const bursting = omiDotPlacement({
      motion: 'successBurst',
      index: 0,
      turn: 0.5,
      burst: omiBurstForTurn('successBurst', 0.5),
    });
    expect(radius(bursting.offset)).toBeGreaterThan(rest + 10);
  });

  it('scatters and re-forms across one lap', () => {
    const radiusAt = (turn: number) =>
      radius(
        omiOrbPlacements({
          motion: 'successBurst',
          turn,
          burst: omiBurstForTurn('successBurst', turn),
        })[0].offset,
      );

    const rest = OmiMarkGeometry.radiusOf(0);
    expect(radiusAt(0)).toBeCloseTo(rest);
    expect(radiusAt(0.5)).toBeGreaterThan(radiusAt(0.1));
    expect(radiusAt(1)).toBeCloseTo(rest);
  });
});
