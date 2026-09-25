'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { TaskCard, TaskCardSkeleton } from './TaskCard';
import type { ActionItem } from '@/types/conversation';

interface TaskGroupProps {
  title: string;
  icon: string;
  tasks: ActionItem[];
  collapsible?: boolean;
  defaultCollapsed?: boolean;
  maxVisible?: number;
  onToggleComplete: (id: string, completed: boolean) => void;
  onSnooze: (id: string, days: number) => void;
  onDelete: (id: string) => void;
  onUpdateDescription?: (id: string, description: string) => void;
  onSetDueDate?: (id: string, date: Date | null) => void;
  selectedIds?: Set<string>;
  onSelect?: (id: string, selected: boolean) => void;
  // Double-click to enter selection mode
  onEnterSelectionMode?: (id: string) => void;
}

export function TaskGroup({
  title,
  icon,
  tasks,
  collapsible = false,
  defaultCollapsed = false,
  maxVisible,
  onToggleComplete,
  onSnooze,
  onDelete,
  onUpdateDescription,
  onSetDueDate,
  selectedIds,
  onSelect,
  onEnterSelectionMode,
}: TaskGroupProps) {
  const [isCollapsed, setIsCollapsed] = useState(defaultCollapsed);
  const [showAll, setShowAll] = useState(false);

  if (tasks.length === 0) return null;

  const visibleTasks = maxVisible && !showAll ? tasks.slice(0, maxVisible) : tasks;
  const hasMore = maxVisible && tasks.length > maxVisible && !showAll;

  return (
    <section className="space-y-2">
      {/* Header */}
      <button
        onClick={() => collapsible && setIsCollapsed(!isCollapsed)}
        disabled={!collapsible}
        className={cn(
          'flex w-full items-center gap-2',
          'text-left',
          collapsible && 'cursor-pointer hover:opacity-80',
        )}
      >
        {collapsible && (
          <span className="text-text-quaternary">
            {isCollapsed ? (
              <ChevronRight className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
          </span>
        )}
        <span className="text-base">{icon}</span>
        <h3 className="text-sm font-medium text-text-secondary">{title}</h3>
        <span className="text-xs text-text-quaternary">({tasks.length})</span>
      </button>

      {/* Tasks */}
      {!isCollapsed && (
        <div className="space-y-1.5">
          {visibleTasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              onToggleComplete={onToggleComplete}
              onSnooze={onSnooze}
              onDelete={onDelete}
              onUpdateDescription={onUpdateDescription}
              onSetDueDate={onSetDueDate}
              isSelected={selectedIds?.has(task.id)}
              onSelect={onSelect}
              onEnterSelectionMode={onEnterSelectionMode}
            />
          ))}

          {/* Show more button */}
          {hasMore && (
            <button
              onClick={() => setShowAll(true)}
              className={cn(
                'w-full py-2 text-sm text-text-tertiary',
                'transition-colors hover:text-white',
                'text-center',
              )}
            >
              Show {tasks.length - maxVisible} more
            </button>
          )}
        </div>
      )}
    </section>
  );
}

// Skeleton loader
interface TaskGroupSkeletonProps {
  count?: number;
}

export function TaskGroupSkeleton({ count = 3 }: TaskGroupSkeletonProps) {
  return (
    <div className="space-y-2">
      {/* Header skeleton */}
      <div className="flex items-center gap-2">
        <div className="h-4 w-4 animate-pulse rounded bg-bg-quaternary" />
        <div className="h-4 w-24 animate-pulse rounded bg-bg-quaternary" />
        <div className="h-3 w-6 animate-pulse rounded bg-bg-quaternary" />
      </div>

      {/* Card skeletons */}
      <div className="space-y-1.5">
        {Array.from({ length: count }).map((_, i) => (
          <TaskCardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}
