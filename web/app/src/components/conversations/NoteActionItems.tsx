'use client';

import { cn } from '@/lib/utils';
import type { StructuredActionItem } from '@/types/conversation';
import { noteAvatarToneIndex, noteParticipantInitials } from '@/lib/meetingNotes';

const AVATAR_TONES = [
  'bg-blue-500/15 text-blue-300',
  'bg-emerald-500/15 text-emerald-300',
  'bg-amber-500/15 text-amber-300',
  'bg-slate-500/15 text-slate-300',
  'bg-rose-500/15 text-rose-300',
  'bg-cyan-500/15 text-cyan-300',
];

/**
 * Action item component
 */
export function ActionItemRow({ item }: { item: StructuredActionItem }) {
  const owner = typeof item.owner_name === 'string' ? item.owner_name.trim() : '';
  const context = typeof item.context === 'string' ? item.context.trim() : '';
  const dueDate = item.due_at ? new Date(item.due_at) : null;
  const dueLabel =
    dueDate && !Number.isNaN(dueDate.getTime()) ? dueDate.toLocaleDateString() : '';

  return (
    <li
      className={cn(
        'flex items-start gap-3 rounded-xl p-4',
        'border border-bg-quaternary/50 bg-bg-tertiary',
        item.completed && 'opacity-60',
      )}
    >
      <div
        className={cn(
          'mt-0.5 h-5 w-5 flex-shrink-0 rounded-md border-2',
          'flex items-center justify-center',
          item.completed ? 'border-success bg-success' : 'border-text-quaternary',
        )}
      >
        {item.completed && (
          <svg className="h-3 w-3 text-white" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
              clipRule="evenodd"
            />
          </svg>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <span
          className={cn(
            'text-text-primary',
            item.completed && 'text-text-tertiary line-through',
          )}
        >
          {item.description}
        </span>
        {(owner || context || dueLabel) && (
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-tertiary">
            {owner && (
              <span className="inline-flex items-center gap-1.5">
                <span
                  aria-hidden="true"
                  className={cn(
                    'flex h-4 w-4 items-center justify-center rounded-full text-[8px] font-semibold',
                    AVATAR_TONES[noteAvatarToneIndex(owner) % AVATAR_TONES.length],
                  )}
                >
                  {noteParticipantInitials(owner)}
                </span>
                {owner}
              </span>
            )}
            {context && <span className="max-w-full truncate">{context}</span>}
            {dueLabel && <span>Due: {dueLabel}</span>}
          </div>
        )}
      </div>
    </li>
  );
}

export function NextStepsList({ items }: { items: StructuredActionItem[] }) {
  if (items.length === 0) return null;

  return (
    <section className="mt-8">
      <h2 className="mb-2 text-lg font-semibold text-text-primary">Next steps</h2>
      <ul className="divide-y divide-bg-quaternary/50">
        {items.map((item, index) => {
          const owner = typeof item.owner_name === 'string' ? item.owner_name.trim() : '';
          const context = typeof item.context === 'string' ? item.context.trim() : '';
          const dueDate = item.due_at ? new Date(item.due_at) : null;
          const dueLabel =
            dueDate && !Number.isNaN(dueDate.getTime())
              ? dueDate.toLocaleDateString()
              : '';
          return (
            <li key={index} className="flex items-start gap-3 py-2.5">
              <span
                aria-hidden="true"
                className={cn(
                  'mt-0.5 flex h-4 w-4 flex-shrink-0 items-center justify-center rounded border',
                  item.completed ? 'border-success bg-success' : 'border-text-quaternary',
                )}
              >
                {item.completed && (
                  <svg
                    className="h-2.5 w-2.5 text-white"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                  >
                    <path
                      fillRule="evenodd"
                      d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                      clipRule="evenodd"
                    />
                  </svg>
                )}
              </span>
              <span className="sr-only">
                {item.completed ? 'Completed' : 'Not completed'}
              </span>
              <div className="min-w-0 flex-1">
                <span
                  className={cn(
                    'text-sm text-text-secondary',
                    item.completed && 'text-text-tertiary line-through',
                  )}
                >
                  {item.description}
                </span>
                {(owner || context || dueLabel) && (
                  <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-tertiary">
                    {owner && (
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          aria-hidden="true"
                          className={cn(
                            'flex h-4 w-4 items-center justify-center rounded-full text-[8px] font-semibold',
                            AVATAR_TONES[
                              noteAvatarToneIndex(owner) % AVATAR_TONES.length
                            ],
                          )}
                        >
                          {noteParticipantInitials(owner)}
                        </span>
                        {owner}
                      </span>
                    )}
                    {context && <span className="max-w-full truncate">{context}</span>}
                    {dueLabel && <span>Due: {dueLabel}</span>}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/**
 * Action items tab content
 */
export function ActionItemsTab({ items }: { items: StructuredActionItem[] }) {
  const completedCount = items.filter((i) => i.completed).length;

  return (
    <div className="space-y-4">
      {/* Progress indicator */}
      <div className="flex items-center gap-3 rounded-lg bg-bg-tertiary/50 p-3">
        <div className="flex-1">
          <div className="h-2 overflow-hidden rounded-full bg-bg-quaternary">
            <div
              className="h-full bg-success transition-all duration-300"
              style={{ width: `${(completedCount / items.length) * 100}%` }}
            />
          </div>
        </div>
        <span className="text-sm text-text-tertiary">
          {completedCount}/{items.length} completed
        </span>
      </div>

      {/* Action items list */}
      <ul className="space-y-3">
        {items.map((item, index) => (
          <ActionItemRow key={index} item={item} />
        ))}
      </ul>
    </div>
  );
}
