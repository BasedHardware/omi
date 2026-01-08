'use client';

import { Brain } from 'lucide-react';

function MemoryCardSkeleton() {
  return (
    <div className="p-4 rounded-xl bg-bg-secondary border border-bg-tertiary">
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-lg bg-bg-tertiary animate-pulse flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="h-4 w-full bg-bg-tertiary rounded animate-pulse mb-2" />
          <div className="h-4 w-4/5 bg-bg-tertiary rounded animate-pulse mb-2" />
          <div className="h-3 w-2/3 bg-bg-tertiary rounded animate-pulse" />
        </div>
      </div>
      <div className="flex items-center gap-2 mt-3">
        <div className="h-5 w-14 bg-bg-tertiary rounded-full animate-pulse" />
        <div className="h-5 w-18 bg-bg-tertiary rounded-full animate-pulse" />
      </div>
    </div>
  );
}

export default function MemoriesLoading() {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Page Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-bg-tertiary bg-bg-primary">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-bg-tertiary">
            <Brain className="w-5 h-5 text-text-secondary" />
          </div>
          <h1 className="text-xl font-semibold text-text-primary font-display">Memories</h1>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex-shrink-0 px-6 py-3 border-b border-bg-tertiary bg-bg-secondary">
        <div className="flex items-center justify-between">
          {/* View mode tabs */}
          <div className="flex items-center gap-1 p-1 rounded-lg bg-bg-tertiary">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="w-8 h-8 rounded-md bg-bg-quaternary animate-pulse" />
            ))}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-bg-tertiary animate-pulse" />
            <div className="w-8 h-8 rounded-lg bg-bg-tertiary animate-pulse" />
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex-shrink-0 px-6 py-3 border-b border-bg-tertiary">
        <div className="flex items-center gap-3">
          <div className="flex-1 h-10 rounded-lg bg-bg-tertiary animate-pulse" />
          <div className="flex items-center gap-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-8 w-20 rounded-full bg-bg-tertiary animate-pulse" />
            ))}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden flex">
        {/* Memory List */}
        <div className="flex-1 overflow-y-auto p-4">
          <div className="space-y-3">
            {[...Array(8)].map((_, i) => (
              <MemoryCardSkeleton key={i} />
            ))}
          </div>
        </div>

        {/* Insights Sidebar */}
        <div className="hidden lg:block w-80 border-l border-bg-tertiary p-4">
          <div className="space-y-6">
            <div>
              <div className="h-5 w-24 bg-bg-tertiary rounded animate-pulse mb-3" />
              <div className="h-32 w-full bg-bg-tertiary rounded-xl animate-pulse" />
            </div>
            <div>
              <div className="h-5 w-28 bg-bg-tertiary rounded animate-pulse mb-3" />
              <div className="space-y-2">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="h-6 w-full bg-bg-tertiary rounded animate-pulse" />
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
