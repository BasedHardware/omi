'use client';

import { MessageSquare } from 'lucide-react';
import { DateGroupSkeleton } from '@/components/conversations/DateGroup';
import { FolderTabsSkeleton } from '@/components/conversations/FolderTabs';

export default function ConversationsLoading() {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Page Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-bg-tertiary bg-bg-primary">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-bg-tertiary">
            <MessageSquare className="w-5 h-5 text-text-secondary" />
          </div>
          <h1 className="text-xl font-semibold text-text-primary font-display">
            Conversations
          </h1>
        </div>
      </div>

      {/* Toolbar: Folder Tabs */}
      <div className="flex-shrink-0 bg-bg-secondary border-b border-bg-tertiary">
        <div className="flex items-center gap-4 px-6 py-3">
          <div className="flex-1 min-w-0">
            <FolderTabsSkeleton />
          </div>
          {/* Skeleton for Select button */}
          <div className="w-20 h-8 rounded-lg bg-bg-tertiary animate-pulse" />
        </div>
      </div>

      {/* Split Panels Container */}
      <div className="flex flex-1 overflow-hidden w-full">
        {/* Left Panel: Conversation List Skeleton */}
        <div
          style={{ width: '420px' }}
          className="w-full lg:w-auto flex-shrink-0 flex flex-col h-full overflow-hidden bg-bg-primary border-r border-bg-tertiary"
        >
          {/* Search and Date Filter skeleton */}
          <div className="flex-shrink-0 px-3 pt-4 pb-3">
            <div className="flex items-center gap-2">
              <div className="flex-1 h-10 rounded-lg bg-bg-tertiary animate-pulse" />
              <div className="w-24 h-10 rounded-lg bg-bg-tertiary animate-pulse" />
            </div>
          </div>

          {/* List Content Skeleton */}
          <div className="flex-1 overflow-y-auto px-3 pb-4">
            <div className="space-y-6">
              <DateGroupSkeleton count={3} />
              <DateGroupSkeleton count={2} />
            </div>
          </div>
        </div>

        {/* Resize Handle placeholder */}
        <div className="hidden lg:flex w-1 bg-bg-tertiary" />

        {/* Right Panel: Detail Skeleton */}
        <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden bg-bg-primary">
          {/* Detail header skeleton */}
          <div className="flex-shrink-0 p-6 border-b border-bg-tertiary">
            <div className="flex items-start gap-4">
              <div className="flex-1">
                <div className="h-7 w-64 bg-bg-tertiary rounded animate-pulse mb-2" />
                <div className="h-4 w-32 bg-bg-tertiary rounded animate-pulse" />
              </div>
            </div>
          </div>

          {/* Detail content skeleton */}
          <div className="flex-1 overflow-y-auto p-6">
            <div className="space-y-4">
              <div className="h-4 w-full bg-bg-tertiary rounded animate-pulse" />
              <div className="h-4 w-5/6 bg-bg-tertiary rounded animate-pulse" />
              <div className="h-4 w-4/6 bg-bg-tertiary rounded animate-pulse" />
              <div className="h-20 w-full bg-bg-tertiary rounded-lg animate-pulse mt-6" />
              <div className="h-4 w-full bg-bg-tertiary rounded animate-pulse" />
              <div className="h-4 w-3/4 bg-bg-tertiary rounded animate-pulse" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
