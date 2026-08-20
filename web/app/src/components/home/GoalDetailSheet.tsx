'use client';

import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Sparkles, X } from 'lucide-react';
import { useGoalDetail } from '@/hooks/useGoalDetail';
import { formatMetricValue, historyDelta, progressLabel } from '@/lib/goals';
import type { UpdateGoalParams } from '@/lib/api';
import type { Goal } from '@/types/goals';
import { GoalSparkline } from './GoalSparkline';

interface GoalDetailSheetProps {
  goal: Goal | null;
  onClose: () => void;
  onSave: (id: string, updates: UpdateGoalParams) => Promise<boolean>;
}

export function GoalDetailSheet({ goal, onClose, onSave }: GoalDetailSheetProps) {
  const detail = useGoalDetail(goal?.id ?? null);
  const [title, setTitle] = useState('');
  const [target, setTarget] = useState('');
  const [unit, setUnit] = useState('');
  const [saving, setSaving] = useState(false);
  const [editedGoalId, setEditedGoalId] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Reset the edit fields whenever a different goal is opened. Adjusting during
  // render rather than in an effect avoids showing the previous goal's values
  // for a frame.
  if (goal && goal.id !== editedGoalId) {
    setEditedGoalId(goal.id);
    setTitle(goal.title);
    setTarget(formatMetricValue(goal.target_value));
    setUnit(goal.unit ?? '');
    setSaving(false);
    setSaveError(null);
  } else if (!goal && editedGoalId !== null) {
    setEditedGoalId(null);
    setTitle('');
    setTarget('');
    setUnit('');
    setSaving(false);
    setSaveError(null);
  }

  if (!goal) return null;

  const isBoolean = goal.goal_type === 'boolean';
  const targetValue = Number(target);
  const targetChanged = !isBoolean && targetValue !== goal.target_value;
  const dirty =
    title.trim() !== goal.title || targetChanged || unit.trim() !== (goal.unit ?? '');
  const targetValid = isBoolean || (Number.isFinite(targetValue) && targetValue > 0);
  const canSave = dirty && title.trim().length > 0 && targetValid && !saving;

  const close = () => {
    setEditedGoalId(null);
    setTitle('');
    setTarget('');
    setUnit('');
    setSaveError(null);
    onClose();
  };

  const save = async () => {
    if (!canSave) return;
    setSaving(true);
    setSaveError(null);

    // Send only what changed; the backend rejects an empty update with a 400.
    const updates: UpdateGoalParams = {};
    if (title.trim() !== goal.title) updates.title = title.trim();
    if (targetChanged) updates.target_value = targetValue;
    if (unit.trim() !== (goal.unit ?? '')) updates.unit = unit.trim() || null;

    try {
      const success = await onSave(goal.id, updates);
      if (!success) {
        setSaveError('Could not save this goal. Please try again.');
        setSaving(false);
        return;
      }
      setSaving(false);
      close();
    } catch {
      setSaveError('Could not save this goal. Please try again.');
      setSaving(false);
    }
  };

  const delta = historyDelta(detail.history);

  return (
    <Dialog.Root open onOpenChange={(next) => !next && close()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[85vh] w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-card border border-stroke bg-bg-raised p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <Dialog.Title className="truncate text-lg font-semibold text-text-primary">
                {goal.title}
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-text-quaternary">
                {progressLabel(goal)}
              </Dialog.Description>
            </div>
            <Dialog.Close
              aria-label="Close"
              className="rounded-element p-1.5 text-text-quaternary transition-colors hover:bg-bg-tertiary hover:text-text-primary"
            >
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>

          <section className="mt-6">
            <h3 className="text-xs uppercase tracking-wide text-text-quaternary">
              Last 30 days
            </h3>
            <div className="mt-2">
              {detail.historyLoading ? (
                <div className="h-14 animate-pulse rounded-control bg-bg-tertiary" />
              ) : detail.historyError ? (
                <p className="text-sm text-error">{detail.historyError}</p>
              ) : (
                <>
                  <GoalSparkline history={detail.history} label={goal.title} />
                  {delta !== null && (
                    <p className="mt-1 text-xs text-text-quaternary">
                      {delta >= 0 ? '+' : ''}
                      {formatMetricValue(delta)} over the recorded window
                    </p>
                  )}
                </>
              )}
            </div>
          </section>

          <section className="mt-6">
            <h3 className="text-xs uppercase tracking-wide text-text-quaternary">
              Advice
            </h3>
            {detail.advice ? (
              <p className="mt-2 whitespace-pre-wrap text-sm text-text-secondary">
                {detail.advice}
              </p>
            ) : (
              <div className="mt-2">
                <button
                  type="button"
                  onClick={() => void detail.requestAdvice()}
                  disabled={detail.adviceLoading}
                  className="flex items-center gap-2 rounded-control bg-bg-tertiary px-3 py-2 text-xs text-text-secondary transition-colors hover:bg-bg-quaternary disabled:opacity-50"
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  {detail.adviceLoading ? 'Thinking…' : 'Get advice'}
                </button>
                {detail.adviceError && (
                  <p className="mt-2 text-sm text-error">{detail.adviceError}</p>
                )}
              </div>
            )}
          </section>

          <section className="mt-6 border-t border-stroke pt-6">
            <h3 className="text-xs uppercase tracking-wide text-text-quaternary">Edit</h3>
            <div className="mt-2 space-y-3">
              <label className="block">
                <span className="sr-only">Title</span>
                <input
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  aria-label="Title"
                  maxLength={500}
                  className="w-full rounded-control bg-bg-tertiary px-3 py-2 text-sm text-text-primary outline-none focus:ring-1 focus:ring-text-quaternary"
                />
              </label>

              {!isBoolean && (
                <div className="grid grid-cols-2 gap-3">
                  <input
                    type="number"
                    value={target}
                    onChange={(event) => setTarget(event.target.value)}
                    aria-label="Target"
                    min={1}
                    className="w-full rounded-control bg-bg-tertiary px-3 py-2 text-sm text-text-primary outline-none focus:ring-1 focus:ring-text-quaternary"
                  />
                  <input
                    value={unit}
                    onChange={(event) => setUnit(event.target.value)}
                    aria-label="Unit"
                    placeholder="unit"
                    maxLength={64}
                    className="w-full rounded-control bg-bg-tertiary px-3 py-2 text-sm text-text-primary outline-none placeholder:text-text-quaternary focus:ring-1 focus:ring-text-quaternary"
                  />
                </div>
              )}
            </div>

            <div className="mt-4 flex justify-end">
              <button
                type="button"
                onClick={() => void save()}
                disabled={!canSave}
                className="rounded-control bg-text-primary px-4 py-2 text-sm font-medium text-bg-primary transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                {saving ? 'Saving…' : 'Save changes'}
              </button>
            </div>
            {saveError && <p className="mt-2 text-sm text-error">{saveError}</p>}
          </section>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
