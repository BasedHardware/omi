'use client';

import { useState } from 'react';
import { Circle, CheckCircle, ChevronDown, ChevronUp, MessageSquare } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ActionItemSummary } from '@/types/recap';

interface TasksSectionProps {
  tasks: ActionItemSummary[];
  onConversationClick?: (conversationId: string) => void;
}

const priorityColors = {
  high: 'text-error',
  medium: 'text-warning',
  low: 'text-text-tertiary',
};

const INITIAL_SHOW_COUNT = 5;

export function TasksSection({
  tasks,
  onConversationClick,
}: TasksSectionProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!tasks || tasks.length === 0) {
    return null;
  }

  // Group by completion status
  const pendingTasks = tasks.filter(t => !t.completed);
  const completedTasks = tasks.filter(t => t.completed);

  // Combine all tasks with pending first
  const allTasks = [...pendingTasks, ...completedTasks];
  const visibleTasks = isExpanded ? allTasks : allTasks.slice(0, INITIAL_SHOW_COUNT);
  const hiddenCount = allTasks.length - INITIAL_SHOW_COUNT;
  const showExpandButton = allTasks.length > INITIAL_SHOW_COUNT;

  return (
    <div className={cn(
      'noise-overlay rounded-xl p-4',
      'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
      'border border-white/[0.04]'
    )}>
      <div className="space-y-2">
        {visibleTasks.map((task, idx) => (
          <div
            key={idx}
            className={cn(
              'flex items-start gap-2.5',
              idx !== visibleTasks.length - 1 && 'pb-2 border-b border-white/[0.04]',
              task.completed && 'opacity-50'
            )}
          >
            {/* Checkbox icon */}
            <div className="flex-shrink-0 mt-0.5">
              {task.completed ? (
                <CheckCircle className="w-4 h-4 text-success" />
              ) : (
                <Circle className="w-4 h-4 text-text-quaternary" />
              )}
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0 flex items-start justify-between gap-2">
              <p className={cn(
                'text-sm text-text-secondary leading-relaxed flex-1',
                task.completed && 'line-through text-text-tertiary'
              )}>
                {task.description}
              </p>

              {/* Priority + conversation link */}
              <div className="flex items-center gap-1.5 flex-shrink-0">
                <span className={cn(
                  'text-[10px] font-medium',
                  priorityColors[task.priority]
                )}>
                  {task.priority.charAt(0).toUpperCase()}
                </span>

                {task.source_conversation_id && (
                  <button
                    onClick={() => onConversationClick?.(task.source_conversation_id)}
                    className={cn(
                      'p-0.5 rounded',
                      'text-text-tertiary hover:text-purple-primary',
                      'hover:bg-purple-primary/10 transition-colors'
                    )}
                    title="View source conversation"
                  >
                    <MessageSquare className="w-3 h-3" />
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Expand/Collapse button */}
      {showExpandButton && (
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className={cn(
            'w-full flex items-center justify-center gap-1.5 pt-3 mt-2',
            'text-xs text-text-tertiary hover:text-text-secondary',
            'border-t border-white/[0.04] transition-colors'
          )}
        >
          {isExpanded ? (
            <>
              <ChevronUp className="w-3.5 h-3.5" />
              Show less
            </>
          ) : (
            <>
              <ChevronDown className="w-3.5 h-3.5" />
              Show {hiddenCount} more
            </>
          )}
        </button>
      )}
    </div>
  );
}
