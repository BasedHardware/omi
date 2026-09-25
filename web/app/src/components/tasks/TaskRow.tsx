'use client';

import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, Trash2, Clock, Calendar, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatDueBadge } from '@/lib/taskDue';
import type { ActionItem } from '@/types/conversation';
import { SuccessCheck } from '@/components/ui/SuccessCheck';
import { formatDateInputValue } from '@/lib/dateInput';

interface TaskRowProps {
  task: ActionItem;
  onToggleComplete: (id: string, completed: boolean) => void;
  onSnooze: (id: string, days: number) => void;
  onDelete: (id: string) => void;
  onUpdateDescription?: (id: string, description: string) => void;
  onSetDueDate?: (id: string, date: Date | null) => void;
  isSelected?: boolean;
  onSelect?: (id: string, selected: boolean) => void;
  isFocused?: boolean;
  // Double-click to enter selection mode
  onEnterSelectionMode?: (id: string) => void;
}

export function TaskRow({
  task,
  onToggleComplete,
  onSnooze,
  onDelete,
  onUpdateDescription,
  onSetDueDate,
  isSelected = false,
  onSelect,
  isFocused = false,
  onEnterSelectionMode,
}: TaskRowProps) {
  const [isHovered, setIsHovered] = useState(false);
  const [isCompleting, setIsCompleting] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(task.description);
  const [showDatePicker, setShowDatePicker] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const datePickerRef = useRef<HTMLDivElement>(null);
  const rowRef = useRef<HTMLDivElement>(null);

  const dueBadge = task.due_at ? formatDueBadge(task.due_at) : null;
  const isOverdue = dueBadge?.isOverdue && !task.completed;

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  useEffect(() => {
    if (isFocused && rowRef.current) {
      rowRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [isFocused]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        datePickerRef.current &&
        !datePickerRef.current.contains(event.target as Node)
      ) {
        setShowDatePicker(false);
      }
    }
    if (showDatePicker) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showDatePicker]);

  const handleCheckboxClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsCompleting(true);
    await onToggleComplete(task.id, !task.completed);
    setTimeout(() => setIsCompleting(false), 300);
  };

  const handleSelectionClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onSelect) {
      onSelect(task.id, !isSelected);
    }
  };

  const handleTextDoubleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!task.completed && onUpdateDescription) {
      setEditValue(task.description);
      setIsEditing(true);
    }
  };

  const handleRowDoubleClick = () => {
    // Double-click on row enters selection mode and selects this task
    // Only trigger if not already in selection mode and handler is provided
    if (!onSelect && onEnterSelectionMode) {
      onEnterSelectionMode(task.id);
    }
  };

  const handleEditSubmit = () => {
    if (editValue.trim() && editValue !== task.description && onUpdateDescription) {
      onUpdateDescription(task.id, editValue.trim());
    }
    setIsEditing(false);
  };

  const handleEditKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleEditSubmit();
    } else if (e.key === 'Escape') {
      setEditValue(task.description);
      setIsEditing(false);
    }
  };

  const handleDateClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!task.completed && onSetDueDate) {
      setShowDatePicker(true);
    }
  };

  const handleDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (onSetDueDate) {
      const newDate = e.target.value ? new Date(e.target.value + 'T12:00:00') : null;
      onSetDueDate(task.id, newDate);
      setShowDatePicker(false);
    }
  };

  return (
    <motion.div
      ref={rowRef}
      layout
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.15 }}
      onHoverStart={() => setIsHovered(true)}
      onHoverEnd={() => setIsHovered(false)}
      onDoubleClick={handleRowDoubleClick}
      className={cn(
        'group flex items-center gap-3 px-3 py-2.5',
        'border-b border-bg-tertiary/50',
        'transition-colors duration-100',
        isHovered && 'bg-white/[0.02]',
        isFocused && 'bg-white/10',
        isSelected && 'bg-white/5',
      )}
    >
      {/* Selection checkbox */}
      {onSelect && (
        <button
          onClick={handleSelectionClick}
          className={cn(
            'h-4 w-4 flex-shrink-0 rounded',
            'border transition-all duration-150',
            'flex items-center justify-center',
            isSelected
              ? 'border-white bg-white'
              : 'border-text-quaternary/50 hover:border-white',
          )}
        >
          {isSelected && (
            <Check className="h-2.5 w-2.5 text-bg-primary" strokeWidth={3} />
          )}
        </button>
      )}

      {/* Completion checkbox - hidden in selection mode */}
      {!onSelect && (
        <button
          onClick={handleCheckboxClick}
          className={cn(
            'h-4 w-4 flex-shrink-0 rounded-full',
            'border transition-all duration-150',
            'flex items-center justify-center',
            task.completed
              ? 'border-success bg-success'
              : isOverdue
              ? 'border-error hover:bg-error/20'
              : 'border-text-quaternary/50 hover:border-text-tertiary',
          )}
        >
          {(task.completed || isCompleting) && (
            <SuccessCheck active={task.completed || isCompleting}>
              <Check className="h-2.5 w-2.5 text-white" strokeWidth={3} />
            </SuccessCheck>
          )}
        </button>
      )}

      {/* Description */}
      <div className="min-w-0 flex-1">
        {isEditing ? (
          <input
            ref={inputRef}
            type="text"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onBlur={handleEditSubmit}
            onKeyDown={handleEditKeyDown}
            className={cn(
              'w-full border border-white/50 bg-bg-secondary text-sm',
              'rounded px-2 py-0.5',
              'text-text-primary outline-none',
              'focus:ring-1 focus:ring-white/30',
            )}
          />
        ) : (
          <p
            onDoubleClick={handleTextDoubleClick}
            className={cn(
              'text-sm transition-colors',
              task.completed ? 'text-text-quaternary line-through' : 'text-text-primary',
              !task.completed && onUpdateDescription && 'cursor-text',
            )}
          >
            {task.description}
          </p>
        )}
      </div>

      {/* Due date badge */}
      {!task.completed && (
        <div className="relative flex-shrink-0">
          {dueBadge ? (
            <button
              onClick={handleDateClick}
              className={cn(
                'flex items-center gap-1 rounded px-2 py-0.5 text-xs',
                'transition-colors',
                isOverdue
                  ? 'bg-error/10 text-error'
                  : 'bg-bg-tertiary text-text-tertiary hover:bg-white/10 hover:text-white',
              )}
            >
              <Clock className="h-3 w-3" />
              {dueBadge.text}
            </button>
          ) : onSetDueDate ? (
            <button
              onClick={handleDateClick}
              className={cn(
                'flex items-center gap-1 rounded px-2 py-0.5 text-xs',
                'text-text-quaternary hover:bg-white/10 hover:text-white',
                'opacity-0 transition-opacity group-hover:opacity-100',
              )}
            >
              <Calendar className="h-3 w-3" />
              Add date
            </button>
          ) : null}

          {/* Date picker popover */}
          <AnimatePresence>
            {showDatePicker && (
              <motion.div
                ref={datePickerRef}
                initial={{ opacity: 0, y: -5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -5 }}
                transition={{ duration: 0.1 }}
                className={cn(
                  'absolute right-0 top-full z-50 mt-1',
                  'rounded-lg border border-bg-tertiary bg-bg-secondary',
                  'p-2 shadow-lg shadow-black/30',
                )}
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex min-w-[140px] flex-col gap-2">
                  <input
                    type="date"
                    value={task.due_at ? formatDateInputValue(new Date(task.due_at)) : ''}
                    onChange={handleDateChange}
                    className={cn(
                      'rounded border border-bg-quaternary bg-bg-tertiary px-2 py-1',
                      'text-xs text-text-primary outline-none',
                      'focus:border-white',
                    )}
                  />
                  <div className="flex gap-1">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        if (onSetDueDate) {
                          onSetDueDate(task.id, new Date());
                          setShowDatePicker(false);
                        }
                      }}
                      className="flex-1 rounded bg-bg-tertiary px-2 py-1 text-xs text-text-secondary hover:bg-white/20"
                    >
                      Today
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        if (onSetDueDate) {
                          const tomorrow = new Date();
                          tomorrow.setDate(tomorrow.getDate() + 1);
                          onSetDueDate(task.id, tomorrow);
                          setShowDatePicker(false);
                        }
                      }}
                      className="flex-1 rounded bg-bg-tertiary px-2 py-1 text-xs text-text-secondary hover:bg-white/20"
                    >
                      Tmrw
                    </button>
                  </div>
                  {task.due_at && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        if (onSetDueDate) {
                          onSetDueDate(task.id, null);
                          setShowDatePicker(false);
                        }
                      }}
                      className="flex items-center justify-center gap-1 rounded bg-error/10 px-2 py-1 text-xs text-error hover:bg-error/20"
                    >
                      <X className="h-3 w-3" />
                      Clear
                    </button>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* Completed date */}
      {task.completed && task.completed_at && (
        <span className="flex-shrink-0 text-xs text-text-quaternary">
          {new Date(task.completed_at).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
          })}
        </span>
      )}

      {/* Hover actions */}
      <AnimatePresence>
        {isHovered && !task.completed && !isEditing && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.1 }}
            onDoubleClick={(e) => e.stopPropagation()}
            className="flex flex-shrink-0 items-center gap-0.5"
          >
            <button
              onClick={(e) => {
                e.stopPropagation();
                onSnooze(task.id, 1);
              }}
              className="rounded px-1.5 py-0.5 text-xs text-text-quaternary hover:bg-white/10 hover:text-white"
              title="Snooze 1 day"
            >
              +1d
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete(task.id);
              }}
              className="rounded p-1 text-text-quaternary hover:bg-error/10 hover:text-error"
              title="Delete"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Delete for completed (always visible on hover) */}
      {task.completed && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete(task.id);
          }}
          className="rounded p-1 text-text-quaternary opacity-0 transition-opacity hover:bg-error/10 hover:text-error group-hover:opacity-100"
          title="Delete"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      )}
    </motion.div>
  );
}
