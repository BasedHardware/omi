'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { X, Loader2, FolderInput, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Folder } from '@/types/folder';

interface MoveFolderDialogProps {
  isOpen: boolean;
  folders: Folder[];
  selectedCount: number;
  onClose: () => void;
  onSelectFolder: (folderId: string) => Promise<void>;
  onCreateFolder: () => void;
  isLoading?: boolean;
  loadingFolderId?: string | null;
}

export function MoveFolderDialog({
  isOpen,
  folders,
  selectedCount,
  onClose,
  onSelectFolder,
  onCreateFolder,
  isLoading = false,
  loadingFolderId = null,
}: MoveFolderDialogProps) {
  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
          />

          {/* Dialog */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className={cn(
              'fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2',
              'w-full max-w-sm rounded-2xl p-6',
              'border border-bg-tertiary bg-bg-secondary',
              'shadow-[0_16px_64px_rgba(0,0,0,0.5)]',
            )}
          >
            {/* Close button */}
            <button
              onClick={onClose}
              disabled={isLoading}
              className={cn(
                'absolute right-4 top-4 rounded-lg p-2',
                'text-text-quaternary hover:text-text-primary',
                'transition-colors hover:bg-bg-tertiary',
                'disabled:cursor-not-allowed disabled:opacity-50',
              )}
            >
              <X className="h-4 w-4" />
            </button>

            {/* Icon */}
            <div
              className={cn(
                'mb-4 h-12 w-12 rounded-xl',
                'flex items-center justify-center bg-white/[0.14]',
              )}
            >
              <FolderInput className="h-6 w-6 text-text-primary" />
            </div>

            {/* Title */}
            <h2 className="mb-2 text-lg font-semibold text-text-primary">
              Move {selectedCount} conversation{selectedCount !== 1 ? 's' : ''} to
            </h2>

            {/* Folder list */}
            <div className="mb-4 max-h-64 space-y-2 overflow-y-auto">
              {folders.length === 0 ? (
                <p className="py-4 text-center text-sm text-text-tertiary">
                  No folders yet. Create one to organize your conversations.
                </p>
              ) : (
                folders.map((folder) => (
                  <button
                    key={folder.id}
                    onClick={() => onSelectFolder(folder.id)}
                    disabled={isLoading}
                    className={cn(
                      'flex w-full items-center gap-3 rounded-xl px-4 py-3',
                      'bg-bg-tertiary hover:bg-bg-quaternary',
                      'transition-colors duration-150',
                      'disabled:cursor-not-allowed disabled:opacity-50',
                    )}
                  >
                    <span className="text-xl">{folder.emoji || '📁'}</span>
                    <span className="flex-1 text-left text-sm font-medium text-text-primary">
                      {folder.name}
                    </span>
                    {folder.conversation_count !== undefined && (
                      <span className="text-xs text-text-quaternary">
                        {folder.conversation_count}
                      </span>
                    )}
                    {loadingFolderId === folder.id && (
                      <Loader2 className="h-4 w-4 animate-spin text-text-primary" />
                    )}
                  </button>
                ))
              )}
            </div>

            {/* Divider */}
            <div className="my-4 border-t border-bg-tertiary" />

            {/* Create new folder button */}
            <button
              onClick={onCreateFolder}
              disabled={isLoading}
              className={cn(
                'flex w-full items-center gap-3 rounded-xl px-4 py-3',
                'bg-white/[0.08] hover:bg-white/[0.14]',
                'text-text-primary',
                'transition-colors duration-150',
                'disabled:cursor-not-allowed disabled:opacity-50',
              )}
            >
              <Plus className="h-5 w-5" />
              <span className="text-sm font-medium">Create new folder</span>
            </button>

            {/* Cancel button */}
            <button
              onClick={onClose}
              disabled={isLoading}
              className={cn(
                'mt-3 w-full rounded-xl px-4 py-2.5',
                'text-sm font-medium text-text-secondary',
                'bg-bg-tertiary hover:bg-bg-quaternary',
                'transition-colors duration-150',
                'disabled:cursor-not-allowed disabled:opacity-50',
              )}
            >
              Cancel
            </button>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
