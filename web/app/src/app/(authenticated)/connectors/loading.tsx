'use client';

import { LayoutGrid } from 'lucide-react';

function AppCardSkeleton() {
  return (
    <div className="rounded-xl border border-bg-tertiary bg-bg-secondary p-4">
      <div className="flex items-start gap-3">
        <div className="h-12 w-12 animate-pulse rounded-lg bg-bg-tertiary" />
        <div className="min-w-0 flex-1">
          <div className="mb-2 h-5 w-32 animate-pulse rounded bg-bg-tertiary" />
          <div className="h-3 w-full animate-pulse rounded bg-bg-tertiary" />
          <div className="mt-1 h-3 w-2/3 animate-pulse rounded bg-bg-tertiary" />
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <div className="h-5 w-16 animate-pulse rounded-full bg-bg-tertiary" />
        <div className="h-5 w-12 animate-pulse rounded-full bg-bg-tertiary" />
      </div>
    </div>
  );
}

export default function AppsLoading() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="flex h-full flex-col">
        {/* Page Header */}
        <div className="flex-shrink-0 border-b border-bg-tertiary bg-bg-primary px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-bg-tertiary p-2">
              <LayoutGrid className="h-5 w-5 text-text-secondary" />
            </div>
            <h1 className="font-display text-xl font-semibold text-text-primary">
              Connectors
            </h1>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex-shrink-0 border-b border-bg-tertiary bg-bg-secondary px-6 py-3">
          <div className="flex items-center gap-1">
            {['Explore', 'Installed', 'My Apps', 'Services'].map((tab, i) => (
              <div
                key={tab}
                className={`rounded-lg px-4 py-2 ${i === 0 ? 'bg-bg-tertiary' : ''}`}
              >
                <div className="h-4 w-16 animate-pulse rounded bg-bg-tertiary" />
              </div>
            ))}
          </div>
        </div>

        {/* Search and Filters */}
        <div className="flex-shrink-0 border-b border-bg-tertiary px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="h-10 flex-1 animate-pulse rounded-lg bg-bg-tertiary" />
            <div className="h-10 w-28 animate-pulse rounded-lg bg-bg-tertiary" />
            <div className="h-10 w-28 animate-pulse rounded-lg bg-bg-tertiary" />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Popular Section */}
          <div className="mb-8">
            <div className="mb-4 h-6 w-32 animate-pulse rounded bg-bg-tertiary" />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {[...Array(4)].map((_, i) => (
                <AppCardSkeleton key={i} />
              ))}
            </div>
          </div>

          {/* Category Section */}
          <div>
            <div className="mb-4 h-6 w-40 animate-pulse rounded bg-bg-tertiary" />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {[...Array(8)].map((_, i) => (
                <AppCardSkeleton key={i} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
