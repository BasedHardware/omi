'use client';

import { useState, useRef, useEffect, memo } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
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
import type { MemoryUseAction } from '@/lib/api';

type MemoryBeliefView = Memory & {
  belief_class?: string | null;
  currency_band?: string | null;
  as_of?: string | null;
  belief_computed_at?: string | null;
  invalid_at?: string | null;
  superseded_by?: string | null;
  ledger_status?: string | null;
  arguments?: Record<string, unknown>;
};

interface MemoryCardProps {
  memory: Memory;
  onEdit: (id: string, content: string) => Promise<boolean>;
  onDelete: (id: string) => Promise<boolean>;
  onToggleVisibility: (id: string, visibility: MemoryVisibility) => Promise<boolean>;
  onAccept?: (id: string) => Promise<boolean>;
  onReject?: (id: string) => Promise<boolean>;
  onSetUse?: (id: string, action: MemoryUseAction) => Promise<boolean>;
  isHighlighted?: boolean;
  isSelected?: boolean;
  onToggleSelect?: (id: string) => void;
  // Double-click to enter selection mode
  onEnterSelectionMode?: (id: string) => void;
}

const categoryConfig: Partial<
  Record<MemoryCategory, { icon: React.ReactNode; label: string; color: string }>
> = {
  interesting: {
    icon: <Lightbulb className="h-4 w-4" />,
    label: 'Interesting',
    color: 'text-white',
  },
  manual: {
    icon: <FileText className="h-4 w-4" />,
    label: 'Manual',
    color: 'text-blue-400',
  },
  system: {
    icon: <Settings className="h-4 w-4" />,
    label: 'System',
    color: 'text-text-quaternary',
  },
};

const DEFAULT_CATEGORY_CONFIG = {
  icon: <FileText className="h-4 w-4" />,
  label: 'Memory',
  color: 'text-text-quaternary',
};

