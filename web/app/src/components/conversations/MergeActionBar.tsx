'use client';

import { motion } from 'framer-motion';
import { X, Merge, Loader2, FolderInput, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface MergeActionBarProps {
  selectedCount: number;
  onCancel: () => void;
  onMerge: () => void;
  onMoveToFolder?: () => void;
  onDelete?: () => void;
  isLoading?: boolean;
  inline?: boolean;
}

export function MergeActionBar({
  selectedCount,
  onCancel,
  onMerge,
  onMoveToFolder,
  onDelete,
  isLoading = false,
  inline = false,
}: MergeActionBarProps) {
  const canMerge = selectedCount >= 2;
  const canMove = selectedCount >= 1;
  const canDelete = selectedCount >= 1;

  if (inline) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.15 }}
        className="flex flex-col gap-2"
      >
        {/* Top row: selection info and cancel */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className={cn(
              'px-2.5 py-1 rounded-full text-xs font-medium',
              'bg-purple-primary/20 text-purple-primary'
            )}>
              {selectedCount} selected
            </span>
          </div>
          <button
            onClick={onCancel}
            disabled={isLoading}
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg',
              'text-xs font-medium text-text-secondary',
              'hover:bg-bg-tertiary hover:text-text-primary',
              'transition-colors',
              'disabled:opacity-50'
            )}
          >
            <X className="w-3.5 h-3.5" />
            <span>Cancel</span>
          </button>
        </div>

        {/* Bottom row: action buttons */}
        <div className="flex items-center gap-2 flex-wrap">
          {onMoveToFolder && (
            <button
              onClick={onMoveToFolder}
              disabled={!canMove || isLoading}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
                'text-xs font-medium transition-colors',
                canMove && !isLoading
                  ? 'bg-bg-tertiary text-text-primary hover:bg-bg-quaternary'
                  : 'bg-bg-tertiary/50 text-text-quaternary cursor-not-allowed'
              )}
            >
              <FolderInput className="w-3.5 h-3.5" />
              <span>Move</span>
            </button>
          )}

          {onDelete && (
            <button
              onClick={onDelete}
              disabled={!canDelete || isLoading}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
                'text-xs font-medium transition-colors',
                canDelete && !isLoading
                  ? 'bg-error/10 text-error hover:bg-error/20'
                  : 'bg-bg-tertiary/50 text-text-quaternary cursor-not-allowed'
              )}
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Delete</span>
            </button>
          )}

          <button
            onClick={onMerge}
            disabled={!canMerge || isLoading}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
              'text-xs font-medium transition-colors',
              canMerge && !isLoading
                ? 'bg-purple-primary text-white hover:bg-purple-primary/90'
                : 'bg-bg-tertiary/50 text-text-quaternary cursor-not-allowed'
            )}
          >
            {isLoading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Merge className="w-3.5 h-3.5" />
            )}
            <span>Merge</span>
          </button>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ y: 100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      exit={{ y: 100, opacity: 0 }}
      transition={{ type: 'spring', damping: 25, stiffness: 300 }}
      className={cn(
        'fixed bottom-6 left-1/2 -translate-x-1/2 z-50',
        'flex items-center gap-3',
        'px-4 py-2.5 rounded-2xl',
        'bg-bg-tertiary/80 backdrop-blur-lg',
        'border border-bg-tertiary',
        'shadow-[0_8px_32px_rgba(0,0,0,0.4)]'
      )}
    >
      <button
        onClick={onCancel}
        disabled={isLoading}
        className={cn(
          'flex items-center gap-2 px-3 py-2 rounded-xl',
          'text-sm font-medium text-text-secondary',
          'hover:bg-bg-tertiary hover:text-text-primary',
          'transition-colors duration-150',
          'disabled:opacity-50 disabled:cursor-not-allowed'
        )}
      >
        <X className="w-4 h-4" />
        <span>Cancel</span>
      </button>

      <div className={cn(
        'px-3 py-1.5 rounded-full',
        'bg-purple-primary/20 text-purple-primary',
        'text-sm font-medium'
      )}>
        {selectedCount} selected
      </div>

      {onMoveToFolder && (
        <button
          onClick={onMoveToFolder}
          disabled={!canMove || isLoading}
          className={cn(
            'flex items-center gap-2 px-4 py-2 rounded-xl',
            'text-sm font-medium',
            'transition-all duration-150',
            canMove && !isLoading
              ? 'bg-bg-tertiary text-text-primary hover:bg-bg-quaternary'
              : 'bg-bg-tertiary text-text-quaternary cursor-not-allowed'
          )}
        >
          <FolderInput className="w-4 h-4" />
          <span>Move</span>
        </button>
      )}

      {onDelete && (
        <button
          onClick={onDelete}
          disabled={!canDelete || isLoading}
          className={cn(
            'flex items-center gap-2 px-4 py-2 rounded-xl',
            'text-sm font-medium',
            'transition-all duration-150',
            canDelete && !isLoading
              ? 'bg-error/10 text-error hover:bg-error/20'
              : 'bg-bg-tertiary text-text-quaternary cursor-not-allowed'
          )}
        >
          <Trash2 className="w-4 h-4" />
          <span>Delete</span>
        </button>
      )}

      <button
        onClick={onMerge}
        disabled={!canMerge || isLoading}
        className={cn(
          'flex items-center gap-2 px-4 py-2 rounded-xl',
          'text-sm font-medium',
          'transition-all duration-150',
          canMerge && !isLoading
            ? 'bg-purple-primary text-white hover:bg-purple-primary/90'
            : 'bg-bg-tertiary text-text-quaternary cursor-not-allowed'
        )}
      >
        {isLoading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Merge className="w-4 h-4" />
        )}
        <span>Merge</span>
      </button>
    </motion.div>
  );
}

