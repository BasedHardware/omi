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
          'flex items-center gap-2 w-full',
          'text-left',
          collapsible && 'cursor-pointer hover:opacity-80'
        )}
      >
        {collapsible && (
          <span className="text-text-quaternary">
            {isCollapsed ? (
              <ChevronRight className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
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
            />
          ))}

          {/* Show more button */}
          {hasMore && (
            <button
              onClick={() => setShowAll(true)}
              className={cn(
                'w-full py-2 text-sm text-text-tertiary',
                'hover:text-purple-primary transition-colors',
                'text-center'
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
        <div className="w-4 h-4 bg-bg-quaternary rounded animate-pulse" />
        <div className="h-4 w-24 bg-bg-quaternary rounded animate-pulse" />
        <div className="h-3 w-6 bg-bg-quaternary rounded animate-pulse" />
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
