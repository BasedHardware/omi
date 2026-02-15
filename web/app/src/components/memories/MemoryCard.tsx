'use client';

import { useState, useRef, useEffect, memo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Lightbulb,
  FileText,
  Settings,
  Pencil,
  Trash2,
  Check,
  Lock,
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
  isHighlighted?: boolean;
  isSelected?: boolean;
  onToggleSelect?: (id: string) => void;
  // Double-click to enter selection mode
  onEnterSelectionMode?: (id: string) => void;
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

export const MemoryCard = memo(function MemoryCard({
  memory,
  onEdit,
  onDelete,
  onToggleVisibility,
  onAccept,
  onReject,
  isHighlighted,
  isSelected,
  onToggleSelect,
  onEnterSelectionMode,
}: MemoryCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(memory.content);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Check if content needs truncation (roughly 2 lines worth at ~120 chars/line)
  const needsTruncation = memory.content.length > 200;

  const categoryInfo = categoryConfig[memory.category];
  const needsReview = !memory.reviewed && memory.user_review === null;

  useEffect(() => {
    if (isEditing && textareaRef.current) {
      textareaRef.current.focus();
      textareaRef.current.select();
      // Auto-resize to fit content
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px';
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

  const handleTextDoubleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsEditing(true);
  };

  const handleCardDoubleClick = () => {
    // Double-click on card enters selection mode and selects this memory
    // Only trigger if not already in selection mode and handler is provided
    if (!onToggleSelect && onEnterSelectionMode) {
      onEnterSelectionMode(memory.id);
    }
  };

  return (
    <motion.div
      id={`memory-${memory.id}`}
      layout
      initial={false}
      animate={{ opacity: isDeleting ? 0.5 : 1 }}
      exit={{ opacity: 0, x: -20 }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onDoubleClick={handleCardDoubleClick}
      className={cn(
        'noise-overlay group relative rounded-xl p-4',
        'bg-white/[0.02] border border-white/[0.06]',
        'transition-all duration-150',
        'hover:bg-white/[0.05] hover:border-purple-primary/30',
        needsReview && 'border-l-4 border-l-warning',
        isHighlighted && 'ring-2 ring-purple-primary bg-purple-primary/10 animate-pulse',
        isSelected && 'bg-purple-primary/5 border-purple-primary/50'
      )}
    >
      {/* Content */}
      <div className="flex items-start gap-3">
        {/* Selection checkbox */}
        {onToggleSelect && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggleSelect(memory.id);
            }}
            className={cn(
              'flex-shrink-0 w-5 h-5 mt-0.5 rounded',
              'border-2 transition-all duration-200',
              'flex items-center justify-center',
              isSelected
                ? 'bg-purple-primary border-purple-primary'
                : 'border-text-quaternary hover:border-purple-primary'
            )}
            aria-label={isSelected ? 'Deselect memory' : 'Select memory'}
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

        {/* Category icon */}
        <div className={cn('flex-shrink-0 mt-0.5', categoryInfo.color)}>
          {categoryInfo.icon}
        </div>

        {/* Main content */}
        <div className="flex-1 min-w-0">
          {isEditing ? (
            <textarea
              ref={textareaRef}
              value={editContent}
              onChange={(e) => {
                setEditContent(e.target.value);
                // Auto-resize as user types
                e.target.style.height = 'auto';
                e.target.style.height = e.target.scrollHeight + 'px';
              }}
              onBlur={handleSaveEdit}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSaveEdit();
                } else if (e.key === 'Escape') {
                  handleCancelEdit();
                }
              }}
              className={cn(
                'w-full text-sm bg-bg-secondary border border-purple-primary/50',
                'rounded px-2 py-1.5 resize-none overflow-hidden',
                'text-text-primary outline-none leading-relaxed',
                'focus:ring-1 focus:ring-purple-primary/30'
              )}
              placeholder="Enter memory content..."
              rows={1}
            />
          ) : (
            <div>
              <p
                onDoubleClick={handleTextDoubleClick}
                title="Double-click to edit"
                className={cn(
                  'text-sm text-text-primary leading-relaxed',
                  'cursor-text select-none',
                  'hover:bg-bg-quaternary/30 rounded px-1 -mx-1 transition-colors',
                  !isExpanded && needsTruncation && 'line-clamp-2'
                )}
              >
                {memory.content}
              </p>
              {needsTruncation && (
                <button
                  onClick={() => setIsExpanded(!isExpanded)}
                  className="text-xs text-text-quaternary hover:text-purple-primary mt-1 transition-colors"
                >
                  {isExpanded ? 'Show less' : 'Show more'}
                </button>
              )}
            </div>
          )}

          {/* Metadata row */}
          {!isEditing && (
            <div className="flex items-center justify-between gap-2 mt-2">
              <div className="flex items-center gap-1.5 flex-wrap">
                {/* Category badge - only show for non-system categories */}
                {memory.category !== 'system' && (
                  <span
                    className={cn(
                      'inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs',
                      memory.category === 'interesting' && 'bg-purple-primary/10 text-purple-primary',
                      memory.category === 'manual' && 'bg-blue-400/10 text-blue-400'
                    )}
                  >
                    {categoryInfo.label}
                  </span>
                )}

                {/* Tags on the left */}
                {memory.tags && memory.tags.length > 0 && (
                  <>
                    {memory.tags.slice(0, 4).map((tag) => (
                      <span
                        key={tag}
                        className="px-2 py-0.5 rounded text-xs bg-bg-quaternary text-text-tertiary"
                      >
                        {tag}
                      </span>
                    ))}
                    {memory.tags.length > 4 && (
                      <span className="text-xs text-text-quaternary">
                        +{memory.tags.length - 4}
                      </span>
                    )}
                  </>
                )}
              </div>

              {/* Date and indicators on the right */}
              <div className="flex items-center gap-2 flex-shrink-0">
                {/* Date */}
                <span className="text-xs text-text-quaternary">
                  {formatDate(memory.created_at)}
                </span>

                {/* Private indicator */}
                {memory.visibility === 'private' && (
                  <button
                    onClick={handleToggleVisibility}
                    className={cn(
                      'p-0.5 rounded transition-colors cursor-pointer',
                      'text-text-quaternary hover:text-text-tertiary'
                    )}
                    title="Private memory (click to make public)"
                  >
                    <Lock className="w-3 h-3" />
                  </button>
                )}

                {/* Edited indicator */}
                {memory.edited && (
                  <span className="text-xs text-text-quaternary italic">edited</span>
                )}
              </div>
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
});
