'use client';

import { useState, useEffect } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X, Loader2, FolderPlus, Pencil } from 'lucide-react';
import { cn } from '@/lib/utils';
import { FOLDER_EMOJIS, FOLDER_COLORS } from '@/types/folder';
import type { Folder, CreateFolderRequest, UpdateFolderRequest } from '@/types/folder';

interface FolderDialogProps {
  isOpen: boolean;
  folder?: Folder | null; // If provided, we're editing; otherwise creating
  onClose: () => void;
  onSubmit: (data: CreateFolderRequest | UpdateFolderRequest) => Promise<void>;
  isLoading?: boolean;
}

export function FolderDialog({
  isOpen,
  folder,
  onClose,
  onSubmit,
  isLoading = false,
}: FolderDialogProps) {
  const isEditing = !!folder;

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [emoji, setEmoji] = useState<string>(FOLDER_EMOJIS[0]);
  const [color, setColor] = useState<string>(FOLDER_COLORS[0].value);

  // Reset form when dialog opens/closes or folder changes
  useEffect(() => {
    if (isOpen) {
      if (folder) {
        setName(folder.name);
        setDescription(folder.description || '');
        setEmoji(folder.emoji || FOLDER_EMOJIS[0]);
        setColor(folder.color || FOLDER_COLORS[0].value);
      } else {
        setName('');
        setDescription('');
        setEmoji(FOLDER_EMOJIS[0]);
        setColor(FOLDER_COLORS[0].value);
      }
    }
  }, [isOpen, folder]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    await onSubmit({
      name: name.trim(),
      description: description.trim() || undefined,
      icon: emoji, // Backend expects 'icon' field with emoji character
      color,
    });
  };

  const isValid = name.trim().length > 0;

  return (
    <Dialog.Root open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        {/* Backdrop */}
        <Dialog.Overlay
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0"
        />

        {/* Dialog Container - Centered with flexbox */}
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 text-center">
          <Dialog.Content
            className={cn(
              'w-full max-w-md p-6 rounded-2xl text-left align-middle',
              'bg-bg-secondary border border-bg-tertiary shadow-[0_16px_64px_rgba(0,0,0,0.5)]',
              'max-h-[85vh] overflow-y-auto',
              'duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]',
              'outline-none focus:outline-none' // Remove default browser focus ring
            )}
          >
            <Dialog.Title className="sr-only">
              {isEditing ? 'Edit Folder' : 'Create Folder'}
            </Dialog.Title>

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
              'flex items-center justify-center'
            )} style={{ backgroundColor: `${color}20` }}>
              {isEditing ? (
                <Pencil className="w-6 h-6" style={{ color }} />
              ) : (
                <FolderPlus className="w-6 h-6" style={{ color }} />
              )}
            </div>

            {/* Visible Title */}
            <h2 className="text-lg font-semibold text-text-primary mb-4">
              {isEditing ? 'Edit Folder' : 'Create Folder'}
            </h2>

            <form onSubmit={handleSubmit}>
              {/* Folder name input */}
              <div className="mb-4">
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Folder name
                </label>
                <div className="flex items-center gap-2">
                  <span className="text-2xl">{emoji}</span>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Enter folder name..."
                    disabled={isLoading}
                    maxLength={100}
                    className={cn(
                      'flex-1 px-3 py-2 rounded-lg',
                      'bg-bg-tertiary border border-bg-quaternary',
                      'text-text-primary placeholder:text-text-quaternary',
                      'focus:outline-none focus:ring-2 focus:ring-purple-primary/50',
                      'disabled:opacity-50'
                    )}
                    autoFocus
                  />
                </div>
              </div>

              {/* Description input */}
              <div className="mb-4">
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Description <span className="text-text-quaternary font-normal">(optional)</span>
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="E.g., Work meetings and project discussions"
                  disabled={isLoading}
                  maxLength={500}
                  rows={2}
                  className={cn(
                    'w-full px-3 py-2 rounded-lg resize-none',
                    'bg-bg-tertiary border border-bg-quaternary',
                    'text-text-primary placeholder:text-text-quaternary',
                    'text-sm',
                    'focus:outline-none focus:ring-2 focus:ring-purple-primary/50',
                    'disabled:opacity-50'
                  )}
                />
                <p className="mt-1 text-xs text-text-quaternary">
                  Helps AI auto-categorize conversations into this folder
                </p>
              </div>

              {/* Emoji picker */}
              <div className="mb-4">
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Icon
                </label>
                <div className="flex flex-wrap gap-2">
                  {FOLDER_EMOJIS.map((e) => (
                    <button
                      key={e}
                      type="button"
                      onClick={() => setEmoji(e)}
                      disabled={isLoading}
                      className={cn(
                        'w-10 h-10 rounded-lg text-xl',
                        'flex items-center justify-center',
                        'transition-all duration-150',
                        emoji === e
                          ? 'bg-purple-primary/20 ring-2 ring-purple-primary'
                          : 'bg-bg-tertiary hover:bg-bg-quaternary',
                        'disabled:opacity-50 disabled:cursor-not-allowed'
                      )}
                    >
                      {e}
                    </button>
                  ))}
                </div>
              </div>

              {/* Color picker */}
              <div className="mb-6">
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Color
                </label>
                <div className="flex flex-wrap gap-2">
                  {FOLDER_COLORS.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => setColor(c.value)}
                      disabled={isLoading}
                      className={cn(
                        'w-8 h-8 rounded-full',
                        'transition-all duration-150',
                        color === c.value
                          ? 'ring-2 ring-offset-2 ring-offset-bg-secondary'
                          : 'hover:scale-110',
                        'disabled:opacity-50 disabled:cursor-not-allowed'
                      )}
                      style={{
                        backgroundColor: c.value,
                        '--tw-ring-color': c.value,
                      } as React.CSSProperties}
                      title={c.label}
                    />
                  ))}
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={onClose}
                  disabled={isLoading}
                  className={cn(
                    'flex-1 px-4 py-2.5 rounded-xl',
                    'text-sm font-medium text-text-secondary',
                    'bg-bg-tertiary hover:bg-bg-quaternary',
                    'transition-colors duration-150',
                    'disabled:opacity-50 disabled:cursor-not-allowed'
                  )}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!isValid || isLoading}
                  className={cn(
                    'flex-1 flex items-center justify-center gap-2',
                    'px-4 py-2.5 rounded-xl',
                    'text-sm font-medium text-white',
                    'transition-colors duration-150',
                    'disabled:opacity-50 disabled:cursor-not-allowed'
                  )}
                  style={{ backgroundColor: isValid ? color : undefined }}
                >
                  {isLoading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : null}
                  <span>{isEditing ? 'Save Changes' : 'Create Folder'}</span>
                </button>
              </div>
            </form>
          </Dialog.Content>
        </div>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

