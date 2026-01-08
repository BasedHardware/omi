'use client';

import { motion } from 'framer-motion';
import { Check, Clock, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ActionItem } from '@/types/conversation';

interface UpcomingTasksCardProps {
  tasks: ActionItem[];
  onToggleComplete: (id: string, completed: boolean) => void;
  maxItems?: number;
}

function formatDueText(dueAt: string | null | undefined): string {
  if (!dueAt) return '';

  const due = new Date(dueAt);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  due.setHours(0, 0, 0, 0);

  const diffTime = due.getTime() - today.getTime();
  const diffDays = Math.round(diffTime / (1000 * 60 * 60 * 24));

  if (diffDays < 0) {
    return `${Math.abs(diffDays)}d late`;
  } else if (diffDays === 0) {
    return 'Today';
  } else if (diffDays === 1) {
    return 'Tomorrow';
  } else if (diffDays <= 7) {
    return due.toLocaleDateString('en-US', { weekday: 'short' });
  } else {
    return due.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }
}

function isOverdue(dueAt: string | null | undefined): boolean {
  if (!dueAt) return false;
  const due = new Date(dueAt);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  due.setHours(0, 0, 0, 0);
  return due < today;
}

export function UpcomingTasksCard({
  tasks,
  onToggleComplete,
  maxItems = 5,
}: UpcomingTasksCardProps) {
  // Get upcoming tasks (non-completed, sorted by due date)
  const upcomingTasks = tasks
    .filter(t => !t.completed)
    .sort((a, b) => {
      // Tasks with due dates come first
      if (!a.due_at && !b.due_at) return 0;
      if (!a.due_at) return 1;
      if (!b.due_at) return -1;
      return new Date(a.due_at).getTime() - new Date(b.due_at).getTime();
    })
    .slice(0, maxItems);

  if (upcomingTasks.length === 0) {
    return null;
  }

  return (
    <div className="bg-bg-secondary rounded-xl p-4 border border-bg-tertiary overflow-hidden">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-text-primary flex items-center gap-2">
          <ArrowRight className="w-4 h-4 text-purple-primary flex-shrink-0" />
          Coming Up
        </h3>
        <span className="text-xs text-text-quaternary flex-shrink-0">
          Next {upcomingTasks.length}
        </span>
      </div>

      <div className="space-y-1">
        {upcomingTasks.map((task, index) => (
          <motion.div
            key={task.id}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.05 }}
            className={cn(
              'group flex items-center gap-2 p-2 -mx-2 rounded-lg',
              'hover:bg-white/[0.03] transition-colors',
              'min-w-0'
            )}
          >
            {/* Quick complete checkbox */}
            <button
              onClick={() => onToggleComplete(task.id, true)}
              className={cn(
                'flex-shrink-0 w-4 h-4 rounded-full border',
                'flex items-center justify-center',
                'transition-all duration-150',
                isOverdue(task.due_at)
                  ? 'border-error hover:bg-error/20'
                  : 'border-text-quaternary/50 hover:border-success hover:bg-success/20'
              )}
            >
              <Check className="w-2.5 h-2.5 text-transparent group-hover:text-success" />
            </button>

            {/* Task description */}
            <span className="flex-1 min-w-0 text-sm text-text-secondary truncate">
              {task.description}
            </span>

            {/* Due indicator */}
            {task.due_at && (
              <span
                className={cn(
                  'flex-shrink-0 text-xs flex items-center gap-1 whitespace-nowrap',
                  isOverdue(task.due_at) ? 'text-error' : 'text-text-quaternary'
                )}
              >
                <Clock className="w-3 h-3" />
                {formatDueText(task.due_at)}
              </span>
            )}
          </motion.div>
        ))}
      </div>
    </div>
  );
}
