'use client';

import Link from '@tschk/moonshine-next/link';
import { Brain, GanttChartSquare, ListChecks } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * The hub's stat ribbon, ported from the Electron desktop app
 * (`components/home/hub/HubStatRibbon.tsx`, itself the macOS DashboardPage
 * ribbon). Purely presentational: counts are passed in, so it has no opinion
 * about where they come from.
 *
 * Desktop has a fourth Screenshots cell linking to Rewind. Web has no Rewind —
 * it needs screen capture — so this is three cells.
 */

export interface HubStatCounts {
  /** null means "not loaded yet". */
  conversations: number | null;
  /**
   * The conversations source is capped at one page, so a full page only proves
   * a floor and renders as "100+".
   */
  conversationsAtLeast: boolean;
  tasks: number | null;
  memories: number | null;
}

interface Cell {
  key: 'conversations' | 'tasks' | 'memories';
  label: string;
  Icon: LucideIcon;
  href: string;
}

const CELLS: Cell[] = [
  {
    key: 'conversations',
    label: 'Conversations',
    Icon: GanttChartSquare,
    href: '/conversations',
  },
  { key: 'tasks', label: 'Tasks', Icon: ListChecks, href: '/tasks' },
  { key: 'memories', label: 'Memories', Icon: Brain, href: '/memories' },
];

export function HubStatRibbon({ counts }: { counts: HubStatCounts }) {
  return (
    <div
      className={cn(
        'flex h-[76px] w-full overflow-hidden rounded-card border border-stroke',
        'bg-bg-raised',
      )}
    >
      {CELLS.map(({ key, label, Icon, href }, index) => {
        const count = counts[key];
        // An em-dash means unknown. A zero is a claim about the user's data, and
        // it is only made once the count has actually loaded.
        const display =
          count === null
            ? '—'
            : key === 'conversations' && counts.conversationsAtLeast
              ? `${count}+`
              : `${count}`;

        return (
          <Link
            key={key}
            href={href}
            aria-label={`${label}: ${display}`}
            className={cn(
              'flex flex-1 flex-col items-center justify-center border-stroke',
              'px-[10px] py-[13px] text-text-tertiary transition-colors duration-150',
              'hover:bg-bg-quaternary hover:text-text-primary',
              index > 0 && 'border-l',
            )}
          >
            <span className="flex items-center gap-1.5">
              <Icon className="h-[11px] w-[11px] shrink-0" strokeWidth={2.5} />
              {/* tabular-nums so the cells do not jitter as counts land. */}
              <span className="font-display text-[22px] font-semibold leading-none tabular-nums">
                {display}
              </span>
            </span>
            <span className="mt-1.5 text-[11px] font-medium leading-none">{label}</span>
          </Link>
        );
      })}
    </div>
  );
}
