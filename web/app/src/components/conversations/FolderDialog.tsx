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
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />

        {/* Dialog Container - Centered with flexbox */}
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 text-center">
          <Dialog.Content
            className={cn(
              'w-full max-w-md rounded-2xl p-6 text-left align-middle',
              'border border-bg-tertiary bg-bg-secondary shadow-[0_16px_64px_rgba(0,0,0,0.5)]',
              'max-h-[85vh] overflow-y-auto',
              'duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]',
              'outline-none focus:outline-none', // Remove default browser focus ring
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
                'flex items-center justify-center',
              )}
              style={{ backgroundColor: `${color}20` }}
            >
              {isEditing ? (
                <Pencil className="h-6 w-6" style={{ color }} />
              ) : (
                <FolderPlus className="h-6 w-6" style={{ color }} />
              )}
            </div>

            {/* Visible Title */}
            <h2 className="mb-4 text-lg font-semibold text-text-primary">
              {isEditing ? 'Edit Folder' : 'Create Folder'}
            </h2>

            <form onSubmit={handleSubmit}>
              {/* Folder name input */}
              <div className="mb-4">
                <label className="mb-2 block text-sm font-medium text-text-secondary">
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
                      'flex-1 rounded-lg px-3 py-2',
                      'border border-bg-quaternary bg-bg-tertiary',
                      'text-text-primary placeholder:text-text-quaternary',
                      'focus:outline-none focus:ring-2 focus:ring-white/25',
                      'disabled:opacity-50',
                    )}
                    autoFocus
                  />
                </div>
              </div>

              {/* Description input */}
              <div className="mb-4">
                <label className="mb-2 block text-sm font-medium text-text-secondary">
                  Description{' '}
                  <span className="font-normal text-text-quaternary">(optional)</span>
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="E.g., Work meetings and project discussions"
                  disabled={isLoading}
                  maxLength={500}
                  rows={2}
                  className={cn(
                    'w-full resize-none rounded-lg px-3 py-2',
                    'border border-bg-quaternary bg-bg-tertiary',
                    'text-text-primary placeholder:text-text-quaternary',
                    'text-sm',
                    'focus:outline-none focus:ring-2 focus:ring-white/25',
                    'disabled:opacity-50',
                  )}
                />
                <p className="mt-1 text-xs text-text-quaternary">
                  Helps AI auto-categorize conversations into this folder
                </p>
              </div>

              {/* Emoji picker */}
              <div className="mb-4">
                <label className="mb-2 block text-sm font-medium text-text-secondary">
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
                        'h-10 w-10 rounded-lg text-xl',
                        'flex items-center justify-center',
                        'transition-all duration-150',
                        emoji === e
                          ? 'bg-white/[0.14] ring-2 ring-white/25'
                          : 'bg-bg-tertiary hover:bg-bg-quaternary',
                        'disabled:cursor-not-allowed disabled:opacity-50',
                      )}
                    >
                      {e}
                    </button>
                  ))}
                </div>
              </div>

              {/* Color picker */}
              <div className="mb-6">
                <label className="mb-2 block text-sm font-medium text-text-secondary">
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
                        'h-8 w-8 rounded-full',
                        'transition-all duration-150',
                        color === c.value
                          ? 'ring-2 ring-offset-2 ring-offset-bg-secondary'
                          : 'hover:scale-110',
                        'disabled:cursor-not-allowed disabled:opacity-50',
                      )}
                      style={
                        {
                          backgroundColor: c.value,
                          '--tw-ring-color': c.value,
                        } as React.CSSProperties
                      }
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
                    'flex-1 rounded-xl px-4 py-2.5',
                    'text-sm font-medium text-text-secondary',
                    'bg-bg-tertiary hover:bg-bg-quaternary',
                    'transition-colors duration-150',
                    'disabled:cursor-not-allowed disabled:opacity-50',
                  )}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!isValid || isLoading}
                  className={cn(
                    'flex flex-1 items-center justify-center gap-2',
                    'rounded-xl px-4 py-2.5',
                    'text-sm font-medium text-white',
                    'transition-colors duration-150',
                    'disabled:cursor-not-allowed disabled:opacity-50',
                  )}
                  style={{ backgroundColor: isValid ? color : undefined }}
                >
                  {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
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
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />

        {/* Dialog Container */}
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 text-center">
          <Dialog.Content
            className={cn(
              'w-full max-w-sm rounded-2xl p-6 text-left align-middle',
              'border border-bg-tertiary bg-bg-secondary shadow-[0_16px_64px_rgba(0,0,0,0.5)]',
              'max-h-[85vh] overflow-y-auto',
              'duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]',
              'outline-none focus:outline-none',
            )}
          >
            <Dialog.Title className="sr-only">Delete Folder Confirmation</Dialog.Title>

            {/* Icon */}
            <div
              className={cn(
                'mb-4 h-12 w-12 rounded-xl',
                'flex items-center justify-center bg-error/20',
              )}
            >
              <span className="text-2xl">{folder.emoji || '📁'}</span>
            </div>

            {/* Title */}
            <h2 className="mb-2 text-lg font-semibold text-text-primary">
              Delete &quot;{folder.name}&quot;?
            </h2>

            {/* Description */}
            <p className="mb-6 text-sm text-text-secondary">
              Conversations in this folder will be moved back to &quot;All&quot;. This
              action cannot be undone.
            </p>

            {/* Actions */}
            <div className="flex gap-3">
              <button
                onClick={onClose}
                disabled={isLoading}
                className={cn(
                  'flex-1 rounded-xl px-4 py-2.5',
                  'text-sm font-medium text-text-secondary',
                  'bg-bg-tertiary hover:bg-bg-quaternary',
                  'transition-colors duration-150',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                )}
              >
                Cancel
              </button>
              <button
                onClick={onConfirm}
                disabled={isLoading}
                className={cn(
                  'flex flex-1 items-center justify-center gap-2',
                  'rounded-xl px-4 py-2.5',
                  'text-sm font-medium text-white',
                  'bg-error hover:bg-error/90',
                  'transition-colors duration-150',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                )}
              >
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                <span>Delete Folder</span>
              </button>
            </div>
          </Dialog.Content>
        </div>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
