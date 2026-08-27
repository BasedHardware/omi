'use client';

/**
 * Loading skeleton
 */
export function DetailSkeleton() {
  return (
    <div className="p-6 animate-pulse">
      {/* Header */}
      <div className="flex items-start gap-4 mb-6">
        <div className="w-14 h-14 rounded-2xl bg-bg-tertiary" />
        <div className="flex-1">
          <div className="h-6 w-3/4 bg-bg-tertiary rounded mb-2" />
          <div className="flex gap-3">
            <div className="h-4 w-24 bg-bg-tertiary rounded" />
            <div className="h-4 w-20 bg-bg-tertiary rounded" />
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-10 w-24 bg-bg-tertiary rounded-lg" />
        ))}
      </div>

      {/* Content */}
      <div className="space-y-3">
        <div className="h-4 w-full bg-bg-tertiary rounded" />
        <div className="h-4 w-5/6 bg-bg-tertiary rounded" />
        <div className="h-4 w-4/6 bg-bg-tertiary rounded" />
      </div>
    </div>
  );
}
