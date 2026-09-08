'use client';

import { useState } from 'react';
import { Check, Lightbulb, Trash2 } from 'lucide-react';
import { goalEmoji } from '@/lib/goalEmoji';
import {
  isCompleted,
  progressColor,
  progressLabel,
  progressPct,
} from '@/lib/goalVisuals';
import type { Goal } from '@/types/goals';

interface GoalCardProps {
  goal: Goal;
  onSetProgress: (id: string, currentValue: number) => Promise<boolean | void>;
  onRename: (id: string, title: string) => Promise<boolean | void>;
  onRemove: (id: string) => Promise<boolean | void>;
  onOpen: (goal: Goal) => void;
}

/**
 * Ported from the Electron desktop app's Goals card
 * (`desktop/windows/src/renderer/src/pages/Goals.tsx`, `renderCard`): the same
 * completion checkbox, title-derived emoji tile, threshold-ramp progress bar,
 * inline-editable title and progress value, and hover-revealed actions.
 */
export function GoalCard({
  goal,
  onSetProgress,
  onRename,
  onRemove,
  onOpen,
}: GoalCardProps) {
  const [titleDraft, setTitleDraft] = useState<string | null>(null);
  const [progressDraft, setProgressDraft] = useState<string | null>(null);

  const done = isCompleted(goal);
  const pct = progressPct(goal);
  const target = goal.target_value ?? 0;

  const commitTitle = () => {
    const next = (titleDraft ?? '').trim();
    setTitleDraft(null);
    if (next && next !== goal.title) void onRename(goal.id, next);
  };

  const commitProgress = () => {
    const raw = progressDraft ?? '';
    setProgressDraft(null);
    // Number('') is 0, so an emptied field would wipe progress rather than
    // reverting.
    const parsed = raw.trim() === '' ? NaN : Number(raw);
    if (Number.isFinite(parsed) && parsed !== goal.current_value) {
      void onSetProgress(goal.id, parsed);
    }
  };

  /** Toggle completion the only way the backend supports: drive the value. */
  const toggleComplete = () => {
    if (target <= 0) return;
    void onSetProgress(goal.id, done ? 0 : target);
  };

  return (
    <li className="surface-card group p-4">
      <div className="flex items-start gap-3">
        <button
          type="button"
          onClick={toggleComplete}
          disabled={target <= 0}
          aria-label={done ? 'Reopen goal' : 'Mark as complete'}
          className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-all duration-200 ${
            done
              ? 'border-white/30 bg-white/15 text-white'
              : 'border-white/20 hover:border-white/45'
          } ${target <= 0 ? 'opacity-40' : ''}`}
        >
          {done && <Check className="h-3.5 w-3.5" />}
        </button>

        {/* Category glyph auto-derived from the title, shared with desktop. */}
        <div
          className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/10 text-[18px] leading-none ${
            done ? 'opacity-50' : ''
          }`}
          aria-hidden="true"
        >
          {goalEmoji(goal.title)}
        </div>

        <div className="min-w-0 flex-1">
          {titleDraft !== null ? (
            <input
              autoFocus
              value={titleDraft}
              aria-label={`${goal.title} title`}
              onChange={(event) => setTitleDraft(event.target.value)}
              onBlur={commitTitle}
              onKeyDown={(event) => {
                if (event.key === 'Enter') commitTitle();
                else if (event.key === 'Escape') setTitleDraft(null);
              }}
              className="w-full border-0 border-b border-white/25 bg-transparent pb-0.5 text-sm text-white focus:border-white/60 focus:outline-none focus:ring-0"
            />
          ) : (
            <button
              type="button"
              onClick={() => setTitleDraft(goal.title)}
              title="Click to edit"
              className={`block w-full text-left text-sm font-medium leading-relaxed ${
                done ? 'text-white/40 line-through' : 'text-white/90'
              }`}
            >
              {goal.title}
            </button>
          )}

          <div className="mt-2.5">
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
              <div
                role="progressbar"
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${goal.title} progress`}
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${pct}%`, backgroundColor: progressColor(pct / 100) }}
              />
            </div>
            <div className="mt-1.5 flex items-center gap-2 text-[11px] text-white/45">
              {progressDraft !== null ? (
                <input
                  type="number"
                  autoFocus
                  min={0}
                  value={progressDraft}
                  aria-label={`${goal.title} current value`}
                  onChange={(event) => setProgressDraft(event.target.value)}
                  onBlur={commitProgress}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') commitProgress();
                    else if (event.key === 'Escape') setProgressDraft(null);
                  }}
                  className="w-20 rounded-md border border-white/20 bg-black/30 px-1.5 py-0.5 text-[11px] text-white [color-scheme:dark] focus:border-white/50 focus:outline-none"
                />
              ) : (
                <button
                  type="button"
                  onClick={() => setProgressDraft(String(goal.current_value ?? 0))}
                  className="rounded-md px-1.5 py-0.5 transition-colors hover:bg-white/5 hover:text-white/70"
                  title="Update progress"
                >
                  {progressLabel(goal)}
                </button>
              )}
              {!done && pct > 0 && <span className="text-white/30">{pct}%</span>}
            </div>
          </div>
        </div>

        <div className="mt-0.5 flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
          {/* Insight needs a real target; a 0-target yes/no goal gives the
              advice model little to reason about. Matches desktop. */}
          {target > 0 && (
            <button
              type="button"
              onClick={() => onOpen(goal)}
              className="rounded-md p-1 text-white/30 transition-colors hover:bg-white/5 hover:text-white/70"
              title="Get goal insight"
              aria-label={`Get goal insight for ${goal.title}`}
            >
              <Lightbulb className="h-4 w-4" />
            </button>
          )}
          <button
            type="button"
            onClick={() => void onRemove(goal.id)}
            className="rounded-md p-1 text-white/30 transition-colors hover:bg-white/5 hover:text-rose-300/80"
            title="Delete goal"
            aria-label={`Delete goal ${goal.title}`}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
    </li>
  );
}
