'use client';

import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Calendar, ChevronLeft, ChevronRight, X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DateFilterProps {
  selectedDate: Date | null;
  onDateChange: (date: Date | null) => void;
  className?: string;
}

type QuickFilter = {
  label: string;
  getDate: () => Date;
};

const quickFilters: QuickFilter[] = [
  { label: 'Today', getDate: () => new Date() },
  {
    label: 'Yesterday',
    getDate: () => {
      const d = new Date();
      d.setDate(d.getDate() - 1);
      return d;
    },
  },
  {
    label: 'Last 7 days',
    getDate: () => {
      const d = new Date();
      d.setDate(d.getDate() - 7);
      return d;
    },
  },
  {
    label: 'This week',
    getDate: () => {
      const d = new Date();
      const day = d.getDay();
      d.setDate(d.getDate() - day);
      return d;
    },
  },
];

const DAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function isSameDay(d1: Date, d2: Date): boolean {
  return (
    d1.getFullYear() === d2.getFullYear() &&
    d1.getMonth() === d2.getMonth() &&
    d1.getDate() === d2.getDate()
  );
}

function isToday(date: Date): boolean {
  return isSameDay(date, new Date());
}

function formatButtonLabel(date: Date | null): string {
  if (!date) return 'All dates';

  const today = new Date();
  if (isSameDay(date, today)) return 'Today';

  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  if (isSameDay(date, yesterday)) return 'Yesterday';

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function getDaysInMonth(year: number, month: number): Date[] {
  const days: Date[] = [];
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);

  // Add padding days from previous month
  const startPadding = firstDay.getDay();
  for (let i = startPadding - 1; i >= 0; i--) {
    const d = new Date(year, month, -i);
    days.push(d);
  }

  // Add days of current month
  for (let i = 1; i <= lastDay.getDate(); i++) {
    days.push(new Date(year, month, i));
  }

  // Add padding days from next month to complete the grid
  const endPadding = 42 - days.length; // 6 rows * 7 days
  for (let i = 1; i <= endPadding; i++) {
    days.push(new Date(year, month + 1, i));
  }

  return days;
}

export function DateFilter({
  selectedDate,
  onDateChange,
  className,
}: DateFilterProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [viewDate, setViewDate] = useState(() => selectedDate || new Date());
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  // Close on escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen]);

  const handlePrevMonth = () => {
    setViewDate((prev) => new Date(prev.getFullYear(), prev.getMonth() - 1, 1));
  };

  const handleNextMonth = () => {
    setViewDate((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1));
  };

  const handleDateSelect = (date: Date) => {
    onDateChange(date);
    setIsOpen(false);
  };

  const handleQuickFilter = (filter: QuickFilter) => {
    const date = filter.getDate();
    onDateChange(date);
    setViewDate(date);
    setIsOpen(false);
  };

  const handleClear = () => {
    onDateChange(null);
    setIsOpen(false);
  };

  const days = getDaysInMonth(viewDate.getFullYear(), viewDate.getMonth());
  const currentMonth = viewDate.getMonth();

  return (
    <div ref={containerRef} className={cn('relative', className)}>
      {/* Trigger button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex items-center gap-2 px-3 py-2 rounded-lg',
          'text-sm font-medium transition-all duration-150',
          'border',
          isOpen
            ? 'bg-bg-tertiary border-purple-primary/40 text-text-primary'
            : selectedDate
            ? 'bg-purple-primary/10 border-purple-primary/30 text-purple-primary'
            : 'bg-transparent border-transparent text-text-secondary hover:bg-bg-tertiary hover:text-text-primary'
        )}
      >
        <Calendar className="w-4 h-4" />
        <span>{formatButtonLabel(selectedDate)}</span>
        {selectedDate && (
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => {
              e.stopPropagation();
              handleClear();
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                e.stopPropagation();
                handleClear();
              }
            }}
            className="p-0.5 rounded hover:bg-bg-quaternary cursor-pointer"
            aria-label="Clear date filter"
          >
            <X className="w-3 h-3" />
          </span>
        )}
      </button>

      {/* Popover */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -10 }}
            transition={{ duration: 0.15 }}
            className={cn(
              'absolute top-full right-0 mt-2 z-50',
              'w-72 p-3 rounded-xl',
              'bg-bg-secondary border border-bg-tertiary',
              'shadow-lg shadow-black/20'
            )}
          >
            {/* Quick filters */}
            <div className="mb-3">
              <p className="text-xs text-text-quaternary mb-2">Quick filters</p>
              <div className="flex flex-wrap gap-1.5">
                {quickFilters.map((filter) => (
                  <button
                    key={filter.label}
                    onClick={() => handleQuickFilter(filter)}
                    className={cn(
                      'px-2.5 py-1 rounded-md text-xs font-medium',
                      'transition-colors',
                      selectedDate && isSameDay(selectedDate, filter.getDate())
                        ? 'bg-purple-primary text-white'
                        : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary hover:text-text-primary'
                    )}
                  >
                    {filter.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Calendar header */}
            <div className="flex items-center justify-between mb-2">
              <button
                onClick={handlePrevMonth}
                className="p-1 rounded-md hover:bg-bg-tertiary text-text-secondary hover:text-text-primary transition-colors"
                aria-label="Previous month"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-sm font-medium text-text-primary">
                {MONTHS[viewDate.getMonth()]} {viewDate.getFullYear()}
              </span>
              <button
                onClick={handleNextMonth}
                className="p-1 rounded-md hover:bg-bg-tertiary text-text-secondary hover:text-text-primary transition-colors"
                aria-label="Next month"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>

            {/* Day names */}
            <div className="grid grid-cols-7 gap-1 mb-1">
              {DAYS.map((day) => (
                <div
                  key={day}
                  className="text-center text-xs text-text-quaternary py-1"
                >
                  {day}
                </div>
              ))}
            </div>

            {/* Days grid */}
            <div className="grid grid-cols-7 gap-1">
              {days.map((date, index) => {
                const isCurrentMonth = date.getMonth() === currentMonth;
                const isSelected = selectedDate && isSameDay(date, selectedDate);
                const isTodayDate = isToday(date);
                const isFuture = date > new Date();

                return (
                  <button
                    key={index}
                    onClick={() => !isFuture && handleDateSelect(date)}
                    disabled={isFuture}
                    className={cn(
                      'w-8 h-8 rounded-md text-xs font-medium',
                      'transition-all duration-100',
                      !isCurrentMonth && 'text-text-quaternary/50',
                      isCurrentMonth && !isSelected && 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary',
                      isSelected && 'bg-purple-primary text-white',
                      isTodayDate && !isSelected && 'ring-1 ring-purple-primary/50',
                      isFuture && 'opacity-30 cursor-not-allowed'
                    )}
                  >
                    {date.getDate()}
                  </button>
                );
              })}
            </div>

            {/* Clear button */}
            {selectedDate && (
              <button
                onClick={handleClear}
                className={cn(
                  'w-full mt-3 py-2 rounded-lg text-sm font-medium',
                  'text-text-secondary hover:text-text-primary',
                  'hover:bg-bg-tertiary transition-colors'
                )}
              >
                Clear filter
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
