'use client';

import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Calendar, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatDateInputValue } from '@/lib/dateInput';

interface TaskQuickAddProps {
  onAdd: (description: string, dueAt?: string) => Promise<void>;
  disabled?: boolean;
  defaultDueDate?: Date | null;
}

export function TaskQuickAdd({
  onAdd,
  disabled = false,
  defaultDueDate,
}: TaskQuickAddProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [value, setValue] = useState('');
  const [dueDate, setDueDate] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus input when expanded
  useEffect(() => {
    if (isExpanded && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isExpanded]);

  // Set default due date when provided
  useEffect(() => {
    if (defaultDueDate && isExpanded) {
      setDueDate(formatDateInputValue(defaultDueDate));
    }
  }, [defaultDueDate, isExpanded]);

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!value.trim() || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const dueAt = dueDate ? new Date(dueDate + 'T12:00:00').toISOString() : undefined;
      await onAdd(value.trim(), dueAt);
      setValue('');
      setDueDate('');
      setIsExpanded(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    } else if (e.key === 'Escape') {
      setValue('');
      setDueDate('');
      setIsExpanded(false);
    }
  };

  const handleCancel = () => {
    setValue('');
    setDueDate('');
    setIsExpanded(false);
  };

  if (!isExpanded) {
    return (
      <button
        onClick={() => setIsExpanded(true)}
        disabled={disabled}
        className={cn(
          'flex w-full items-center gap-2 px-3 py-2.5',
          'rounded-lg border border-dashed border-bg-quaternary',
          'text-text-tertiary hover:text-text-secondary',
          'hover:border-white/50 hover:bg-bg-tertiary',
          'transition-all duration-150',
          disabled && 'cursor-not-allowed opacity-50',
        )}
      >
        <Plus className="h-4 w-4" />
        <span className="text-sm">Add new task...</span>
      </button>
    );
  }

  return (
    <motion.form
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.15 }}
      onSubmit={handleSubmit}
      className={cn('rounded-lg border border-white/50', 'space-y-3 bg-bg-secondary p-3')}
    >
      {/* Input */}
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="What needs to be done?"
        disabled={isSubmitting}
        className={cn(
          'w-full bg-transparent',
          'text-sm text-text-primary placeholder:text-text-quaternary',
          'outline-none',
        )}
      />

      {/* Actions row */}
      <div className="flex items-center justify-between gap-2">
        {/* Date picker */}
        <div className="flex items-center gap-2">
          <div className="relative">
            <Calendar className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-text-quaternary" />
            <input
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              disabled={isSubmitting}
              className={cn(
                'rounded py-1 pl-8 pr-2 text-xs',
                'border border-transparent bg-bg-secondary',
                'text-text-secondary',
                'focus:border-white/50 focus:outline-none',
                'transition-colors',
              )}
            />
          </div>
          {dueDate && (
            <button
              type="button"
              onClick={() => setDueDate('')}
              className="p-1 text-text-quaternary hover:text-text-secondary"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>

        {/* Buttons */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleCancel}
            disabled={isSubmitting}
            className={cn(
              'rounded px-3 py-1 text-xs',
              'text-text-tertiary hover:text-text-secondary',
              'transition-colors',
            )}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!value.trim() || isSubmitting}
            className={cn(
              'rounded px-3 py-1 text-xs',
              'bg-white hover:bg-white/90',
              'font-medium text-black',
              'transition-colors',
              'disabled:cursor-not-allowed disabled:opacity-50',
            )}
          >
            {isSubmitting ? 'Adding...' : 'Add Task'}
          </button>
        </div>
      </div>

      {/* Hint */}
      <p className="text-[10px] text-text-quaternary">
        Press Enter to add, Escape to cancel
      </p>
    </motion.form>
  );
}
