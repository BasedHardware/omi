'use client';

import { useRef, useState, useEffect, useImperativeHandle } from 'react';
import { Send, Paperclip } from 'lucide-react';
import { FilePreview, ALLOWED_EXTENSIONS, MAX_FILES } from './FilePreview';
import { InlineVoiceRecorder } from './VoiceRecorder';
import { uploadChatFiles } from '@/lib/api';
import { cn } from '@/lib/utils';

/**
 * The ask bar: text, attachments, dictation and send.
 *
 * Desktop keeps one composer for the whole Home stage and moves it between the
 * hub and the transcript rather than giving each mode its own, so this owns the
 * draft and upload state and reports only completed sends upward.
 */

interface FilePreviewItem {
  file: File;
  preview?: string;
  uploading?: boolean;
  uploadedId?: string;
}

export interface ChatComposerHandle {
  focus: () => void;
}

interface ChatComposerProps {
  /** Resolves once the send completes, so the caller can react to the first message. */
  onSend: (text: string, fileIds: string[]) => Promise<void>;
  isStreaming: boolean;
  appId?: string;
  placeholder?: string;
  /** Rendered under the input; the hub omits it to keep the resting state calm. */
  hint?: string;
  ref?: React.Ref<ChatComposerHandle>;
}

export function ChatComposer({
  onSend,
  isStreaming,
  appId,
  placeholder = 'Ask anything...',
  hint,
  ref,
}: ChatComposerProps) {
  const [input, setInput] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<FilePreviewItem[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useImperativeHandle(ref, () => ({ focus: () => inputRef.current?.focus() }), []);

  // Auto-resize textarea
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  // Handle file selection
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;

    // Limit to MAX_FILES
    const availableSlots = MAX_FILES - selectedFiles.length;
    const filesToAdd = files.slice(0, availableSlots);

    // Create preview items
    const newItems: FilePreviewItem[] = await Promise.all(
      filesToAdd.map(async (file) => {
        let preview: string | undefined;
        if (file.type.startsWith('image/')) {
          preview = URL.createObjectURL(file);
        }
        return { file, preview, uploading: true };
      }),
    );

    setSelectedFiles((prev) => [...prev, ...newItems]);

    // Upload files
    setIsUploading(true);
    try {
      const uploadedFiles = await uploadChatFiles(filesToAdd, appId);

      // Update items with uploaded IDs
      setSelectedFiles((prev) =>
        prev.map((item) => {
          const uploadedFile = uploadedFiles.find((f) => f.name === item.file.name);
          if (uploadedFile) {
            return { ...item, uploading: false, uploadedId: uploadedFile.id };
          }
          return item;
        }),
      );
    } catch (err) {
      console.error('Failed to upload files:', err);
      // Remove failed uploads
      setSelectedFiles((prev) => prev.filter((item) => !filesToAdd.includes(item.file)));
    } finally {
      setIsUploading(false);
    }

    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Remove file from selection
  const handleRemoveFile = (index: number) => {
    setSelectedFiles((prev) => {
      const item = prev[index];
      // Revoke object URL if it was an image
      if (item.preview) {
        URL.revokeObjectURL(item.preview);
      }
      return prev.filter((_, i) => i !== index);
    });
  };

  // Handle voice transcript - append to input and focus
  const handleVoiceTranscript = (transcript: string) => {
    setInput((prev) => (prev ? `${prev} ${transcript}` : transcript));
    inputRef.current?.focus();
  };

  const handleSend = async () => {
    const text = input;
    if (!text.trim() || isStreaming) return;

    // Get file IDs from uploaded files
    const fileIds = selectedFiles
      .filter((item) => item.uploadedId)
      .map((item) => item.uploadedId as string);

    setInput('');
    setSelectedFiles([]);
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }

    await onSend(text, fileIds);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  const canSend =
    (input.trim() || selectedFiles.some((f) => f.uploadedId)) &&
    !isStreaming &&
    !isUploading;

  return (
    <div>
      {/* File preview bar */}
      {selectedFiles.length > 0 && (
        <FilePreview
          files={selectedFiles}
          onRemove={handleRemoveFile}
          disabled={isStreaming}
        />
      )}

      <div className="flex items-center gap-2">
        {/* File attach button */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isStreaming || selectedFiles.length >= MAX_FILES}
          className={cn(
            'p-2 rounded-element flex-shrink-0',
            'text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            'transition-colors',
          )}
          title={
            selectedFiles.length >= MAX_FILES ? `Max ${MAX_FILES} files` : 'Attach file'
          }
        >
          <Paperclip className="w-5 h-5" />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ALLOWED_EXTENSIONS}
          onChange={handleFileSelect}
          className="hidden"
        />

        {/* Text input */}
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={isStreaming}
          rows={1}
          className={cn(
            'flex-1 px-4 py-3 rounded-control resize-none',
            'bg-bg-tertiary border border-stroke',
            'text-text-primary placeholder:text-text-quaternary',
            'focus:outline-none focus:ring-2 focus:ring-white/20 focus:border-white/20',
            'transition-all',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            'h-[48px] max-h-[200px]',
          )}
        />

        {/* Inline voice recorder - always visible */}
        <InlineVoiceRecorder
          onTranscript={handleVoiceTranscript}
          disabled={isStreaming}
        />

        {/* Send button */}
        <button
          onClick={() => void handleSend()}
          disabled={!canSend}
          className={cn(
            'w-[48px] h-[48px] rounded-control flex-shrink-0',
            'flex items-center justify-center',
            'bg-text-primary text-bg-primary hover:opacity-90',
            'disabled:opacity-40 disabled:cursor-not-allowed',
            'transition-opacity',
          )}
          aria-label="Send message"
        >
          <Send className="w-5 h-5" />
        </button>
      </div>
      {hint && <p className="text-xs text-text-quaternary mt-2 text-center">{hint}</p>}
    </div>
  );
}
