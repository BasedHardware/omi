'use client';

import { cn } from '@/lib/utils';
import type { StructuredActionItem } from '@/types/conversation';

/**
 * Action item component
 */
function ActionItemRow({ item }: { item: StructuredActionItem }) {
  return (
    <div
      className={cn(
        'flex items-start gap-3 p-4 rounded-xl',
        'bg-bg-tertiary border border-bg-quaternary/50',
        item.completed && 'opacity-60',
      )}
    >
      <div
        className={cn(
          'w-5 h-5 rounded-md border-2 flex-shrink-0 mt-0.5',
          'flex items-center justify-center',
          item.completed ? 'bg-success border-success' : 'border-text-quaternary',
        )}
      >
        {item.completed && (
          <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
              clipRule="evenodd"
            />
          </svg>
        )}
      </div>
      <div className="flex-1">
        <span
          className={cn(
            'text-text-primary',
            item.completed && 'line-through text-text-tertiary',
          )}
        >
          {item.description}
        </span>
        {item.due_at && (
          <p className="text-xs text-text-quaternary mt-1">
            Due: {new Date(item.due_at).toLocaleDateString()}
          </p>
        )}
      </div>
    </div>
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
      <div className="flex items-center gap-3 p-3 rounded-lg bg-bg-tertiary/50">
        <div className="flex-1">
          <div className="h-2 bg-bg-quaternary rounded-full overflow-hidden">
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
      <div className="space-y-3">
        {items.map((item, index) => (
          <ActionItemRow key={index} item={item} />
        ))}
      </div>
    </div>
  );
}
