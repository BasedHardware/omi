'use client';

import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, Trash2, Calendar, Clock, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ActionItem } from '@/types/conversation';

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

/**
 * Format days late/until due
 */
function formatDueStatus(dueAt: string): { text: string; isOverdue: boolean; isToday: boolean } {
  const due = new Date(dueAt);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  due.setHours(0, 0, 0, 0);

  const diffTime = due.getTime() - today.getTime();
  const diffDays = Math.round(diffTime / (1000 * 60 * 60 * 24));

  if (diffDays < 0) {
    const daysLate = Math.abs(diffDays);
    return {
      text: daysLate === 1 ? '1 day late' : `${daysLate} days late`,
      isOverdue: true,
      isToday: false,
    };
  } else if (diffDays === 0) {
    return { text: 'Due today', isOverdue: false, isToday: true };
  } else if (diffDays === 1) {
    return { text: 'Due tomorrow', isOverdue: false, isToday: false };
  } else if (diffDays <= 7) {
    return {
      text: `Due ${due.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}`,
      isOverdue: false,
      isToday: false,
    };
  } else {
    return {
      text: `Due ${due.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`,
      isOverdue: false,
      isToday: false,
    };
  }
}

/**
 * Format date for input[type="date"]
 */
function formatDateForInput(date: Date): string {
  return date.toISOString().split('T')[0];
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
      if (datePickerRef.current && !datePickerRef.current.contains(event.target as Node)) {
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
        'noise-overlay group relative rounded-xl cursor-pointer',
        'border-l-4 transition-all duration-150',
        'bg-white/[0.02] hover:bg-white/[0.05]',
        'p-4',
        // Left border color based on status
        task.completed
          ? 'border-l-success/50'
          : isOverdue
          ? 'border-l-purple-primary'
          : 'border-l-bg-quaternary',
        // Selection state
        isSelected && 'ring-2 ring-purple-primary/50 bg-purple-primary/5'
      )}
    >
      <div className="flex items-start gap-3">
        {/* Selection checkbox - shown when onSelect is provided */}
        {onSelect && (
          <button
            onClick={handleSelectionClick}
            className={cn(
              'flex-shrink-0 w-5 h-5 mt-0.5 rounded',
              'border-2 transition-all duration-200',
              'flex items-center justify-center',
              isSelected
                ? 'bg-purple-primary border-purple-primary'
                : 'border-text-quaternary hover:border-purple-primary'
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
                  <Check className="w-3 h-3 text-white" strokeWidth={3} />
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
              'flex-shrink-0 w-5 h-5 mt-0.5 rounded-full',
              'border-2 transition-all duration-200',
              'flex items-center justify-center',
              task.completed
                ? 'bg-success border-success'
                : isOverdue
                ? 'border-purple-primary hover:bg-purple-primary/20'
                : 'border-text-quaternary hover:border-text-tertiary hover:bg-bg-tertiary'
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
                  <Check className="w-3 h-3 text-white" strokeWidth={3} />
                </motion.div>
              )}
            </AnimatePresence>
          </button>
        )}

        {/* Content */}
        <div className="flex-1 min-w-0">
          {isEditing ? (
            <input
              ref={inputRef}
              type="text"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onBlur={handleEditSubmit}
              onKeyDown={handleEditKeyDown}
              className={cn(
                'w-full text-sm bg-bg-secondary border border-purple-primary/50',
                'rounded px-2 py-0.5 -ml-2 -my-0.5',
                'text-text-primary outline-none',
                'focus:ring-2 focus:ring-purple-primary/30'
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
                !task.completed && onUpdateDescription && 'hover:text-purple-primary cursor-text'
              )}
              title={!task.completed ? 'Double-click to edit' : undefined}
            >
              {task.description}
            </p>
          )}

          {/* Due date / status */}
          {dueStatus && !task.completed && (
            <div className="relative flex items-center gap-1.5 mt-1">
              <button
                onClick={handleDateClick}
                className={cn(
                  'flex items-center gap-1.5 group/date',
                  'hover:text-purple-primary transition-colors',
                  isOverdue ? 'text-error hover:text-error' : 'text-text-quaternary'
                )}
                title="Click to change date"
              >
                <Clock className="w-3 h-3" />
                <span className={cn(
                  'text-xs',
                  isOverdue ? 'text-error' : 'text-text-quaternary group-hover/date:text-purple-primary'
                )}>
                  {dueStatus.text}
                </span>
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
                      'absolute top-full left-0 mt-1 z-50',
                      'bg-bg-secondary border border-bg-tertiary rounded-lg',
                      'shadow-lg shadow-black/30 p-3'
                    )}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="flex flex-col gap-2">
                      <input
                        type="date"
                        value={task.due_at ? formatDateForInput(new Date(task.due_at)) : ''}
                        onChange={handleDateChange}
                        className={cn(
                          'bg-bg-tertiary border border-bg-quaternary rounded px-2 py-1',
                          'text-sm text-text-primary outline-none',
                          'focus:border-purple-primary'
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
                          className="flex-1 px-2 py-1 text-xs bg-bg-tertiary hover:bg-purple-primary/20 rounded text-text-secondary"
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
                          className="flex-1 px-2 py-1 text-xs bg-bg-tertiary hover:bg-purple-primary/20 rounded text-text-secondary"
                        >
                          Tomorrow
                        </button>
                      </div>
                      {task.due_at && (
                        <button
                          onClick={handleClearDate}
                          className="flex items-center justify-center gap-1 px-2 py-1 text-xs bg-error/10 hover:bg-error/20 rounded text-error"
                        >
                          <X className="w-3 h-3" />
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
                  'hover:text-purple-primary transition-colors text-xs'
                )}
              >
                <Calendar className="w-3 h-3" />
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
                      'absolute top-full left-0 mt-1 z-50',
                      'bg-bg-secondary border border-bg-tertiary rounded-lg',
                      'shadow-lg shadow-black/30 p-3'
                    )}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="flex flex-col gap-2">
                      <input
                        type="date"
                        onChange={handleDateChange}
                        className={cn(
                          'bg-bg-tertiary border border-bg-quaternary rounded px-2 py-1',
                          'text-sm text-text-primary outline-none',
                          'focus:border-purple-primary'
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
                          className="flex-1 px-2 py-1 text-xs bg-bg-tertiary hover:bg-purple-primary/20 rounded text-text-secondary"
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
                          className="flex-1 px-2 py-1 text-xs bg-bg-tertiary hover:bg-purple-primary/20 rounded text-text-secondary"
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
            <div className="flex items-center gap-1.5 mt-1">
              <Check className="w-3 h-3 text-success" />
              <span className="text-xs text-text-quaternary">
                Completed {new Date(task.completed_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
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
                  'px-2 py-1 text-xs rounded',
                  'bg-bg-secondary hover:bg-purple-primary/20 hover:text-purple-primary',
                  'text-text-tertiary transition-colors'
                )}
                title="Set due to today"
              >
                Today
              </button>
              <button
                onClick={(e) => handleSnooze(e, 1)}
                className={cn(
                  'px-2 py-1 text-xs rounded',
                  'bg-bg-secondary hover:bg-purple-primary/20 hover:text-purple-primary',
                  'text-text-tertiary transition-colors'
                )}
                title="Snooze 1 day"
              >
                +1 day
              </button>
              <button
                onClick={(e) => handleSnooze(e, 7)}
                className={cn(
                  'px-2 py-1 text-xs rounded',
                  'bg-bg-secondary hover:bg-purple-primary/20 hover:text-purple-primary',
                  'text-text-tertiary transition-colors'
                )}
                title="Snooze 7 days"
              >
                +7 days
              </button>

              {/* Delete button */}
              <button
                onClick={handleDelete}
                className={cn(
                  'p-1.5 rounded',
                  'bg-bg-secondary hover:bg-error/20 hover:text-error',
                  'text-text-quaternary transition-colors'
                )}
                title="Delete task"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Delete for completed items (always visible) */}
        {task.completed && (
          <button
            onClick={handleDelete}
            className={cn(
              'p-1.5 rounded opacity-0 group-hover:opacity-100',
              'hover:bg-error/20 hover:text-error',
              'text-text-quaternary transition-all'
            )}
            title="Delete task"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </motion.div>
  );
}

// Skeleton loader
export function TaskCardSkeleton() {
  return (
    <div className="flex items-start gap-3 p-4 rounded-xl bg-bg-tertiary animate-pulse border-l-4 border-l-bg-quaternary">
      <div className="w-5 h-5 rounded-full bg-bg-quaternary flex-shrink-0" />
      <div className="flex-1 space-y-2">
        <div className="h-4 bg-bg-quaternary rounded w-3/4" />
        <div className="h-3 bg-bg-quaternary rounded w-1/4" />
      </div>
    </div>
  );
}
