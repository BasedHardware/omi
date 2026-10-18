'use client';

import { useState } from 'react';
import { Play } from 'lucide-react';

export function formatQuoteTimestamp(start: number): string {
  const total = Math.floor(start);
  const seconds = String(total % 60).padStart(2, '0');
  const minutes = Math.floor(total / 60) % 60;
  const hours = Math.floor(total / 3600);
  return hours
    ? `${hours}:${String(minutes).padStart(2, '0')}:${seconds}`
    : `${minutes}:${seconds}`;
}

// This client currently ships English UI. Intl supplies spoken, pluralized units.
export function quoteTimestampLabel(start: number): string {
  const total = Math.floor(start);
  const units = [
    ['hour', Math.floor(total / 3600)],
    ['minute', Math.floor(total / 60) % 60],
    ['second', total % 60],
  ] as const;
  const duration = units
    .filter(([unit, value]) => value || unit === 'second')
    .map(([unit, value]) =>
      new Intl.NumberFormat('en', { style: 'unit', unit, unitDisplay: 'long' }).format(
        value,
      ),
    )
    .join(' ');
  return `Jump to ${duration}`;
}

export function QuoteTimestamps({
  sources,
  onOpenSource,
}: {
  sources: { id: string; start: number }[];
  onOpenSource: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? sources : sources.slice(0, 3);
  if (!sources.length) return null;
  const linkClass =
    'rounded-sm py-1 hover:text-text-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2';
  return (
    <div
      className="mt-2 flex flex-wrap items-center gap-x-1.5 text-xs tabular-nums text-text-tertiary"
      aria-label="Transcript sources"
    >
      {visible.map((source, index) => (
        <span key={source.id} className="inline-flex items-center gap-1.5">
          {index === 0 ? (
            <Play aria-hidden="true" className="h-3 w-3" />
          ) : (
            <span aria-hidden="true">·</span>
          )}
          <button
            type="button"
            className={linkClass}
            aria-label={quoteTimestampLabel(source.start)}
            onClick={() => onOpenSource(source.id)}
          >
            {formatQuoteTimestamp(source.start)}
          </button>
        </span>
      ))}
      {sources.length > 3 && (
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true">·</span>
          <button
            type="button"
            className={linkClass}
            aria-expanded={expanded}
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? 'Show less' : `+${sources.length - 3} more`}
          </button>
        </span>
      )}
    </div>
  );
}
