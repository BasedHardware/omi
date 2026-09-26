'use client';

import { motion, useReducedMotion } from 'framer-motion';
import { OmiMarkGeometry } from '@/lib/omiOrb';

interface OmiPulseMarkProps {
  size: number;
  level?: number;
  active?: boolean;
  label?: string;
  testId?: string;
}

export function OmiPulseMark({
  size,
  level = 0,
  active = false,
  label = 'Omi',
  testId,
}: OmiPulseMarkProps) {
  const reducedMotion = useReducedMotion();
  const activity = Math.min(1, Math.max(0, level));
  const pulseMaximum = 1.02 + activity * 0.05;
  const pulses = active && !reducedMotion;

  return (
    <motion.div
      className="flex flex-shrink-0 items-center justify-center"
      style={{ width: size, height: size }}
      animate={{ scale: pulses ? [0.94, pulseMaximum, 0.94] : 1 }}
      transition={
        pulses
          ? { duration: 1.5 - activity * 0.4, ease: 'easeInOut', repeat: Infinity }
          : { duration: reducedMotion ? 0 : 0.16, ease: 'easeOut' }
      }
      data-testid={testId}
      data-pulse-min={pulses ? 0.94 : 1}
      data-pulse-max={pulses ? pulseMaximum : 1}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${OmiMarkGeometry.canvas} ${OmiMarkGeometry.canvas}`}
        className="text-text-primary"
        role="img"
        aria-label={label}
      >
        {Array.from({ length: OmiMarkGeometry.dotCount }, (_, index) => {
          const rest = OmiMarkGeometry.restOf(index);
          return (
            <circle
              key={index}
              cx={OmiMarkGeometry.centre + rest.x}
              cy={OmiMarkGeometry.centre + rest.y}
              r={OmiMarkGeometry.dotRadius}
              fill="currentColor"
            />
          );
        })}
      </svg>
    </motion.div>
  );
}