// Confirm delete folder dialog
interface DeleteFolderDialogProps {
  isOpen: boolean;
  folder: Folder | null;
  onClose: () => void;
  onConfirm: () => Promise<void>;
  isLoading?: boolean;
}

export function DeleteFolderDialog({
  isOpen,
  folder,
  onClose,
  onConfirm,
  isLoading = false,
}: DeleteFolderDialogProps) {
  if (!folder) return null;

  return (
    <Dialog.Root open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        {/* Backdrop */}
        <Dialog.Overlay
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0"
        />

        {/* Dialog Container */}
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 text-center">
          <Dialog.Content
            className={cn(
              'w-full max-w-sm p-6 rounded-2xl text-left align-middle',
              'bg-bg-secondary border border-bg-tertiary shadow-[0_16px_64px_rgba(0,0,0,0.5)]',
              'max-h-[85vh] overflow-y-auto',
              'duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]',
              'outline-none focus:outline-none'
            )}
          >
            <Dialog.Title className="sr-only">
              Delete Folder Confirmation
            </Dialog.Title>

            {/* Icon */}
            <div className={cn(
              'w-12 h-12 rounded-xl mb-4',
              'bg-error/20 flex items-center justify-center'
            )}>
              <span className="text-2xl">{folder.emoji || '📁'}</span>
            </div>

            {/* Title */}
            <h2 className="text-lg font-semibold text-text-primary mb-2">
              Delete &quot;{folder.name}&quot;?
            </h2>

            {/* Description */}
            <p className="text-sm text-text-secondary mb-6">
              Conversations in this folder will be moved back to &quot;All&quot;.
              This action cannot be undone.
            </p>

            {/* Actions */}
            <div className="flex gap-3">
              <button
                onClick={onClose}
                disabled={isLoading}
                className={cn(
                  'flex-1 px-4 py-2.5 rounded-xl',
                  'text-sm font-medium text-text-secondary',
                  'bg-bg-tertiary hover:bg-bg-quaternary',
                  'transition-colors duration-150',
                  'disabled:opacity-50 disabled:cursor-not-allowed'
                )}
              >
                Cancel
              </button>
              <button
                onClick={onConfirm}
                disabled={isLoading}
                className={cn(
                  'flex-1 flex items-center justify-center gap-2',
                  'px-4 py-2.5 rounded-xl',
                  'text-sm font-medium text-white',
                  'bg-error hover:bg-error/90',
                  'transition-colors duration-150',
                  'disabled:opacity-50 disabled:cursor-not-allowed'
                )}
              >
                {isLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : null}
                <span>Delete Folder</span>
              </button>
            </div>
          </Dialog.Content>
        </div>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
