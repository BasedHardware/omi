'use client';

import { useState } from 'react';
import { Check, Minus, Plus, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  formatGoalMetric,
  formatMetricValue,
  goalProgressPercent,
  isGoalComplete,
} from '@/lib/goals';
import type { Goal } from '@/types/goals';

interface GoalCardProps {
  goal: Goal;
  onSetProgress: (id: string, currentValue: number) => Promise<void>;
  onRemove: (id: string) => Promise<void>;
  onOpen: (goal: Goal) => void;
}

export function GoalCard({ goal, onSetProgress, onRemove, onOpen }: GoalCardProps) {
  const [draft, setDraft] = useState(() => formatMetricValue(goal.current_value));
  const [lastKnownValue, setLastKnownValue] = useState(goal.current_value);
  const percent = goalProgressPercent(goal);
  const complete = isGoalComplete(goal);
  const isBoolean = goal.goal_type === 'boolean';

  // Follow server-confirmed values, including a rolled-back optimistic write.
  // Adjusting during render rather than in an effect avoids rendering the stale
  // value for a frame first.
  if (goal.current_value !== lastKnownValue) {
    setLastKnownValue(goal.current_value);
    setDraft(formatMetricValue(goal.current_value));
  }

  const commit = (value: number) => {
    if (value === goal.current_value) return;
    void onSetProgress(goal.id, value);
  };

  const step = (delta: number) => {
    commit(Math.max(goal.min_value, goal.current_value + delta));
  };

  return (
    <article className="rounded-card border border-stroke bg-bg-raised p-5 transition-colors hover:border-text-quaternary/40">
      <div className="flex items-start justify-between gap-4">
        <button
          type="button"
          onClick={() => onOpen(goal)}
          className="min-w-0 flex-1 text-left"
        >
          <h3 className="truncate font-medium text-text-primary hover:underline">
            {goal.title}
          </h3>
          <p className="mt-1 text-sm text-text-quaternary">{formatGoalMetric(goal)}</p>
        </button>

        <button
          type="button"
          onClick={() => void onRemove(goal.id)}
          aria-label={`Delete goal ${goal.title}`}
          className="rounded-control p-2 text-text-quaternary transition-colors hover:bg-bg-tertiary hover:text-error"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-bg-tertiary">
        <div
          role="progressbar"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${goal.title} progress`}
          className={cn(
            'h-full rounded-full transition-all',
            complete ? 'bg-success' : 'bg-text-secondary',
          )}
          style={{ width: `${percent}%` }}
        />
      </div>

      <div className="mt-4 flex items-center justify-between gap-3">
        <span className="text-xs text-text-quaternary">{percent}%</span>

        {isBoolean ? (
          <button
            type="button"
            onClick={() => commit(complete ? goal.min_value : goal.target_value)}
            className={cn(
              'flex items-center gap-2 rounded-chip px-3 py-1.5 text-xs transition-colors',
              complete
                ? 'bg-success/10 text-success'
                : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary',
            )}
          >
            <Check className="h-3.5 w-3.5" />
            {complete ? 'Done' : 'Mark done'}
          </button>
        ) : (
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => step(-1)}
              aria-label={`Decrease ${goal.title}`}
              disabled={goal.current_value <= goal.min_value}
              className="rounded-element bg-bg-tertiary p-1.5 text-text-secondary transition-colors hover:bg-bg-quaternary disabled:opacity-40"
            >
              <Minus className="h-3.5 w-3.5" />
            </button>

            <input
              type="number"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onBlur={() => {
                // Number('') is 0, so an emptied field would otherwise wipe
                // progress to zero on blur rather than reverting.
                const parsed = draft.trim() === '' ? NaN : Number(draft);
                if (Number.isFinite(parsed)) {
                  commit(parsed);
                } else {
                  setDraft(formatMetricValue(goal.current_value));
                }
              }}
              aria-label={`${goal.title} current value`}
              className="w-16 rounded-element bg-bg-tertiary px-2 py-1 text-center text-xs text-text-primary outline-none focus:ring-1 focus:ring-text-quaternary"
            />

            <button
              type="button"
              onClick={() => step(1)}
              aria-label={`Increase ${goal.title}`}
              className="rounded-element bg-bg-tertiary p-1.5 text-text-secondary transition-colors hover:bg-bg-quaternary"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>
    </article>
  );
}
