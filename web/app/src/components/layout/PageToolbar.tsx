'use client';

import type { ReactNode } from 'react';
import { Search, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Input } from '@/components/ui/input';

export interface PageToolbarSearch {
  value: string;
  onChange: (value: string) => void;
  /** Called on Enter and on clear, with the value being submitted. */
  onSubmit?: (value: string) => void;
  placeholder?: string;
}

export interface PageToolbarProps {
  /** View controls — tabs, filters, select mode. Rendered left. */
  controls?: ReactNode;
  /** Page actions — create, export. Rendered right of the search field. */
  actions?: ReactNode;
  search?: PageToolbarSearch;
  /** Secondary row: active filter chips, inline bulk-action bars. */
  below?: ReactNode;
  className?: string;
}

/**
 * The single top row every page uses. It deliberately renders no title: the
 * sidebar is the only place that names the current page, so Conversations, Memories,
 * Tasks and Connectors line up by construction instead of by coincidence.
 */
export function PageToolbar({
  controls,
  actions,
  search,
  below,
  className,
}: PageToolbarProps) {
  return (
    <div
      className={cn('flex-shrink-0 border-b border-stroke bg-bg-secondary', className)}
    >
      {/* Mobile stacks the row: controls scroll horizontally instead of
          squeezing, and the search field gets its own full-width line. Desktop
          keeps the single row. Without this, wide controls (folder tabs, view
          toggles) plus the fixed-width search overflow a phone viewport. */}
      <div className="flex flex-col gap-2.5 px-4 py-3 sm:flex-row sm:items-center sm:gap-3">
        {controls && (
          <div className="no-scrollbar flex min-w-0 items-center gap-3 overflow-x-auto">
            {controls}
          </div>
        )}

        <div
          className={cn(
            'flex min-w-0 items-center gap-2',
            'w-full sm:ml-auto sm:w-auto sm:flex-shrink-0',
          )}
        >
          {search && (
            <div className="relative w-full min-w-0 sm:w-52 lg:w-64">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-quaternary" />
              <Input
                type="text"
                value={search.value}
                onChange={(e) => search.onChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') search.onSubmit?.(search.value);
                }}
                placeholder={search.placeholder ?? 'Search'}
                aria-label={search.placeholder ?? 'Search'}
                className="pl-9 pr-8"
              />
              {search.value && (
                <button
                  type="button"
                  onClick={() => {
                    search.onChange('');
                    search.onSubmit?.('');
                  }}
                  aria-label="Clear search"
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-element p-1 text-text-tertiary transition-colors hover:bg-bg-quaternary hover:text-text-primary"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          )}
          {actions}
        </div>
      </div>

      {below && <div className="px-4 pb-3">{below}</div>}
    </div>
  );
}
