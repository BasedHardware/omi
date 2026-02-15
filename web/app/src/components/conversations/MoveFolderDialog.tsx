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
              'fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50',
              'w-full max-w-sm p-6 rounded-2xl',
              'bg-bg-secondary border border-bg-tertiary',
              'shadow-[0_16px_64px_rgba(0,0,0,0.5)]'
            )}
          >
            {/* Close button */}
            <button
              onClick={onClose}
              disabled={isLoading}
              className={cn(
                'absolute top-4 right-4 p-2 rounded-lg',
                'text-text-quaternary hover:text-text-primary',
                'hover:bg-bg-tertiary transition-colors',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              <X className="w-4 h-4" />
            </button>

            {/* Icon */}
            <div className={cn(
              'w-12 h-12 rounded-xl mb-4',
              'bg-purple-primary/20 flex items-center justify-center'
            )}>
              <FolderInput className="w-6 h-6 text-purple-primary" />
            </div>

            {/* Title */}
            <h2 className="text-lg font-semibold text-text-primary mb-2">
              Move {selectedCount} conversation{selectedCount !== 1 ? 's' : ''} to
            </h2>

            {/* Folder list */}
            <div className="space-y-2 mb-4 max-h-64 overflow-y-auto">
              {folders.length === 0 ? (
                <p className="text-sm text-text-tertiary py-4 text-center">
                  No folders yet. Create one to organize your conversations.
                </p>
              ) : (
                folders.map((folder) => (
                  <button
                    key={folder.id}
                    onClick={() => onSelectFolder(folder.id)}
                    disabled={isLoading}
                    className={cn(
                      'w-full flex items-center gap-3 px-4 py-3 rounded-xl',
                      'bg-bg-tertiary hover:bg-bg-quaternary',
                      'transition-colors duration-150',
                      'disabled:opacity-50 disabled:cursor-not-allowed'
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
                      <Loader2 className="w-4 h-4 animate-spin text-purple-primary" />
                    )}
                  </button>
                ))
              )}
            </div>

            {/* Divider */}
            <div className="border-t border-bg-tertiary my-4" />

            {/* Create new folder button */}
            <button
              onClick={onCreateFolder}
              disabled={isLoading}
              className={cn(
                'w-full flex items-center gap-3 px-4 py-3 rounded-xl',
                'bg-purple-primary/10 hover:bg-purple-primary/20',
                'text-purple-primary',
                'transition-colors duration-150',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              <Plus className="w-5 h-5" />
              <span className="text-sm font-medium">Create new folder</span>
            </button>

            {/* Cancel button */}
            <button
              onClick={onClose}
              disabled={isLoading}
              className={cn(
                'w-full mt-3 px-4 py-2.5 rounded-xl',
                'text-sm font-medium text-text-secondary',
                'bg-bg-tertiary hover:bg-bg-quaternary',
                'transition-colors duration-150',
                'disabled:opacity-50 disabled:cursor-not-allowed'
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
