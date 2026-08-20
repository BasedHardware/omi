'use client';

import { GanttChartSquare } from 'lucide-react';
import { ConversationGallerySkeleton } from '@/components/conversations/ConversationGallery';
import { FolderTabsSkeleton } from '@/components/conversations/FolderTabs';

export default function ConversationsLoading() {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Page Header */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-stroke bg-bg-secondary">
        <GanttChartSquare className="w-6 h-6 text-text-secondary" />
        <h1 className="text-2xl font-bold text-text-primary">Conversations</h1>
      </div>

      {/* Toolbar */}
      <div className="flex-shrink-0 bg-bg-secondary border-b border-stroke">
        <div className="flex items-center gap-4 px-6 py-3">
          <div className="flex-1 min-w-0">
            <FolderTabsSkeleton />
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <div className="w-56 h-9 rounded-control bg-bg-tertiary animate-pulse" />
            <div className="w-24 h-9 rounded-control bg-bg-tertiary animate-pulse" />
            <div className="w-20 h-9 rounded-control bg-bg-tertiary animate-pulse" />
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
