'use client';

import { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ActionItem } from '@/types/conversation';

interface MonthCalendarProps {
  items: ActionItem[];
  selectedDate?: Date | null;
  onSelectDate?: (date: Date) => void;
  onDropTask?: (date: Date, taskId: string) => void;
}

export function MonthCalendar({
  items,
  selectedDate,
  onSelectDate,
  onDropTask,
}: MonthCalendarProps) {
  const [currentMonth, setCurrentMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });

  const today = useMemo(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
  }, []);

  // Create a map of date string -> task counts for quick lookup
  const taskMap = useMemo(() => {
    const map = new Map<string, { pending: number; completed: number }>();

    items.forEach((item) => {
      if (!item.due_at) return;
      const dateStr = new Date(item.due_at).toDateString();
      const existing = map.get(dateStr) || { pending: 0, completed: 0 };

      if (item.completed) {
        existing.completed++;
      } else {
        existing.pending++;
      }

      map.set(dateStr, existing);
    });

    return map;
  }, [items]);

  // Generate calendar days for the current month
  const calendarDays = useMemo(() => {
    const year = currentMonth.getFullYear();
    const month = currentMonth.getMonth();

    // First day of the month
    const firstDay = new Date(year, month, 1);
    // Last day of the month
    const lastDay = new Date(year, month + 1, 0);

    // Start from the Sunday of the week containing the first day
    const startDate = new Date(firstDay);
    startDate.setDate(startDate.getDate() - firstDay.getDay());

    // End on the Saturday of the week containing the last day
    const endDate = new Date(lastDay);
    endDate.setDate(endDate.getDate() + (6 - lastDay.getDay()));

    const days: Date[] = [];
    const current = new Date(startDate);

    while (current <= endDate) {
      days.push(new Date(current));
      current.setDate(current.getDate() + 1);
    }

    return days;
  }, [currentMonth]);

  const monthName = currentMonth.toLocaleDateString('en-US', {
    month: 'long',
    year: 'numeric',
  });

  const goToPreviousMonth = () => {
    setCurrentMonth(
      new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1)
    );
  };

  const goToNextMonth = () => {
    setCurrentMonth(
      new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1)
    );
  };

  const goToToday = () => {
    setCurrentMonth(new Date(today.getFullYear(), today.getMonth(), 1));
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.currentTarget.classList.add('ring-2', 'ring-purple-primary');
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.currentTarget.classList.remove('ring-2', 'ring-purple-primary');
  };

  const handleDrop = (e: React.DragEvent, date: Date) => {
    e.preventDefault();
    e.currentTarget.classList.remove('ring-2', 'ring-purple-primary');
    const taskId = e.dataTransfer.getData('taskId');
    if (taskId && onDropTask) {
      onDropTask(date, taskId);
    }
  };

  const weekDays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  return (
    <div className="rounded-xl bg-bg-secondary border border-bg-tertiary p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-text-primary">{monthName}</h3>
        <div className="flex items-center gap-1">
          <button
            onClick={goToToday}
            className={cn(
              'px-2 py-1 text-xs rounded',
              'text-text-tertiary hover:text-text-secondary hover:bg-bg-quaternary',
              'transition-colors'
            )}
          >
            Today
          </button>
          <button
            onClick={goToPreviousMonth}
            className={cn(
              'p-1 rounded',
              'text-text-tertiary hover:text-text-secondary hover:bg-bg-quaternary',
              'transition-colors'
            )}
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button
            onClick={goToNextMonth}
            className={cn(
              'p-1 rounded',
              'text-text-tertiary hover:text-text-secondary hover:bg-bg-quaternary',
              'transition-colors'
            )}
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Weekday headers */}
      <div className="grid grid-cols-7 gap-1 mb-1">
        {weekDays.map((day) => (
          <div
            key={day}
            className="text-center text-[10px] font-medium text-text-quaternary uppercase py-1"
          >
            {day}
          </div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7 gap-1">
        {calendarDays.map((date, index) => {
          const isCurrentMonth = date.getMonth() === currentMonth.getMonth();
          const isToday = date.toDateString() === today.toDateString();
          const isSelected =
            selectedDate?.toDateString() === date.toDateString();
          const taskData = taskMap.get(date.toDateString());
          const hasTasks = taskData && (taskData.pending > 0 || taskData.completed > 0);
          const allCompleted = taskData && taskData.pending === 0 && taskData.completed > 0;

          return (
            <motion.button
              key={date.toISOString()}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: index * 0.005 }}
              onClick={() => onSelectDate?.(date)}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={(e) => handleDrop(e, date)}
              className={cn(
                'relative aspect-square flex flex-col items-center justify-center rounded-lg',
                'transition-all duration-150',
                isCurrentMonth
                  ? 'text-text-secondary'
                  : 'text-text-quaternary opacity-40',
                isToday && 'bg-purple-primary/10 text-purple-primary font-semibold',
                isSelected && 'ring-2 ring-purple-primary',
                !isToday && isCurrentMonth && 'hover:bg-bg-quaternary'
              )}
            >
              {/* Day number */}
              <span className="text-sm">{date.getDate()}</span>

              {/* Task indicator */}
              {hasTasks && isCurrentMonth && (
                <div className="absolute bottom-1">
                  {allCompleted ? (
                    <div className="w-1.5 h-1.5 rounded-full bg-success" />
                  ) : (
                    <span
                      className={cn(
                        'text-[9px] font-medium',
                        isToday ? 'text-purple-primary' : 'text-purple-primary'
                      )}
                    >
                      {taskData.pending}
                    </span>
                  )}
                </div>
              )}
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
