'use client';

import { CheckSquare } from 'lucide-react';

function TaskCardSkeleton() {
  return (
    <div className="flex items-center gap-3 p-3 rounded-lg bg-bg-secondary border border-bg-tertiary">
      <div className="w-5 h-5 rounded border-2 border-bg-quaternary animate-pulse" />
      <div className="flex-1 min-w-0">
        <div className="h-4 w-full bg-bg-tertiary rounded animate-pulse" />
      </div>
      <div className="h-5 w-16 bg-bg-tertiary rounded-full animate-pulse" />
    </div>
  );
}

function TaskGroupSkeleton({ count }: { title?: string; count: number }) {
  return (
    <div className="rounded-xl bg-bg-secondary border border-bg-tertiary overflow-hidden">
      <div className="px-4 py-3 border-b border-bg-tertiary">
        <div className="flex items-center justify-between">
          <div className="h-5 w-24 bg-bg-tertiary rounded animate-pulse" />
          <div className="h-5 w-8 bg-bg-tertiary rounded-full animate-pulse" />
        </div>
      </div>
      <div className="p-3 space-y-2">
        {[...Array(count)].map((_, i) => (
          <TaskCardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}

export default function TasksLoading() {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Page Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-bg-tertiary bg-bg-primary">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-bg-tertiary">
            <CheckSquare className="w-5 h-5 text-text-secondary" />
          </div>
          <h1 className="text-xl font-semibold text-text-primary font-display">Tasks</h1>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex-shrink-0 px-6 py-3 border-b border-bg-tertiary bg-bg-secondary">
        <div className="flex items-center justify-between">
          {/* View tabs */}
          <div className="flex items-center gap-1 p-1 rounded-lg bg-bg-tertiary">
            <div className="w-8 h-8 rounded-md bg-bg-quaternary animate-pulse" />
            <div className="w-8 h-8 rounded-md bg-bg-tertiary animate-pulse" />
          </div>

          {/* Stats */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <div className="h-4 w-16 bg-bg-tertiary rounded animate-pulse" />
              <div className="h-5 w-8 bg-bg-tertiary rounded animate-pulse" />
            </div>
            <div className="flex items-center gap-2">
              <div className="h-4 w-20 bg-bg-tertiary rounded animate-pulse" />
              <div className="h-5 w-8 bg-bg-tertiary rounded animate-pulse" />
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-bg-tertiary animate-pulse" />
            <div className="w-8 h-8 rounded-lg bg-bg-tertiary animate-pulse" />
          </div>
        </div>
      </div>

      {/* Quick Add */}
      <div className="flex-shrink-0 px-6 py-3 border-b border-bg-tertiary">
        <div className="h-10 w-full rounded-lg bg-bg-tertiary animate-pulse" />
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <TaskGroupSkeleton title="Overdue" count={2} />
          <TaskGroupSkeleton title="Today" count={3} />
          <TaskGroupSkeleton title="Tomorrow" count={2} />
          <TaskGroupSkeleton title="This Week" count={4} />
          <TaskGroupSkeleton title="Later" count={3} />
          <TaskGroupSkeleton title="No Date" count={2} />
        </div>
      </div>
    </div>
  );
}
