'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  OmiMarkGeometry,
  omiBurstForTurn,
  omiDotPlacement,
  omiMotionForState,
  omiOrbPlacements,
  smoothOmiLevel,
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

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function')
    return false;
  return window.matchMedia(REDUCED_MOTION_QUERY).matches;
}

/**
 * Tracks the preference rather than sampling it once: a reader who turns
 * reduced motion on mid-session is asking the animation already on screen to
 * stop, and a value read at mount can never answer that.
 */
function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(prefersReducedMotion);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const query = window.matchMedia(REDUCED_MOTION_QUERY);
    const update = () => setReduced(query.matches);
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  return reduced;
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
  const reduced = useReducedMotion();
  const usesCompositorPulse = active === 'pulse';

  const dots = useRef<(SVGCircleElement | null)[]>([]);
  const levelRef = useRef(level);
  const smoothedLevelRef = useRef(level);
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
    let previous = 0;

    const tick = (now: number) => {
      if (start === 0) start = now;
      const elapsed = previous === 0 ? 1000 / 60 : now - previous;
      previous = now;
      smoothedLevelRef.current = smoothOmiLevel(
        smoothedLevelRef.current,
        levelRef.current,
        elapsed,
      );
      const turn = ((((now - start) / lap) % 1) + 1) % 1;
      for (let i = 0; i < OmiMarkGeometry.dotCount; i++) {
        const node = dots.current[i];
        if (!node) continue;
        const dot = omiDotPlacement({
          motion: active,
          index: i,
          turn,
          level: smoothedLevelRef.current,
          burst: omiBurstForTurn(active, turn),
        });
        if (usesCompositorPulse) {
          node.style.transform = `scale(${dot.scale})`;
          node.style.opacity = String(Math.max(0, Math.min(1, dot.alpha)));
          continue;
        }
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
  }, [active, reduced, paused, centre, unit, usesCompositorPulse]);

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className={className}
      role="img"
      aria-label="Omi"
    >
      {restFrame.map((dot, i) => {
        const opacity = Math.max(0, Math.min(1, dot.alpha));
        return (
          <circle
            key={i}
            ref={(node) => {
              dots.current[i] = node;
            }}
            cx={centre + dot.offset.x * unit}
            cy={centre + dot.offset.y * unit}
            r={OmiMarkGeometry.dotRadius * unit * (usesCompositorPulse ? 1 : dot.scale)}
            opacity={usesCompositorPulse ? undefined : opacity}
            fill="currentColor"
            style={
              usesCompositorPulse
                ? {
                    opacity,
                    transform: `scale(${dot.scale})`,
                    transformBox: 'fill-box',
                    transformOrigin: 'center',
                  }
                : undefined
            }
          />
        );
      })}
    </svg>
  );
}

export default OmiOrb;
