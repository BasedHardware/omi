'use client';

import { useRef, useState } from 'react';
import { uploadChatFiles } from '@/features/chat/api';
import { MAX_FILES, type FilePreviewItem } from './FilePreview';
import type { MessageFile } from '@/types/conversation';

/**
 * Shared draft-attachment state for Home's pill composer and the overlay panel.
 * Upload lives here so the two UIs do not fork the MAX_FILES / preview / rollback path.
 */
export function useChatAttachments(appId?: string) {
  const [selectedFiles, setSelectedFiles] = useState<FilePreviewItem[]>([]);
  const [pendingUploadCount, setPendingUploadCount] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingUploadCountRef = useRef(0);
  const isUploading = pendingUploadCount > 0;

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;

    const availableSlots = MAX_FILES - selectedFiles.length;
    const filesToAdd = files.slice(0, availableSlots);

    const newItems: FilePreviewItem[] = filesToAdd.map((file) => {
      let preview: string | undefined;
      if (file.type.startsWith('image/')) {
        preview = URL.createObjectURL(file);
      }
      return { file, preview, uploading: true };
    });

    setSelectedFiles((prev) => [...prev, ...newItems]);

    pendingUploadCountRef.current += 1;
    setPendingUploadCount((current) => current + 1);
    try {
      const uploadedFiles = await uploadChatFiles(filesToAdd, appId);

      setSelectedFiles((prev) =>
        prev.map((item) => {
          const fileIndex = filesToAdd.indexOf(item.file);
          const uploadedFile = fileIndex >= 0 ? uploadedFiles[fileIndex] : undefined;
          if (uploadedFile) {
            return {
              ...item,
              uploading: false,
              uploadedId: uploadedFile.id,
              uploadedFile,
            };
          }
          return item;
        }),
      );
    } catch (err) {
      console.error('Failed to upload files:', err);
      setSelectedFiles((prev) => prev.filter((item) => !filesToAdd.includes(item.file)));
    } finally {
      pendingUploadCountRef.current = Math.max(0, pendingUploadCountRef.current - 1);
      setPendingUploadCount((current) => Math.max(0, current - 1));
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleRemoveFile = (index: number) => {
    setSelectedFiles((prev) => {
      const item = prev[index];
      if (item?.preview) {
        URL.revokeObjectURL(item.preview);
      }
      return prev.filter((_, i) => i !== index);
    });
  };

  const takeReadyFiles = (): MessageFile[] =>
    selectedFiles.flatMap((item) => (item.uploadedFile ? [item.uploadedFile] : []));

  const clear = () => {
    setSelectedFiles((prev) => {
      for (const item of prev) {
        if (item.preview) URL.revokeObjectURL(item.preview);
      }
      return [];
    });
  };

  return {
    selectedFiles,
    isUploading,
    fileInputRef,
    pendingUploadCountRef,
    handleFileSelect,
    handleRemoveFile,
    takeReadyFiles,
    clear,
    hasReadyUpload: selectedFiles.some((item) => item.uploadedId),
    atFileLimit: selectedFiles.length >= MAX_FILES,
  };
}
