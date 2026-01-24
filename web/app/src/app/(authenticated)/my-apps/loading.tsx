'use client';

import { LayoutGrid } from 'lucide-react';

function AppCardSkeleton() {
  return (
    <div className="p-4 rounded-xl bg-bg-secondary border border-bg-tertiary">
      <div className="flex items-start gap-3">
        <div className="w-12 h-12 rounded-lg bg-bg-tertiary animate-pulse" />
        <div className="flex-1 min-w-0">
          <div className="h-5 w-32 bg-bg-tertiary rounded animate-pulse mb-2" />
          <div className="h-3 w-full bg-bg-tertiary rounded animate-pulse" />
          <div className="h-3 w-2/3 bg-bg-tertiary rounded animate-pulse mt-1" />
        </div>
      </div>
      <div className="flex items-center gap-2 mt-3">
        <div className="h-5 w-16 bg-bg-tertiary rounded-full animate-pulse" />
        <div className="h-5 w-12 bg-bg-tertiary rounded-full animate-pulse" />
      </div>
    </div>
  );
}

export default function AppsLoading() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="flex flex-col h-full">
        {/* Page Header */}
        <div className="flex-shrink-0 px-6 py-4 border-b border-bg-tertiary bg-bg-primary">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-bg-tertiary">
              <LayoutGrid className="w-5 h-5 text-text-secondary" />
            </div>
            <h1 className="text-xl font-semibold text-text-primary font-display">Apps</h1>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex-shrink-0 px-6 py-3 border-b border-bg-tertiary bg-bg-secondary">
          <div className="flex items-center gap-1">
            {['Explore', 'Installed', 'My Apps'].map((tab, i) => (
              <div
                key={tab}
                className={`px-4 py-2 rounded-lg ${
                  i === 0 ? 'bg-bg-tertiary' : ''
                }`}
              >
                <div className="h-4 w-16 bg-bg-tertiary rounded animate-pulse" />
              </div>
            ))}
          </div>
        </div>

        {/* Search and Filters */}
        <div className="flex-shrink-0 px-6 py-4 border-b border-bg-tertiary">
          <div className="flex items-center gap-3">
            <div className="flex-1 h-10 rounded-lg bg-bg-tertiary animate-pulse" />
            <div className="w-28 h-10 rounded-lg bg-bg-tertiary animate-pulse" />
            <div className="w-28 h-10 rounded-lg bg-bg-tertiary animate-pulse" />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Popular Section */}
          <div className="mb-8">
            <div className="h-6 w-32 bg-bg-tertiary rounded animate-pulse mb-4" />
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {[...Array(4)].map((_, i) => (
                <AppCardSkeleton key={i} />
              ))}
            </div>
          </div>

          {/* Category Section */}
          <div>
            <div className="h-6 w-40 bg-bg-tertiary rounded animate-pulse mb-4" />
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
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
