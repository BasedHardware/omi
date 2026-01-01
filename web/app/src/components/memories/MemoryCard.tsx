'use client';

import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Lightbulb,
  FileText,
  Settings,
  Pencil,
  Trash2,
  Check,
  X,
  Eye,
  EyeOff,
  ThumbsUp,
  ThumbsDown,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Memory, MemoryCategory, MemoryVisibility } from '@/types/conversation';

interface MemoryCardProps {
  memory: Memory;
  onEdit: (id: string, content: string) => Promise<boolean>;
  onDelete: (id: string) => Promise<boolean>;
  onToggleVisibility: (id: string, visibility: MemoryVisibility) => Promise<boolean>;
  onAccept?: (id: string) => Promise<boolean>;
  onReject?: (id: string) => Promise<boolean>;
}

const categoryConfig: Record<MemoryCategory, { icon: React.ReactNode; label: string; color: string }> = {
  interesting: {
    icon: <Lightbulb className="w-4 h-4" />,
    label: 'Interesting',
    color: 'text-purple-primary',
  },
  manual: {
    icon: <FileText className="w-4 h-4" />,
    label: 'Manual',
    color: 'text-blue-400',
  },
  system: {
    icon: <Settings className="w-4 h-4" />,
    label: 'System',
    color: 'text-text-quaternary',
  },
};

export function MemoryCard({
  memory,
  onEdit,
  onDelete,
  onToggleVisibility,
  onAccept,
  onReject,
}: MemoryCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(memory.content);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const categoryInfo = categoryConfig[memory.category];
  const needsReview = !memory.reviewed && memory.user_review === null;

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleSaveEdit = async () => {
    if (editContent.trim() && editContent !== memory.content) {
      const success = await onEdit(memory.id, editContent.trim());
      if (success) {
        setIsEditing(false);
      }
    } else {
      setIsEditing(false);
      setEditContent(memory.content);
    }
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditContent(memory.content);
  };

  const handleDelete = async () => {
    setIsDeleting(true);
    await onDelete(memory.id);
  };

  const handleToggleVisibility = async () => {
    const newVisibility = memory.visibility === 'public' ? 'private' : 'public';
    await onToggleVisibility(memory.id, newVisibility);
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: isDeleting ? 0.5 : 1, y: 0 }}
      exit={{ opacity: 0, x: -20 }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className={cn(
        'group relative rounded-xl p-4',
        'bg-bg-tertiary border border-bg-quaternary',
        'transition-all duration-150',
        'hover:bg-bg-quaternary/50 hover:border-purple-primary/30',
        needsReview && 'border-l-4 border-l-warning'
      )}
    >
      {/* Content */}
      <div className="flex items-start gap-3">
        {/* Category icon */}
        <div className={cn('flex-shrink-0 mt-0.5', categoryInfo.color)}>
          {categoryInfo.icon}
        </div>

        {/* Main content */}
        <div className="flex-1 min-w-0">
          {isEditing ? (
            <div className="space-y-2">
              <textarea
                ref={inputRef}
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSaveEdit();
                  } else if (e.key === 'Escape') {
                    handleCancelEdit();
                  }
                }}
                className={cn(
                  'w-full px-3 py-2 rounded-lg resize-none',
                  'bg-bg-secondary border border-bg-quaternary',
                  'text-sm text-text-primary',
                  'focus:outline-none focus:ring-2 focus:ring-purple-primary/50',
                  'placeholder:text-text-quaternary'
                )}
                rows={3}
                placeholder="Enter memory content..."
              />
              <div className="flex justify-end gap-2">
                <button
                  onClick={handleCancelEdit}
                  className={cn(
                    'p-1.5 rounded-md',
                    'text-text-tertiary hover:text-text-primary',
                    'hover:bg-bg-tertiary transition-colors'
                  )}
                >
                  <X className="w-4 h-4" />
                </button>
                <button
                  onClick={handleSaveEdit}
                  className={cn(
                    'p-1.5 rounded-md',
                    'text-success hover:text-success',
                    'hover:bg-success/10 transition-colors'
                  )}
                >
                  <Check className="w-4 h-4" />
                </button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-text-primary leading-relaxed">{memory.content}</p>
          )}

          {/* Metadata row */}
          {!isEditing && (
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              {/* Category badge */}
              <span
                className={cn(
                  'inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs',
                  memory.category === 'interesting' && 'bg-purple-primary/10 text-purple-primary',
                  memory.category === 'manual' && 'bg-blue-400/10 text-blue-400',
                  memory.category === 'system' && 'bg-bg-quaternary text-text-quaternary'
                )}
              >
                {categoryInfo.label}
              </span>

              {/* Date */}
              <span className="text-xs text-text-quaternary">
                {formatDate(memory.created_at)}
              </span>

              {/* Visibility badge */}
              <button
                onClick={handleToggleVisibility}
                className={cn(
                  'inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs',
                  'transition-colors cursor-pointer',
                  memory.visibility === 'public'
                    ? 'bg-success/10 text-success hover:bg-success/20'
                    : 'bg-warning/10 text-warning hover:bg-warning/20'
                )}
              >
                {memory.visibility === 'public' ? (
                  <>
                    <Eye className="w-3 h-3" />
                    Public
                  </>
                ) : (
                  <>
                    <EyeOff className="w-3 h-3" />
                    Private
                  </>
                )}
              </button>

              {/* Edited indicator */}
              {memory.edited && (
                <span className="text-xs text-text-quaternary italic">edited</span>
              )}
            </div>
          )}
        </div>

        {/* Action buttons - show on hover or when card needs review */}
        <AnimatePresence>
          {(isHovered || needsReview) && !isEditing && (
            <motion.div
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 10 }}
              className="flex items-center gap-1 flex-shrink-0"
            >
              {needsReview && onAccept && onReject ? (
                // Review buttons
                <>
                  <button
                    onClick={() => onReject?.(memory.id)}
                    className={cn(
                      'p-2 rounded-lg',
                      'text-error hover:bg-error/10',
                      'transition-colors'
                    )}
                    title="Reject memory"
                  >
                    <ThumbsDown className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => onAccept?.(memory.id)}
                    className={cn(
                      'p-2 rounded-lg',
                      'text-success hover:bg-success/10',
                      'transition-colors'
                    )}
                    title="Accept memory"
                  >
                    <ThumbsUp className="w-4 h-4" />
                  </button>
                </>
              ) : (
                // Edit/Delete buttons
                <>
                  <button
                    onClick={() => setIsEditing(true)}
                    className={cn(
                      'p-2 rounded-lg',
                      'text-text-tertiary hover:text-text-primary',
                      'hover:bg-bg-tertiary transition-colors'
                    )}
                    title="Edit memory"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button
                    onClick={handleDelete}
                    disabled={isDeleting}
                    className={cn(
                      'p-2 rounded-lg',
                      'text-text-tertiary hover:text-error',
                      'hover:bg-error/10 transition-colors',
                      isDeleting && 'opacity-50 cursor-not-allowed'
                    )}
                    title="Delete memory"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
