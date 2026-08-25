'use client';

import { CalendarDays } from 'lucide-react';

function RecapCardSkeleton() {
  return (
    <div className="p-4 rounded-xl bg-bg-secondary border border-bg-tertiary">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-10 h-10 rounded-lg bg-bg-tertiary animate-pulse" />
        <div className="flex-1">
          <div className="h-5 w-32 bg-bg-tertiary rounded animate-pulse mb-1" />
          <div className="h-3 w-20 bg-bg-tertiary rounded animate-pulse" />
        </div>
      </div>
      <div className="space-y-2">
        <div className="h-3 w-full bg-bg-tertiary rounded animate-pulse" />
        <div className="h-3 w-4/5 bg-bg-tertiary rounded animate-pulse" />
      </div>
    </div>
  );
}

export default function RecapsLoading() {
  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Page Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-bg-tertiary bg-bg-primary">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-bg-tertiary">
            <CalendarDays className="w-5 h-5 text-text-secondary" />
          </div>
          <h1 className="text-xl font-semibold text-text-primary font-display">Recaps</h1>
        </div>
      </div>

      {/* Split View */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel: Recap List */}
        <div style={{ width: '420px' }} className="flex-shrink-0 flex flex-col h-full overflow-hidden bg-bg-primary border-r border-bg-tertiary">
          {/* Month Header */}
          <div className="flex-shrink-0 px-4 py-3 border-b border-bg-tertiary">
            <div className="flex items-center justify-between">
              <div className="h-6 w-32 bg-bg-tertiary rounded animate-pulse" />
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-bg-tertiary animate-pulse" />
                <div className="w-8 h-8 rounded-lg bg-bg-tertiary animate-pulse" />
              </div>
            </div>
          </div>

          {/* Recap List */}
          <div className="flex-1 overflow-y-auto p-3">
            <div className="space-y-3">
              {[...Array(7)].map((_, i) => (
                <RecapCardSkeleton key={i} />
              ))}
            </div>
          </div>
        </div>

        {/* Resize Handle */}
        <div className="hidden lg:flex w-1 bg-bg-tertiary" />

        {/* Right Panel: Detail */}
        <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden bg-bg-primary">
          {/* Detail Header */}
          <div className="flex-shrink-0 p-6 border-b border-bg-tertiary">
            <div className="flex items-start gap-4">
              <div className="w-14 h-14 rounded-xl bg-bg-tertiary animate-pulse" />
              <div className="flex-1">
                <div className="h-7 w-48 bg-bg-tertiary rounded animate-pulse mb-2" />
                <div className="h-4 w-32 bg-bg-tertiary rounded animate-pulse" />
              </div>
            </div>
          </div>

          {/* Detail Content */}
          <div className="flex-1 overflow-y-auto p-6">
            <div className="space-y-6">
              {/* Summary */}
              <div>
                <div className="h-5 w-24 bg-bg-tertiary rounded animate-pulse mb-3" />
                <div className="space-y-2">
                  <div className="h-4 w-full bg-bg-tertiary rounded animate-pulse" />
                  <div className="h-4 w-full bg-bg-tertiary rounded animate-pulse" />
                  <div className="h-4 w-3/4 bg-bg-tertiary rounded animate-pulse" />
                </div>
              </div>

              {/* Highlights */}
              <div>
                <div className="h-5 w-28 bg-bg-tertiary rounded animate-pulse mb-3" />
                <div className="space-y-2">
                  {[...Array(4)].map((_, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <div className="w-5 h-5 rounded bg-bg-tertiary animate-pulse flex-shrink-0" />
                      <div className="h-4 flex-1 bg-bg-tertiary rounded animate-pulse" />
                    </div>
                  ))}
                </div>
              </div>

              {/* Map placeholder */}
              <div className="h-48 w-full bg-bg-tertiary rounded-xl animate-pulse" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
