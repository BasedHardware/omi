'use client';

import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import type { CreateGoalParams } from '@/lib/api';

interface GoalComposerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (params: CreateGoalParams) => Promise<unknown>;
}

export function GoalComposer({ open, onOpenChange, onCreate }: GoalComposerProps) {
  const [title, setTitle] = useState('');
  const [target, setTarget] = useState('');
  const [unit, setUnit] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setTitle('');
    setTarget('');
    setUnit('');
    setError(null);
  };

  const close = (next: boolean) => {
    if (!next) reset();
    onOpenChange(next);
  };

  // Desktop defaults a blank or invalid target to 1, so a title-only goal still
  // creates as a yes/no-style goal that completes on one tick.
  const parsedTarget = Number(target);
  const targetValue =
    Number.isFinite(parsedTarget) && parsedTarget > 0 ? parsedTarget : 1;
  const canSubmit = title.trim().length > 0 && !submitting;

  const submit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);

    const created = await onCreate({
      title: title.trim(),
      target_value: targetValue,
      ...(unit.trim() ? { unit: unit.trim() } : {}),
    });

    setSubmitting(false);

    if (created) {
      close(false);
    } else {
      setError('Could not save that goal. Try again.');
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={close}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-card border border-stroke bg-bg-raised p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="text-lg font-semibold text-text-primary">
                Set a goal
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-text-quaternary">
                Omi tracks progress against it as you go.
              </Dialog.Description>
            </div>
            <Dialog.Close
              aria-label="Close"
              className="rounded-element p-1.5 text-text-quaternary transition-colors hover:bg-bg-tertiary hover:text-text-primary"
            >
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>

          <div className="mt-5 space-y-4">
            <label className="block">
              <span className="text-xs uppercase tracking-wide text-text-quaternary">
                Goal
              </span>
              <input
                autoFocus
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void submit();
                }}
                placeholder="Read 12 books this year"
                maxLength={500}
                className="mt-1.5 w-full rounded-control bg-bg-tertiary px-3 py-2 text-sm text-text-primary outline-none placeholder:text-text-quaternary focus:ring-1 focus:ring-text-quaternary"
              />
            </label>

            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="text-xs uppercase tracking-wide text-text-quaternary">
                  Target
                </span>
                <input
                  type="number"
                  value={target}
                  onChange={(event) => setTarget(event.target.value)}
                  min={1}
                  className="mt-1.5 w-full rounded-control bg-bg-tertiary px-3 py-2 text-sm text-text-primary outline-none focus:ring-1 focus:ring-text-quaternary"
                />
              </label>
              <label className="block">
                <span className="text-xs uppercase tracking-wide text-text-quaternary">
                  Unit
                </span>
                <input
                  value={unit}
                  onChange={(event) => setUnit(event.target.value)}
                  placeholder="books"
                  maxLength={64}
                  className="mt-1.5 w-full rounded-control bg-bg-tertiary px-3 py-2 text-sm text-text-primary outline-none placeholder:text-text-quaternary focus:ring-1 focus:ring-text-quaternary"
                />
              </label>
            </div>

            {error && <p className="text-sm text-error">{error}</p>}
          </div>

          <div className="mt-6 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => close(false)}
              className="rounded-control px-4 py-2 text-sm text-text-quaternary transition-colors hover:text-text-secondary"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void submit()}
              disabled={!canSubmit}
              className="rounded-control bg-text-primary px-4 py-2 text-sm font-medium text-bg-primary transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              {submitting ? 'Saving…' : 'Set goal'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
