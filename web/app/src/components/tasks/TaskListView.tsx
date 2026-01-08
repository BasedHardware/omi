'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { TaskRow } from './TaskRow';
import type { ActionItem } from '@/types/conversation';

interface TaskListViewProps {
  pendingTasks: ActionItem[];
  completedTasks: ActionItem[];
  showCompleted: boolean;
  onToggleShowCompleted: () => void;
  selectedIds: Set<string>;
  onSelect: (id: string, selected: boolean) => void;
  isSelectMode: boolean;
  focusedIndex: number;
  onToggleComplete: (id: string, completed: boolean) => void;
  onSnooze: (id: string, days: number) => void;
  onDelete: (id: string) => void;
  onUpdateDescription: (id: string, description: string) => void;
  onSetDueDate: (id: string, date: Date | null) => void;
  searchQuery?: string;
}

export function TaskListView({
  pendingTasks,
  completedTasks,
  showCompleted,
  onToggleShowCompleted,
  selectedIds,
  onSelect,
  isSelectMode,
  focusedIndex,
  onToggleComplete,
  onSnooze,
  onDelete,
  onUpdateDescription,
  onSetDueDate,
  searchQuery = '',
}: TaskListViewProps) {
  // Filter tasks based on search query
  const filteredPending = searchQuery
    ? pendingTasks.filter(t =>
        t.description.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : pendingTasks;

  const filteredCompleted = searchQuery
    ? completedTasks.filter(t =>
        t.description.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : completedTasks;

  const isEmpty = filteredPending.length === 0 && filteredCompleted.length === 0;

  if (isEmpty && !searchQuery) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <div className="w-16 h-16 mb-4 rounded-full bg-bg-tertiary flex items-center justify-center">
          <span className="text-2xl">✓</span>
        </div>
        <h3 className="text-lg font-medium text-text-primary mb-2">All caught up!</h3>
        <p className="text-sm text-text-tertiary">No tasks to show. Add a new task to get started.</p>
      </div>
    );
  }

  if (isEmpty && searchQuery) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <p className="text-sm text-text-tertiary">No tasks match "{searchQuery}"</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {/* Pending tasks - flat list */}
      <div className="border border-bg-tertiary rounded-lg overflow-hidden">
        <AnimatePresence mode="popLayout">
          {filteredPending.map((task, index) => (
            <TaskRow
              key={task.id}
              task={task}
              onToggleComplete={onToggleComplete}
              onSnooze={onSnooze}
              onDelete={onDelete}
              onUpdateDescription={onUpdateDescription}
              onSetDueDate={onSetDueDate}
              isSelected={selectedIds.has(task.id)}
              onSelect={isSelectMode ? onSelect : undefined}
              isFocused={focusedIndex === index}
            />
          ))}
        </AnimatePresence>

        {filteredPending.length === 0 && (
          <div className="px-4 py-8 text-center text-text-tertiary text-sm">
            No pending tasks
          </div>
        )}
      </div>

      {/* Completed tasks toggle */}
      {filteredCompleted.length > 0 && (
        <div className="mt-4">
          <button
            onClick={onToggleShowCompleted}
            className={cn(
              'flex items-center gap-2 px-3 py-2 w-full',
              'text-sm text-text-tertiary hover:text-text-secondary',
              'transition-colors rounded-lg hover:bg-bg-tertiary/50'
            )}
          >
            {showCompleted ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
            <span>
              {showCompleted ? 'Hide' : 'Show'} {filteredCompleted.length} completed task
              {filteredCompleted.length !== 1 ? 's' : ''}
            </span>
          </button>

          <AnimatePresence>
            {showCompleted && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden"
              >
                <div className="border border-bg-tertiary rounded-lg overflow-hidden mt-2">
                  {filteredCompleted.map((task, index) => (
                    <TaskRow
                      key={task.id}
                      task={task}
                      onToggleComplete={onToggleComplete}
                      onSnooze={onSnooze}
                      onDelete={onDelete}
                      onUpdateDescription={onUpdateDescription}
                      onSetDueDate={onSetDueDate}
                      isSelected={selectedIds.has(task.id)}
                      onSelect={isSelectMode ? onSelect : undefined}
                      isFocused={focusedIndex === filteredPending.length + index}
                    />
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
