'use client';

import { useEffect, useMemo, useRef } from 'react';
import {
  OmiMarkGeometry,
  omiDotPlacement,
  omiMotionForState,
  omiOrbPlacements,
  type OmiOrbMotion,
  type OmiOrbState,
} from '@/lib/omiOrb';

interface OmiOrbProps {
  state?: OmiOrbState;
  /** Overrides the motion the state would pick. */
  motion?: OmiOrbMotion;
  /** Input level, 0 to 1. Drives `sine` and `audioBars`; ignored elsewhere. */
  level?: number;
  size?: number;
  /** Stable for the life of one wait, so the motion never twitches mid-wait. */
  seed?: number;
  className?: string;
  paused?: boolean;
}

/**
 * One full lap of each motion. The idle mark turns slowly; the level-metering
 * motions have to keep up with speech, so they run much tighter.
 */
const LAP_SECONDS: Record<OmiOrbMotion, number> = {
  mark: 6,
  spin: 6,
  pulse: 1.7,
  gather: 2.4,
  sine: 1.6,
  travellingWave: 2.2,
  standingWave: 2.4,
  pendulumWave: 3,
  tusiPendulum: 3,
  audioBars: 2,
  tusi: 2.6,
  nestedOrbit: 3,
  doubleCircle: 3,
  epicycloid: 2.6,
  lissajous: 3,
  pendulumSwing: 2.4,
  successBurst: 2,
};

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function')
    return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function OmiOrb({
  state = 'idle',
  motion,
  level = 0,
  size = 46,
  seed = 0,
  className,
  paused = false,
}: OmiOrbProps) {
  const active: OmiOrbMotion = motion ?? omiMotionForState(state, seed);
  const reduced = useMemo(prefersReducedMotion, []);

  const dots = useRef<(SVGCircleElement | null)[]>([]);
  const levelRef = useRef(level);
  levelRef.current = level;

  const unit = size / OmiMarkGeometry.canvas;
  const centre = size / 2;

  // The resting frame, used for the server render, for reduced motion, and as
  // the first paint before the loop takes over the attributes directly.
  const restFrame = useMemo(
    () =>
      omiOrbPlacements({
        motion: reduced ? 'mark' : active,
        turn: 0,
        level: reduced ? 0 : level,
      }),
    // `level` is read only for the very first paint; the loop owns it after.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [active, reduced],
  );

  useEffect(() => {
    if (reduced || paused) return;
    const lap = LAP_SECONDS[active] * 1000;
    let frame = 0;
    let start = 0;

    const tick = (now: number) => {
      if (start === 0) start = now;
      const turn = ((((now - start) / lap) % 1) + 1) % 1;
      for (let i = 0; i < OmiMarkGeometry.dotCount; i++) {
        const node = dots.current[i];
        if (!node) continue;
        const dot = omiDotPlacement({
          motion: active,
          index: i,
          turn,
          level: levelRef.current,
        });
        // Mutating attributes directly keeps the tree from re-rendering 60
        // times a second for what is purely a paint change.
        node.setAttribute('cx', String(centre + dot.offset.x * unit));
        node.setAttribute('cy', String(centre + dot.offset.y * unit));
        node.setAttribute('r', String(OmiMarkGeometry.dotRadius * unit * dot.scale));
        node.setAttribute('opacity', String(Math.max(0, Math.min(1, dot.alpha))));
      }
      frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [active, reduced, paused, centre, unit]);

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className={className}
      role="img"
      aria-label="Omi"
    >
      {restFrame.map((dot, i) => (
        <circle
          key={i}
          ref={(node) => {
            dots.current[i] = node;
          }}
          cx={centre + dot.offset.x * unit}
          cy={centre + dot.offset.y * unit}
          r={OmiMarkGeometry.dotRadius * unit * dot.scale}
          opacity={Math.max(0, Math.min(1, dot.alpha))}
          fill="currentColor"
        />
      ))}
    </svg>
  );
}

export default OmiOrb;
