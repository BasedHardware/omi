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
    e.currentTarget.classList.add('ring-2', 'ring-white');
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.currentTarget.classList.remove('ring-2', 'ring-white');
  };

  const handleDrop = (e: React.DragEvent, date: Date) => {
    e.preventDefault();
    e.currentTarget.classList.remove('ring-2', 'ring-white');
    const taskId = e.dataTransfer.getData('taskId');
    if (taskId && onDropTask) {
      onDropTask(date, taskId);
    }
  };

  return (
    <div className="scrollbar-hide flex gap-2 overflow-x-auto pb-2">
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
              'flex min-w-[72px] flex-col items-center rounded-lg px-3 py-2',
              'border transition-all duration-150',
              day.isToday
                ? 'border-white/50 bg-white/10'
                : 'border-transparent bg-bg-tertiary hover:border-white/30 hover:bg-bg-quaternary',
              isSelected && 'ring-2 ring-white',
            )}
          >
            {/* Day name */}
            <span
              className={cn(
                'text-[10px] font-medium uppercase tracking-wide',
                day.isToday ? 'text-white' : 'text-text-quaternary',
              )}
            >
              {day.dayName}
            </span>

            {/* Day number */}
            <span
              className={cn(
                'my-0.5 text-lg font-semibold',
                day.isToday ? 'text-text-primary' : 'text-text-secondary',
              )}
            >
              {day.dayNumber}
            </span>

            {/* Badge */}
            {!hasNoTasks && (
              <div className="flex h-5 items-center justify-center">
                {allCompleted ? (
                  <div className="flex h-5 w-5 items-center justify-center rounded-full bg-success">
                    <Check className="h-3 w-3 text-white" strokeWidth={3} />
                  </div>
                ) : (
                  <span
                    className={cn(
                      'rounded-full px-1.5 py-0.5 text-xs font-medium',
                      'bg-white text-black',
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
