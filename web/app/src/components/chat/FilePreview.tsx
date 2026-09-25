'use client';

import { X, FileText, Image as ImageIcon, Loader2 } from 'lucide-react';
import Image from '@tschk/moonshine-next/image';
import { cn } from '@/lib/utils';

interface FilePreviewItem {
  file: File;
  preview?: string;
  uploading?: boolean;
  uploadedId?: string;
}

interface FilePreviewProps {
  files: FilePreviewItem[];
  onRemove: (index: number) => void;
  disabled?: boolean;
}

function isImageFile(file: File): boolean {
  return file.type.startsWith('image/');
}

export function FilePreview({ files, onRemove, disabled }: FilePreviewProps) {
  if (files.length === 0) return null;

  return (
    <div className="flex gap-2 overflow-x-auto px-4 py-3">
      {files.map((item, index) => (
        <div
          key={index}
          className={cn(
            'relative h-16 w-16 flex-shrink-0 overflow-hidden rounded-lg',
            'border border-bg-quaternary bg-bg-tertiary',
            'group',
          )}
        >
          {/* Preview content */}
          {isImageFile(item.file) && item.preview ? (
            <Image
              src={item.preview}
              alt={item.file.name}
              fill
              className="object-cover"
            />
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center p-1">
              <FileText className="mb-1 h-6 w-6 text-text-tertiary" />
              <span className="max-w-full truncate px-1 text-[10px] text-text-quaternary">
                {item.file.name.split('.').pop()?.toUpperCase()}
              </span>
            </div>
          )}

          {/* Upload loading overlay */}
          {item.uploading && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/50">
              <Loader2 className="h-5 w-5 animate-spin text-white" />
            </div>
          )}

          {/* Remove button */}
          {!disabled && !item.uploading && (
            <button
              onClick={() => onRemove(index)}
              className={cn(
                'absolute -right-1 -top-1 h-5 w-5 rounded-full',
                'border border-bg-tertiary bg-bg-primary',
                'flex items-center justify-center',
                'opacity-0 transition-opacity group-hover:opacity-100',
                'hover:border-error hover:bg-error hover:text-white',
              )}
            >
              <X className="h-3 w-3" />
            </button>
          )}

          {/* Uploaded indicator */}
          {item.uploadedId && !item.uploading && (
            <div className="absolute bottom-0 left-0 right-0 bg-green-500/80 py-0.5">
              <span className="block text-center text-[8px] text-white">Ready</span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// Allowed file types
export const ALLOWED_FILE_TYPES = {
  images: ['image/jpeg', 'image/png', 'image/gif', 'image/webp'],
  documents: [
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'text/plain',
    'text/markdown',
  ],
};

export const ALLOWED_EXTENSIONS =
  '.jpg,.jpeg,.png,.gif,.webp,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md';

export const MAX_FILES = 4;
