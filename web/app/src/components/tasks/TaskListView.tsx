'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, CheckCircle2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow as ShadcnTableRow,
} from '@/components/ui/table';
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
  onEnterSelectionMode?: (id: string) => void;
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
  onEnterSelectionMode,
}: TaskListViewProps) {
  const filteredPending = searchQuery
    ? pendingTasks.filter(t => t.description.toLowerCase().includes(searchQuery.toLowerCase()))
    : pendingTasks;

  const filteredCompleted = searchQuery
    ? completedTasks.filter(t => t.description.toLowerCase().includes(searchQuery.toLowerCase()))
    : completedTasks;

  const isEmpty = filteredPending.length === 0 && filteredCompleted.length === 0;

  if (isEmpty && !searchQuery) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <CheckCircle2 className="w-10 h-10 text-muted-foreground mb-3" />
        <h3 className="text-sm font-medium text-foreground mb-1">All caught up!</h3>
        <p className="text-xs text-muted-foreground">No tasks to show.</p>
      </div>
    );
  }

  if (isEmpty && searchQuery) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <p className="text-sm text-muted-foreground">No tasks match &ldquo;{searchQuery}&rdquo;</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Pending tasks table */}
      <Table>
        <TableHeader>
          <ShadcnTableRow className="border-border/30 hover:bg-transparent">
            <TableHead className="w-8 px-2" />
            <TableHead className="text-[10px] uppercase tracking-wider font-medium">Task</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider font-medium w-28 text-right">Due</TableHead>
            <TableHead className="w-10" />
          </ShadcnTableRow>
        </TableHeader>
        <TableBody>
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
                onEnterSelectionMode={onEnterSelectionMode}
              />
            ))}
          </AnimatePresence>
        </TableBody>
      </Table>

      {filteredPending.length === 0 && (
        <div className="px-4 py-6 text-center text-muted-foreground text-sm">
          No pending tasks
        </div>
      )}

      {/* Completed toggle */}
      {filteredCompleted.length > 0 && (
        <div>
          <button
            onClick={onToggleShowCompleted}
            className={cn(
              'flex items-center gap-1.5 px-2 py-1.5 w-full text-left',
              'text-xs text-muted-foreground hover:text-foreground',
              'transition-colors rounded-md hover:bg-accent/50'
            )}
          >
            <ChevronDown className={cn(
              'w-3 h-3 transition-transform duration-150',
              !showCompleted && '-rotate-90'
            )} />
            <span>
              {filteredCompleted.length} completed
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
                <Table>
                  <TableBody>
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
                        onEnterSelectionMode={onEnterSelectionMode}
                      />
                    ))}
                  </TableBody>
                </Table>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
