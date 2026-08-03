'use client';

import { useState } from 'react';
import { Plus, Target } from 'lucide-react';
import { useGoals } from '@/hooks/useGoals';
import { useScores } from '@/hooks/useScores';
import { GoalCard } from './GoalCard';
import { GoalComposer } from './GoalComposer';
import { ScoreSummary } from './ScoreSummary';

export function HomePage() {
  const { goals, loading, error, addGoal, setProgress, removeGoal } = useGoals();
  const { scores, loading: scoresLoading } = useScores();
  const [composerOpen, setComposerOpen] = useState(false);

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-10">
      <header className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-text-primary">Home</h1>
        <button
          type="button"
          onClick={() => setComposerOpen(true)}
          className="flex items-center gap-2 rounded-lg bg-text-primary px-4 py-2 text-sm font-medium text-bg-primary transition-opacity hover:opacity-90"
        >
          <Plus className="h-4 w-4" />
          Set a goal
        </button>
      </header>

      <div className="mt-6">
        <ScoreSummary scores={scores} loading={scoresLoading} />
      </div>

      <section className="mt-8">
        <h2 className="text-sm font-medium uppercase tracking-wide text-text-quaternary">
          Goals
        </h2>

        {error && (
          <p className="mt-4 rounded-lg border border-error/30 bg-error/10 px-4 py-3 text-sm text-error">
            {error}
          </p>
        )}

        {loading && goals.length === 0 ? (
          <div className="mt-4 space-y-3">
            {[0, 1].map((key) => (
              <div
                key={key}
                className="h-32 animate-pulse rounded-xl border border-bg-tertiary bg-bg-secondary"
              />
            ))}
          </div>
        ) : goals.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-bg-tertiary bg-bg-secondary/50 px-6 py-12 text-center">
            <Target className="mx-auto h-8 w-8 text-text-quaternary" />
            <p className="mt-3 font-medium text-text-primary">No goals yet</p>
            <p className="mt-1 text-sm text-text-quaternary">
              Set one and Omi will track progress against it.
            </p>
            <button
              type="button"
              onClick={() => setComposerOpen(true)}
              className="mt-5 rounded-lg bg-text-primary px-4 py-2 text-sm font-medium text-bg-primary transition-opacity hover:opacity-90"
            >
              Set a goal
            </button>
          </div>
        ) : (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {goals.map((goal) => (
              <GoalCard
                key={goal.id}
                goal={goal}
                onSetProgress={setProgress}
                onRemove={removeGoal}
              />
            ))}
          </div>
        )}
      </section>

      <GoalComposer
        open={composerOpen}
        onOpenChange={setComposerOpen}
        onCreate={addGoal}
      />
    </div>
  );
}
