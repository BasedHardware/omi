'use client';

import Link from '@tschk/moonshine-next/link';
import { Check } from 'lucide-react';
import type { ActionItem } from '@/types/conversation';
import { cn } from '@/lib/utils';

/**
 * The middle of the hub: what is actually waiting on you.
 *
 * This is the web read of desktop's `homeKnowsList` (DashboardPage) — the open
 * action items, rendered as plain rows in a 520pt column. Desktop shows no
 * count tiles here and neither does this: a number is a worse answer than the
 * thing itself.
 */

/** Desktop caps the list so the hub stays a glance, not a backlog. */
const VISIBLE = 4;

interface HomeTaskListProps {
  items: ActionItem[];
  loading: boolean;
  error: string | null;
  onComplete: (id: string) => void;
}

export function HomeTaskList({ items, loading, error, onComplete }: HomeTaskListProps) {
  if (loading) {
    return (
      <div className="w-full space-y-2">
        {[0, 1, 2].map((key) => (
          <div key={key} className="h-11 animate-pulse rounded-control bg-bg-raised/60" />
        ))}
      </div>
    );
  }

  if (error) {
    return <p className="text-center text-sm text-error">Could not load tasks.</p>;
  }

  if (items.length === 0) {
    return (
      <p className="text-center text-sm text-text-quaternary">
        Nothing&apos;s waiting on you.
      </p>
    );
  }

  const visible = items.slice(0, VISIBLE);
  const overflow = items.length - visible.length;

  return (
    <div className="w-full">
      <ul className="space-y-1">
        {visible.map((item) => (
          <li key={item.id}>
            <div
              className={cn(
                'group flex items-center gap-3 rounded-control px-3 py-2.5',
                'transition-colors hover:bg-bg-raised/70',
              )}
            >
              <button
                type="button"
                onClick={() => onComplete(item.id)}
                aria-label={`Complete: ${item.description}`}
                className={cn(
                  'flex h-[18px] w-[18px] flex-shrink-0 items-center justify-center',
                  'rounded-full border border-stroke text-transparent',
                  'transition-colors hover:border-text-primary hover:text-text-primary',
                )}
              >
                <Check className="h-3 w-3" strokeWidth={3} />
              </button>
              <Link
                href="/tasks"
                className="min-w-0 flex-1 truncate text-sm text-text-secondary transition-colors group-hover:text-text-primary"
              >
                {item.description}
              </Link>
            </div>
          </li>
        ))}
      </ul>

      {overflow > 0 && (
        <Link
          href="/tasks"
          className="mt-2 block px-3 text-xs text-text-quaternary transition-colors hover:text-text-secondary"
        >
          {overflow} more in Tasks
        </Link>
      )}
    </div>
  );
}
