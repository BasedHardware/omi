'use client';

import { X, FileText, Image as ImageIcon, Loader2 } from 'lucide-react';
import Image from 'next/image';
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
    <div className="flex gap-2 px-4 py-3 overflow-x-auto">
      {files.map((item, index) => (
        <div
          key={index}
          className={cn(
            'relative flex-shrink-0 w-16 h-16 rounded-lg overflow-hidden',
            'bg-bg-tertiary border border-bg-quaternary',
            'group'
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
            <div className="w-full h-full flex flex-col items-center justify-center p-1">
              <FileText className="w-6 h-6 text-text-tertiary mb-1" />
              <span className="text-[10px] text-text-quaternary truncate max-w-full px-1">
                {item.file.name.split('.').pop()?.toUpperCase()}
              </span>
            </div>
          )}

          {/* Upload loading overlay */}
          {item.uploading && (
            <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
              <Loader2 className="w-5 h-5 text-white animate-spin" />
            </div>
          )}

          {/* Remove button */}
          {!disabled && !item.uploading && (
            <button
              onClick={() => onRemove(index)}
              className={cn(
                'absolute -top-1 -right-1 w-5 h-5 rounded-full',
                'bg-bg-primary border border-bg-tertiary',
                'flex items-center justify-center',
                'opacity-0 group-hover:opacity-100 transition-opacity',
                'hover:bg-error hover:border-error hover:text-white'
              )}
            >
              <X className="w-3 h-3" />
            </button>
          )}

          {/* Uploaded indicator */}
          {item.uploadedId && !item.uploading && (
            <div className="absolute bottom-0 left-0 right-0 bg-green-500/80 py-0.5">
              <span className="text-[8px] text-white text-center block">Ready</span>
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

export const ALLOWED_EXTENSIONS = '.jpg,.jpeg,.png,.gif,.webp,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md';

export const MAX_FILES = 4;
