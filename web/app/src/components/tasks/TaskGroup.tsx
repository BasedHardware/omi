'use client';

import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { TaskCard, TaskCardSkeleton } from './TaskCard';
import type { ActionItem } from '@/types/conversation';

interface TaskGroupProps {
  title: string;
  icon: React.ReactNode;
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
    <section>
      {/* Group header */}
      <button
        onClick={() => collapsible && setIsCollapsed(!isCollapsed)}
        disabled={!collapsible}
        className={cn(
          'flex items-center gap-1.5 px-2 py-1.5 w-full text-left',
          collapsible && 'cursor-pointer hover:bg-accent/50 rounded-md'
        )}
      >
        {collapsible && (
          <ChevronDown
            className={cn(
              'w-3 h-3 text-muted-foreground transition-transform duration-150',
              isCollapsed && '-rotate-90'
            )}
          />
        )}
        <span className="text-muted-foreground">{icon}</span>
        <span className="text-xs font-medium text-foreground">{title}</span>
        <span className="text-[10px] text-muted-foreground">{tasks.length}</span>
      </button>

      {/* Data table */}
      {!isCollapsed && (
        <>
          <Table>
            <TableHeader>
              <TableRow className="border-border/30 hover:bg-transparent">
                <TableHead className="w-8 px-2" />
                <TableHead className="text-[10px] uppercase tracking-wider font-medium">Task</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wider font-medium w-28 text-right">Due</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
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
            </TableBody>
          </Table>

          {hasMore && (
            <button
              onClick={() => setShowAll(true)}
              className="w-full py-1.5 text-xs text-muted-foreground hover:text-primary transition-colors text-center"
            >
              Show {tasks.length - (maxVisible || 0)} more
            </button>
          )}
        </>
      )}
    </section>
  );
}

export function TaskGroupSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div>
      <div className="flex items-center gap-1.5 px-2 py-1.5">
        <div className="w-3 h-3 bg-muted rounded animate-pulse" />
        <div className="h-3 w-20 bg-muted rounded animate-pulse" />
      </div>
      <div>
        {Array.from({ length: count }).map((_, i) => (
          <TaskCardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}
