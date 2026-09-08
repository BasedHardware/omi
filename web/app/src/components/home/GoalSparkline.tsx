'use client';

import { sparklinePoints } from '@/lib/goals';
import type { GoalHistoryEntry } from '@/types/goals';

const WIDTH = 280;
const HEIGHT = 56;
const PADDING = 4;

interface GoalSparklineProps {
  history: GoalHistoryEntry[];
  label: string;
}

export function GoalSparkline({ history, label }: GoalSparklineProps) {
  const points = sparklinePoints(history);

  if (points.length < 2) {
    return (
      <p className="text-sm text-text-quaternary">Not enough history to chart yet.</p>
    );
  }

  const path = points
    .map(({ x, y }, index) => {
      const px = PADDING + x * (WIDTH - PADDING * 2);
      const py = PADDING + y * (HEIGHT - PADDING * 2);
      return `${index === 0 ? 'M' : 'L'} ${px.toFixed(1)} ${py.toFixed(1)}`;
    })
    .join(' ');

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className="h-14 w-full"
      role="img"
      aria-label={`${label} progress over time`}
      preserveAspectRatio="none"
    >
      <path
        d={path}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-text-secondary"
      />
    </svg>
  );
}