export const MemoryCard = memo(function MemoryCard({
  memory,
  onEdit,
  onDelete,
  onToggleVisibility,
  onAccept,
  onReject,
  onSetUse,
  isHighlighted,
  isSelected,
  onToggleSelect,
  onEnterSelectionMode,
}: MemoryCardProps) {
  const beliefMemory = memory as MemoryBeliefView;
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(memory.content);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [contentOverflows, setContentOverflows] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const contentRef = useRef<HTMLParagraphElement>(null);
  const reduceMotion = useReducedMotion();

  // Check if content needs truncation (roughly 2 lines worth at ~120 chars/line)
  const needsTruncation = memory.content.length > 200 || contentOverflows;

  const categoryInfo =
    (memory.category && categoryConfig[memory.category]) || DEFAULT_CATEGORY_CONFIG;
  const needsReview = !memory.reviewed && memory.user_review === null;
  const memoryUse =
    beliefMemory.arguments?.memory_use &&
    typeof beliefMemory.arguments.memory_use === 'object'
      ? (beliefMemory.arguments.memory_use as { suppressed?: boolean; useful?: boolean })
      : undefined;
  const isSuppressed = memoryUse?.suppressed === true;
  const isUseful = memoryUse?.useful === true;
  const isInactiveHistorical = Boolean(
    beliefMemory.invalid_at ||
      beliefMemory.superseded_by ||
      (beliefMemory.ledger_status && beliefMemory.ledger_status !== 'active'),
  );

  useEffect(() => {
    if (isEditing && textareaRef.current) {
      textareaRef.current.focus();
      textareaRef.current.select();
      // Auto-resize to fit content
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px';
    }
  }, [isEditing]);

  useEffect(() => {
    const element = contentRef.current;
    if (!element || isExpanded) return;

    const updateOverflow = () => {
      setContentOverflows(element.scrollHeight > element.clientHeight);
    };
    updateOverflow();

    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(updateOverflow);
    observer.observe(element);
    return () => observer.disconnect();
  }, [isExpanded, memory.content]);

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

  const handleSetUse = async (action: MemoryUseAction) => {
    if (!onSetUse || isInactiveHistorical) return false;
    return onSetUse(memory.id, action);
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

  const beliefLabel = beliefMemory.currency_band
    ? beliefMemory.currency_band.replaceAll('_', ' ')
    : beliefMemory.belief_computed_at
    ? 'Needs classification'
    : null;

  const formatEvidenceDate = (dateString: string | null | undefined) => {
    if (!dateString) return null;
    const date = new Date(dateString);
    if (Number.isNaN(date.getTime())) return null;
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
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
      layout={!reduceMotion}
      initial={false}
      animate={{ opacity: isDeleting ? 0.5 : 1 }}
      exit={{
        opacity: 0,
        transform: reduceMotion ? 'translateX(0)' : 'translateX(-12px)',
      }}
      transition={{
        duration: reduceMotion ? 0.08 : 0.18,
        ease: [0.23, 1, 0.32, 1],
      }}
      onDoubleClick={handleCardDoubleClick}
      className={cn(
        'noise-overlay group relative rounded-xl p-4',
        'border border-white/[0.06] bg-white/[0.02]',
        'transition-colors duration-150',
        'hover:border-white/30 hover:bg-white/[0.05]',
        needsReview && 'border-l-4 border-l-warning',
        isHighlighted && 'animate-pulse bg-white/10 ring-2 ring-white',
        isSelected && 'border-white/50 bg-white/5',
      )}
    >
      {/* Content */}
      <div data-testid="memory-card-content" className="flex items-start gap-3">
        {/* Selection checkbox */}
        {onToggleSelect && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggleSelect(memory.id);
            }}
            className={cn(
              'mt-0.5 h-5 w-5 flex-shrink-0 rounded',
              'border-2 transition-all duration-200',
              'flex items-center justify-center',
              isSelected
                ? 'border-white bg-white'
                : 'border-text-quaternary hover:border-white',
            )}
            aria-label={isSelected ? 'Deselect memory' : 'Select memory'}
          >
            <AnimatePresence>
              {isSelected && (
                <motion.div
                  initial={{
                    opacity: 0,
                    transform: reduceMotion ? 'scale(1)' : 'scale(0.95)',
                  }}
                  animate={{ opacity: 1, transform: 'scale(1)' }}
                  exit={{
                    opacity: 0,
                    transform: reduceMotion ? 'scale(1)' : 'scale(0.95)',
                  }}
                  transition={{ duration: reduceMotion ? 0.08 : 0.12 }}
                >
                  <Check className="h-3 w-3 text-bg-primary" strokeWidth={3} />
                </motion.div>
              )}
            </AnimatePresence>
          </button>
        )}

        {/* Category icon */}
        <div className={cn('mt-0.5 flex-shrink-0', categoryInfo.color)}>
          {categoryInfo.icon}
        </div>

        {/* Main content */}
        <div className="min-w-0 flex-1">
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
                'w-full border border-white/50 bg-bg-secondary text-sm',
                'resize-none overflow-hidden rounded px-2 py-1.5',
                'leading-relaxed text-text-primary outline-none',
                'focus:ring-1 focus:ring-white/30',
              )}
              placeholder="Enter memory content..."
              rows={1}
            />
          ) : (
            <div>
              <p
                ref={contentRef}
                onDoubleClick={handleTextDoubleClick}
                title="Double-click to edit"
                className={cn(
                  'break-words text-sm leading-relaxed text-text-primary [overflow-wrap:anywhere]',
                  'cursor-text select-none',
                  '-mx-1 rounded pl-1 pr-20 transition-colors hover:bg-bg-quaternary/30',
                  !isExpanded && 'line-clamp-2',
                )}
              >
                {memory.content}
              </p>
              {needsTruncation && (
                <button
                  onClick={() => setIsExpanded(!isExpanded)}
                  className="mt-1 text-xs text-text-quaternary transition-colors hover:text-white"
                >
                  {isExpanded ? 'Show less' : 'Show more'}
                </button>
              )}
            </div>
          )}

          {/* Metadata row */}
          {!isEditing && (
            <div
              data-testid="memory-card-metadata"
              className="mt-2 flex items-center justify-between gap-2"
            >
              <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
                {/* Category badge - only show for non-system categories */}
                {memory.category !== 'system' && (
                  <span
                    className={cn(
                      'inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs',
                      memory.category === 'interesting' && 'bg-white/10 text-white',
                      memory.category === 'manual' && 'bg-blue-400/10 text-blue-400',
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
                        className="max-w-full truncate rounded bg-bg-quaternary px-2 py-0.5 text-xs text-text-tertiary"
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

                {beliefLabel && (
                  <span
                    className="inline-flex items-center gap-1 rounded-md bg-white/10 px-2 py-0.5 text-xs capitalize text-text-secondary"
                    title={
                      beliefMemory.belief_computed_at
                        ? `Assessed ${
                            formatEvidenceDate(beliefMemory.belief_computed_at) ||
                            'recently'
                          }`
                        : undefined
                    }
                  >
                    {beliefLabel}
                  </span>
                )}

                {beliefMemory.as_of && (
                  <span className="text-xs text-text-quaternary">
                    Evidence{' '}
                    {formatEvidenceDate(beliefMemory.as_of) || beliefMemory.as_of}
                  </span>
                )}
              </div>

              {/* Date and indicators on the right */}
              <div className="flex flex-shrink-0 items-center gap-2">
                {/* Date */}
                <span className="whitespace-nowrap text-xs text-text-quaternary">
                  {formatDate(memory.created_at)}
                </span>

                {/* Private indicator */}
                {memory.visibility === 'private' && (
                  <button
                    onClick={handleToggleVisibility}
                    className={cn(
                      'cursor-pointer rounded p-0.5 transition-colors',
                      'text-text-quaternary hover:text-text-tertiary',
                    )}
                    title="Private memory (click to make public)"
                  >
                    <Lock className="h-3 w-3" />
                  </button>
                )}

                {/* Edited indicator */}
                {memory.edited && (
                  <span className="text-xs italic text-text-quaternary">edited</span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Action buttons - show on hover or when card needs review */}
        {!isEditing && (
          <div
            data-testid="memory-card-actions"
            className={cn(
              'absolute right-3 top-3 z-10 flex items-center gap-1',
              'transition-opacity duration-150',
              needsReview
                ? 'opacity-100'
                : 'opacity-100 sm:pointer-events-none sm:opacity-0 sm:group-focus-within:pointer-events-auto sm:group-focus-within:opacity-100 sm:group-hover:pointer-events-auto sm:group-hover:opacity-100',
            )}
          >
            {onSetUse && !isInactiveHistorical && (
              <>
                <button
                  onClick={() => handleSetUse(isSuppressed ? 'allow' : 'suppress')}
                  className={cn(
                    'rounded-lg px-2 py-1 text-xs transition-colors',
                    isSuppressed
                      ? 'text-success hover:bg-success/10'
                      : 'text-text-tertiary hover:bg-error/10 hover:text-error',
                  )}
                  title={
                    isSuppressed
                      ? 'Allow Omi to use this memory'
                      : "Don't use this memory"
                  }
                >
                  {isSuppressed ? 'Allow use' : "Don't use"}
                </button>
                {!isSuppressed && !needsReview && (
                  <button
                    onClick={() => handleSetUse('useful')}
                    className={cn(
                      'rounded-lg p-2 transition-colors',
                      isUseful
                        ? 'text-success hover:bg-success/10'
                        : 'text-text-tertiary hover:bg-bg-tertiary hover:text-text-primary',
                    )}
                    title="Mark memory useful"
                    aria-label="Mark memory useful"
                  >
                    <ThumbsUp className="h-4 w-4" />
                  </button>
                )}
              </>
            )}
            {needsReview && onAccept && onReject ? (
              // Review buttons
              <>
                <button
                  onClick={() => onReject?.(memory.id)}
                  className={cn(
                    'rounded-lg p-2',
                    'text-error hover:bg-error/10',
                    'transition-colors',
                  )}
                  title="Reject memory"
                >
                  <ThumbsDown className="h-4 w-4" />
                </button>
                <button
                  onClick={() => onAccept?.(memory.id)}
                  className={cn(
                    'rounded-lg p-2',
                    'text-success hover:bg-success/10',
                    'transition-colors',
                  )}
                  title="Accept memory"
                >
                  <ThumbsUp className="h-4 w-4" />
                </button>
              </>
            ) : (
              // Edit/Delete buttons
              <>
                <button
                  onClick={() => setIsEditing(true)}
                  className={cn(
                    'rounded-lg p-2',
                    'text-text-tertiary hover:text-text-primary',
                    'transition-colors hover:bg-bg-tertiary',
                  )}
                  title="Edit memory"
                >
                  <Pencil className="h-4 w-4" />
                </button>
                <button
                  onClick={handleDelete}
                  disabled={isDeleting}
                  className={cn(
                    'rounded-lg p-2',
                    'text-text-tertiary hover:text-error',
                    'transition-colors hover:bg-error/10',
                    isDeleting && 'cursor-not-allowed opacity-50',
                  )}
                  title="Delete memory"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
});
