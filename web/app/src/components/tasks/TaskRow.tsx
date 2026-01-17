'use client';

import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, Trash2, Clock, Calendar, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ActionItem } from '@/types/conversation';

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

function formatDueBadge(dueAt: string): { text: string; isOverdue: boolean } {
  const due = new Date(dueAt);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  due.setHours(0, 0, 0, 0);

  const diffTime = due.getTime() - today.getTime();
  const diffDays = Math.round(diffTime / (1000 * 60 * 60 * 24));

  if (diffDays < 0) {
    return { text: `${Math.abs(diffDays)}d late`, isOverdue: true };
  } else if (diffDays === 0) {
    return { text: 'Today', isOverdue: false };
  } else if (diffDays === 1) {
    return { text: 'Tomorrow', isOverdue: false };
  } else if (diffDays <= 7) {
    return { text: due.toLocaleDateString('en-US', { weekday: 'short' }), isOverdue: false };
  } else {
    return { text: due.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }), isOverdue: false };
  }
}

function formatDateForInput(date: Date): string {
  return date.toISOString().split('T')[0];
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
        isFocused && 'bg-purple-primary/10',
        isSelected && 'bg-purple-primary/5'
      )}
    >
      {/* Selection checkbox */}
      {onSelect && (
        <button
          onClick={handleSelectionClick}
          className={cn(
            'flex-shrink-0 w-4 h-4 rounded',
            'border transition-all duration-150',
            'flex items-center justify-center',
            isSelected
              ? 'bg-purple-primary border-purple-primary'
              : 'border-text-quaternary/50 hover:border-purple-primary'
          )}
        >
          {isSelected && <Check className="w-2.5 h-2.5 text-white" strokeWidth={3} />}
        </button>
      )}

      {/* Completion checkbox - hidden in selection mode */}
      {!onSelect && (
        <button
          onClick={handleCheckboxClick}
          className={cn(
            'flex-shrink-0 w-4 h-4 rounded-full',
            'border transition-all duration-150',
            'flex items-center justify-center',
            task.completed
              ? 'bg-success border-success'
              : isOverdue
              ? 'border-error hover:bg-error/20'
              : 'border-text-quaternary/50 hover:border-text-tertiary'
          )}
        >
          {(task.completed || isCompleting) && (
            <Check className="w-2.5 h-2.5 text-white" strokeWidth={3} />
          )}
        </button>
      )}

      {/* Description */}
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
              'rounded px-2 py-0.5',
              'text-text-primary outline-none',
              'focus:ring-1 focus:ring-purple-primary/30'
            )}
          />
        ) : (
          <p
            onDoubleClick={handleTextDoubleClick}
            className={cn(
              'text-sm truncate transition-colors',
              task.completed
                ? 'text-text-quaternary line-through'
                : 'text-text-primary',
              !task.completed && onUpdateDescription && 'cursor-text'
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
                'flex items-center gap-1 px-2 py-0.5 rounded text-xs',
                'transition-colors',
                isOverdue
                  ? 'bg-error/10 text-error'
                  : 'bg-bg-tertiary text-text-tertiary hover:bg-purple-primary/10 hover:text-purple-primary'
              )}
            >
              <Clock className="w-3 h-3" />
              {dueBadge.text}
            </button>
          ) : onSetDueDate ? (
            <button
              onClick={handleDateClick}
              className={cn(
                'flex items-center gap-1 px-2 py-0.5 rounded text-xs',
                'text-text-quaternary hover:text-purple-primary hover:bg-purple-primary/10',
                'opacity-0 group-hover:opacity-100 transition-opacity'
              )}
            >
              <Calendar className="w-3 h-3" />
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
                  'absolute top-full right-0 mt-1 z-50',
                  'bg-bg-secondary border border-bg-tertiary rounded-lg',
                  'shadow-lg shadow-black/30 p-2'
                )}
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex flex-col gap-2 min-w-[140px]">
                  <input
                    type="date"
                    value={task.due_at ? formatDateForInput(new Date(task.due_at)) : ''}
                    onChange={handleDateChange}
                    className={cn(
                      'bg-bg-tertiary border border-bg-quaternary rounded px-2 py-1',
                      'text-xs text-text-primary outline-none',
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
                      className="flex items-center justify-center gap-1 px-2 py-1 text-xs bg-error/10 hover:bg-error/20 rounded text-error"
                    >
                      <X className="w-3 h-3" />
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
          {new Date(task.completed_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
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
            className="flex items-center gap-0.5 flex-shrink-0"
          >
            <button
              onClick={(e) => {
                e.stopPropagation();
                onSnooze(task.id, 1);
              }}
              className="px-1.5 py-0.5 text-xs rounded text-text-quaternary hover:text-purple-primary hover:bg-purple-primary/10"
              title="Snooze 1 day"
            >
              +1d
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete(task.id);
              }}
              className="p-1 rounded text-text-quaternary hover:text-error hover:bg-error/10"
              title="Delete"
            >
              <Trash2 className="w-3.5 h-3.5" />
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
          className="p-1 rounded text-text-quaternary hover:text-error hover:bg-error/10 opacity-0 group-hover:opacity-100 transition-opacity"
          title="Delete"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      )}
    </motion.div>
  );
}
