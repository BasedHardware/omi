'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { describeScorePeriod, resolveDefaultTab } from '@/lib/scores';
import type { ScoreTab, Scores } from '@/types/scores';

const TABS: Array<{ id: ScoreTab; label: string }> = [
  { id: 'daily', label: 'Today' },
  { id: 'weekly', label: 'This week' },
  { id: 'overall', label: 'All time' },
];

interface ScoreSummaryProps {
  scores: Scores | null;
  loading: boolean;
}

export function ScoreSummary({ scores, loading }: ScoreSummaryProps) {
  const [tab, setTab] = useState<ScoreTab | null>(null);
  const activeTab = tab ?? (scores ? resolveDefaultTab(scores) : 'daily');
  const period = scores?.[activeTab] ?? null;

  return (
    <section className="rounded-card border border-stroke bg-bg-raised p-6">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-sm font-medium uppercase tracking-wide text-text-quaternary">
          Score
        </h2>
        <div className="flex gap-1 rounded-control bg-bg-tertiary p-1">
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              aria-pressed={activeTab === id}
              className={cn(
                'rounded-chip px-3 py-1.5 text-xs transition-colors',
                activeTab === id
                  ? 'bg-bg-quaternary text-text-primary'
                  : 'text-text-quaternary hover:text-text-secondary',
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {loading && !scores ? (
        <div className="mt-6 h-12 w-32 animate-pulse rounded-control bg-bg-tertiary" />
      ) : period ? (
        <div className="mt-6 flex items-end gap-3">
          <span className="text-5xl font-semibold leading-none text-text-primary">
            {Math.round(period.score)}
          </span>
          <span className="pb-1 text-sm text-text-quaternary">
            {describeScorePeriod(period)}
          </span>
        </div>
      ) : (
        <p className="mt-6 text-sm text-text-quaternary">Score unavailable.</p>
      )}
    </section>
  );
}
