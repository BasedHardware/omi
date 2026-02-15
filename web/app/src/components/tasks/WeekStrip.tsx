'use client';

import { motion } from 'framer-motion';
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DayData {
  date: Date;
  dayName: string;
  dayNumber: number;
  isToday: boolean;
  pending: number;
  completed: number;
}

interface WeekStripProps {
  days: DayData[];
  selectedDate?: Date | null;
  onSelectDate?: (date: Date) => void;
  onDropTask?: (date: Date, taskId: string) => void;
}

export function WeekStrip({
  days,
  selectedDate,
  onSelectDate,
  onDropTask,
}: WeekStripProps) {
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

  return (
    <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
      {days.map((day, index) => {
        const isSelected = selectedDate?.toDateString() === day.date.toDateString();
        const hasNoTasks = day.pending === 0 && day.completed === 0;
        const allCompleted = day.pending === 0 && day.completed > 0;

        return (
          <motion.button
            key={day.date.toISOString()}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.05 }}
            onClick={() => onSelectDate?.(day.date)}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={(e) => handleDrop(e, day.date)}
            className={cn(
              'flex flex-col items-center min-w-[72px] px-3 py-2 rounded-lg',
              'border transition-all duration-150',
              day.isToday
                ? 'bg-purple-primary/10 border-purple-primary/50'
                : 'bg-bg-tertiary border-transparent hover:bg-bg-quaternary hover:border-purple-primary/30',
              isSelected && 'ring-2 ring-purple-primary'
            )}
          >
            {/* Day name */}
            <span
              className={cn(
                'text-[10px] font-medium uppercase tracking-wide',
                day.isToday ? 'text-purple-primary' : 'text-text-quaternary'
              )}
            >
              {day.dayName}
            </span>

            {/* Day number */}
            <span
              className={cn(
                'text-lg font-semibold my-0.5',
                day.isToday ? 'text-text-primary' : 'text-text-secondary'
              )}
            >
              {day.dayNumber}
            </span>

            {/* Badge */}
            {!hasNoTasks && (
              <div className="h-5 flex items-center justify-center">
                {allCompleted ? (
                  <div className="w-5 h-5 rounded-full bg-success flex items-center justify-center">
                    <Check className="w-3 h-3 text-white" strokeWidth={3} />
                  </div>
                ) : (
                  <span
                    className={cn(
                      'px-1.5 py-0.5 rounded-full text-xs font-medium',
                      'bg-purple-primary text-white'
                    )}
                  >
                    {day.pending}
                  </span>
                )}
              </div>
            )}

            {/* Empty spacer to maintain height */}
            {hasNoTasks && <div className="h-5" />}
          </motion.button>
        );
      })}
    </div>
  );
}
