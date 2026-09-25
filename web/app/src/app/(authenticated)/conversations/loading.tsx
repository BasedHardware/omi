'use client';

import { GanttChartSquare } from 'lucide-react';
import { ConversationGallerySkeleton } from '@/components/conversations/ConversationGallery';
import { FolderTabsSkeleton } from '@/components/conversations/FolderTabs';

export default function ConversationsLoading() {
  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Page Header */}
      <div className="flex items-center gap-3 border-b border-stroke bg-bg-secondary px-6 py-4">
        <GanttChartSquare className="h-6 w-6 text-text-secondary" />
        <h1 className="text-2xl font-bold text-text-primary">Conversations</h1>
      </div>

      {/* Toolbar */}
      <div className="flex-shrink-0 border-b border-stroke bg-bg-secondary">
        <div className="flex items-center gap-4 px-6 py-3">
          <div className="min-w-0 flex-1">
            <FolderTabsSkeleton />
          </div>
          <div className="flex flex-shrink-0 items-center gap-2">
            <div className="h-9 w-56 animate-pulse rounded-control bg-bg-tertiary" />
            <div className="h-9 w-24 animate-pulse rounded-control bg-bg-tertiary" />
            <div className="h-9 w-20 animate-pulse rounded-control bg-bg-tertiary" />
          </div>
        </div>
      </div>

      {/* Gallery skeleton */}
      <div className="flex-1 overflow-hidden bg-bg-primary pt-4">
        <ConversationGallerySkeleton />
      </div>
    </div>
  );
}
