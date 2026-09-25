'use client';

import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, Trash2, Calendar, Clock, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatDueStatus } from '@/lib/taskDue';
import type { ActionItem } from '@/types/conversation';
import { formatDateInputValue } from '@/lib/dateInput';

interface TaskCardProps {
  task: ActionItem;
  onToggleComplete: (id: string, completed: boolean) => void;
  onSnooze: (id: string, days: number) => void;
  onDelete: (id: string) => void;
  onUpdateDescription?: (id: string, description: string) => void;
  onSetDueDate?: (id: string, date: Date | null) => void;
  isSelected?: boolean;
  onSelect?: (id: string, selected: boolean) => void;
  // Double-click to enter selection mode
  onEnterSelectionMode?: (id: string) => void;
}

export function TaskCard({
  task,
  onToggleComplete,
  onSnooze,
  onDelete,
  onUpdateDescription,
  onSetDueDate,
  isSelected = false,
  onSelect,
  onEnterSelectionMode,
}: TaskCardProps) {
  const [isHovered, setIsHovered] = useState(false);
  const [isCompleting, setIsCompleting] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(task.description);
  const [showDatePicker, setShowDatePicker] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const datePickerRef = useRef<HTMLDivElement>(null);

  const dueStatus = task.due_at ? formatDueStatus(task.due_at) : null;
  const isOverdue = dueStatus?.isOverdue && !task.completed;

  // Focus input when editing starts
  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  // Handle click outside for date picker
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

  const handleSnooze = (e: React.MouseEvent, days: number) => {
    e.stopPropagation();
    onSnooze(task.id, days);
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    onDelete(task.id);
  };

  const handleTextDoubleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!task.completed && onUpdateDescription) {
      setEditValue(task.description);
      setIsEditing(true);
    }
  };

  const handleCardDoubleClick = () => {
    // Double-click on card enters selection mode and selects this task
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

  const handleClearDate = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onSetDueDate) {
      onSetDueDate(task.id, null);
      setShowDatePicker(false);
    }
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.2 }}
      onHoverStart={() => setIsHovered(true)}
      onHoverEnd={() => setIsHovered(false)}
      onDoubleClick={handleCardDoubleClick}
      className={cn(
        'noise-overlay group relative cursor-pointer rounded-xl',
        'transition-all duration-150',
        'bg-white/[0.02] hover:bg-white/[0.05]',
        'p-4',
        showDatePicker && 'z-10',
        // Selection state
        isSelected && 'bg-white/5 ring-2 ring-white/50',
      )}
    >
      <div className="flex items-start gap-3">
        {/* Selection checkbox - shown when onSelect is provided */}
        {onSelect && (
          <button
            onClick={handleSelectionClick}
            className={cn(
              'mt-0.5 h-5 w-5 flex-shrink-0 rounded',
              'border-2 transition-all duration-200',
              'flex items-center justify-center',
              isSelected
                ? 'border-white bg-white'
                : 'border-text-quaternary hover:border-white',
            )}
            aria-label={isSelected ? 'Deselect task' : 'Select task'}
          >
            <AnimatePresence>
              {isSelected && (
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  exit={{ scale: 0 }}
                  transition={{ duration: 0.15 }}
                >
                  <Check className="h-3 w-3 text-bg-primary" strokeWidth={3} />
                </motion.div>
              )}
            </AnimatePresence>
          </button>
        )}

        {/* Completion checkbox - hidden in selection mode */}
        {!onSelect && (
          <button
            onClick={handleCheckboxClick}
            className={cn(
              'mt-0.5 h-5 w-5 flex-shrink-0 rounded-full',
              'border-2 transition-all duration-200',
              'flex items-center justify-center',
              task.completed
                ? 'border-success bg-success'
                : isOverdue
                ? 'border-white hover:bg-white/20'
                : 'border-text-quaternary hover:border-text-tertiary hover:bg-bg-tertiary',
            )}
            aria-label={task.completed ? 'Mark incomplete' : 'Mark complete'}
          >
            <AnimatePresence>
              {(task.completed || isCompleting) && (
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  exit={{ scale: 0 }}
                  transition={{ duration: 0.15 }}
                >
                  <Check className="h-3 w-3 text-white" strokeWidth={3} />
                </motion.div>
              )}
            </AnimatePresence>
          </button>
        )}

        {/* Content */}
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
                '-my-0.5 -ml-2 rounded px-2 py-0.5',
                'text-text-primary outline-none',
                'focus:ring-2 focus:ring-white/30',
              )}
            />
          ) : (
            <p
              onDoubleClick={handleTextDoubleClick}
              className={cn(
                'text-sm transition-all duration-200',
                task.completed
                  ? 'text-text-quaternary line-through'
                  : 'text-text-primary',
                !task.completed && onUpdateDescription && 'cursor-text hover:text-white',
              )}
              title={!task.completed ? 'Double-click to edit' : undefined}
            >
              {task.description}
            </p>
          )}

          {/* Due date / status */}
          {dueStatus && !task.completed && (
            <div className="relative mt-1 flex items-center gap-1.5">
              <button
                onClick={handleDateClick}
                className={cn(
                  'group/date flex items-center gap-1.5',
                  'transition-colors hover:text-white',
                  isOverdue ? 'text-error hover:text-error' : 'text-text-quaternary',
                )}
                title="Click to change date"
              >
                <Clock className="h-3 w-3" />
                <span
                  className={cn(
                    'text-xs',
                    isOverdue
                      ? 'text-error'
                      : 'text-text-quaternary group-hover/date:text-white',
                  )}
                >
                  {dueStatus.text}
                </span>
              </button>

              {/* Replaces the coloured left edge bar: overdue stays legible as text. */}
              {isOverdue && (
                <span className="rounded-badge bg-bg-quaternary px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-text-secondary">
                  Overdue
                </span>
              )}

              {/* Date picker popover */}
              <AnimatePresence>
                {showDatePicker && (
                  <motion.div
                    ref={datePickerRef}
                    initial={{ opacity: 0, y: -5 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -5 }}
                    transition={{ duration: 0.15 }}
                    className={cn(
                      'absolute left-0 top-full z-50 mt-1',
                      'rounded-lg border border-bg-tertiary bg-bg-secondary',
                      'p-3 shadow-lg shadow-black/30',
                    )}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="flex flex-col gap-2">
                      <input
                        type="date"
                        value={
                          task.due_at ? formatDateInputValue(new Date(task.due_at)) : ''
                        }
                        onChange={handleDateChange}
                        className={cn(
                          'rounded border border-bg-quaternary bg-bg-tertiary px-2 py-1',
                          'text-sm text-text-primary outline-none',
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
                          Tomorrow
                        </button>
                      </div>
                      {task.due_at && (
                        <button
                          onClick={handleClearDate}
                          className="flex items-center justify-center gap-1 rounded bg-error/10 px-2 py-1 text-xs text-error hover:bg-error/20"
                        >
                          <X className="h-3 w-3" />
                          Remove date
                        </button>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          {/* No due date - add one */}
          {!task.due_at && !task.completed && onSetDueDate && (
            <div className="relative mt-1">
              <button
                onClick={handleDateClick}
                className={cn(
                  'flex items-center gap-1.5 text-text-quaternary',
                  'text-xs transition-colors hover:text-white',
                )}
              >
                <Calendar className="h-3 w-3" />
                <span>Add due date</span>
              </button>

              {/* Date picker popover */}
              <AnimatePresence>
                {showDatePicker && (
                  <motion.div
                    ref={datePickerRef}
                    initial={{ opacity: 0, y: -5 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -5 }}
                    transition={{ duration: 0.15 }}
                    className={cn(
                      'absolute left-0 top-full z-50 mt-1',
                      'rounded-lg border border-bg-tertiary bg-bg-secondary',
                      'p-3 shadow-lg shadow-black/30',
                    )}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="flex flex-col gap-2">
                      <input
                        type="date"
                        onChange={handleDateChange}
                        className={cn(
                          'rounded border border-bg-quaternary bg-bg-tertiary px-2 py-1',
                          'text-sm text-text-primary outline-none',
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
                          Tomorrow
                        </button>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          {/* Completed timestamp */}
          {task.completed && task.completed_at && (
            <div className="mt-1 flex items-center gap-1.5">
              <Check className="h-3 w-3 text-success" />
              <span className="text-xs text-text-quaternary">
                Completed{' '}
                {new Date(task.completed_at).toLocaleDateString('en-US', {
                  month: 'short',
                  day: 'numeric',
                })}
              </span>
            </div>
          )}
        </div>

        {/* Hover actions */}
        <AnimatePresence>
          {isHovered && !task.completed && !isEditing && (
            <motion.div
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 10 }}
              transition={{ duration: 0.15 }}
              className="flex items-center gap-1"
            >
              {/* Snooze buttons */}
              <button
                onClick={(e) => handleSnooze(e, 0)}
                className={cn(
                  'rounded px-2 py-1 text-xs',
                  'bg-bg-secondary hover:bg-white/20 hover:text-white',
                  'text-text-tertiary transition-colors',
                )}
                title="Set due to today"
              >
                Today
              </button>
              <button
                onClick={(e) => handleSnooze(e, 1)}
                className={cn(
                  'rounded px-2 py-1 text-xs',
                  'bg-bg-secondary hover:bg-white/20 hover:text-white',
                  'text-text-tertiary transition-colors',
                )}
                title="Snooze 1 day"
              >
                +1 day
              </button>
              <button
                onClick={(e) => handleSnooze(e, 7)}
                className={cn(
                  'rounded px-2 py-1 text-xs',
                  'bg-bg-secondary hover:bg-white/20 hover:text-white',
                  'text-text-tertiary transition-colors',
                )}
                title="Snooze 7 days"
              >
                +7 days
              </button>

              {/* Delete button */}
              <button
                onClick={handleDelete}
                className={cn(
                  'rounded p-1.5',
                  'bg-bg-secondary hover:bg-error/20 hover:text-error',
                  'text-text-quaternary transition-colors',
                )}
                title="Delete task"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Delete for completed items (always visible) */}
        {task.completed && (
          <button
            onClick={handleDelete}
            className={cn(
              'rounded p-1.5 opacity-0 group-hover:opacity-100',
              'hover:bg-error/20 hover:text-error',
              'text-text-quaternary transition-all',
            )}
            title="Delete task"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </motion.div>
  );
}

// Skeleton loader
export function TaskCardSkeleton() {
  return (
    <div className="flex animate-pulse items-start gap-3 rounded-xl bg-bg-tertiary p-4">
      <div className="h-5 w-5 flex-shrink-0 rounded-full bg-bg-quaternary" />
      <div className="flex-1 space-y-2">
        <div className="h-4 w-3/4 rounded bg-bg-quaternary" />
        <div className="h-3 w-1/4 rounded bg-bg-quaternary" />
      </div>
    </div>
  );
}
