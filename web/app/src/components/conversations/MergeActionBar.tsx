'use client';

import { motion } from 'framer-motion';
import { X, Merge, Loader2, FolderInput } from 'lucide-react';
import { cn } from '@/lib/utils';

interface MergeActionBarProps {
  selectedCount: number;
  onCancel: () => void;
  onMerge: () => void;
  onMoveToFolder?: () => void;
  isLoading?: boolean;
}

export function MergeActionBar({
  selectedCount,
  onCancel,
  onMerge,
  onMoveToFolder,
  isLoading = false,
}: MergeActionBarProps) {
  const canMerge = selectedCount >= 2;
  const canMove = selectedCount >= 1;

  return (
    <motion.div
      initial={{ y: 100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      exit={{ y: 100, opacity: 0 }}
      transition={{ type: 'spring', damping: 25, stiffness: 300 }}
      className={cn(
        'fixed bottom-6 left-1/2 -translate-x-1/2 z-50',
        'flex items-center gap-3',
        'px-4 py-3 rounded-2xl',
        'bg-bg-secondary/95 backdrop-blur-lg',
        'border border-bg-tertiary',
        'shadow-[0_8px_32px_rgba(0,0,0,0.4)]'
      )}
    >
      {/* Cancel button */}
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

      {/* Selection count badge */}
      <div className={cn(
        'px-3 py-1.5 rounded-full',
        'bg-purple-primary/20 text-purple-primary',
        'text-sm font-medium'
      )}>
        {selectedCount} selected
      </div>

      {/* Move to Folder button */}
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

      {/* Merge button */}
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
