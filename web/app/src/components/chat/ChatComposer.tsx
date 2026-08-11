'use client';

import { useRef, useState, useEffect, useImperativeHandle } from 'react';
import { ArrowUp, Paperclip } from 'lucide-react';
import { FilePreview, ALLOWED_EXTENSIONS, MAX_FILES } from './FilePreview';
import { InlineVoiceRecorder } from './VoiceRecorder';
import { OmiPulseMark } from '@/components/ui/OmiPulseMark';
import { uploadChatFiles } from '@/lib/api';
import type { MessageFile } from '@/types/conversation';
import { cn } from '@/lib/utils';

/**
 * The ask bar: one pill that carries the text and every control that acts on
 * it.
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
  uploadedFile?: MessageFile;
}

export interface ChatComposerHandle {
  focus: () => void;
}

interface ChatComposerProps {
  /** Resolves once the send completes, so the caller can react to the first message. */
  onSend: (text: string, files: MessageFile[]) => Promise<void>;
  isStreaming: boolean;
  disabled?: boolean;
  appId?: string;
  placeholder?: string;
  /**
   * Capture controls live in the pill so that starting a recording and asking
   * about it are the same gesture in the same place. Omitted where there is no
   * capture to start.
   *
   * It wears a waveform rather than a microphone, and sits next to send rather
   * than beside the attachment. Dictation is also a microphone, and two mics a
   * thumb apart meaning different things read as one control drawn twice: this
   * one opens a live conversation, the other one types for you.
   */
  recording?: {
    isActive: boolean;
    /** Input level, 0..1, so the button itself meters what it is hearing. */
    level: number;
    onStart: () => void;
    onStop: () => void;
    disabled?: boolean;
  };
  ref?: React.Ref<ChatComposerHandle>;
}

export function ChatComposer({
  onSend,
  isStreaming,
  disabled = false,
  appId,
  placeholder = 'Ask anything...',
  recording,
  ref,
}: ChatComposerProps) {
  const [input, setInput] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<FilePreviewItem[]>([]);
  const [pendingUploadCount, setPendingUploadCount] = useState(0);

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingUploadCountRef = useRef(0);
  const isUploading = pendingUploadCount > 0;

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
    const newItems: FilePreviewItem[] = filesToAdd.map((file) => {
      let preview: string | undefined;
      if (file.type.startsWith('image/')) {
        preview = URL.createObjectURL(file);
      }
      return { file, preview, uploading: true };
    });

    setSelectedFiles((prev) => [...prev, ...newItems]);

    // Upload files
    pendingUploadCountRef.current += 1;
    setPendingUploadCount((current) => current + 1);
    try {
      const uploadedFiles = await uploadChatFiles(filesToAdd, appId);

      // Update items with uploaded IDs
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
      // Remove failed uploads
      setSelectedFiles((prev) => prev.filter((item) => !filesToAdd.includes(item.file)));
    } finally {
      pendingUploadCountRef.current = Math.max(0, pendingUploadCountRef.current - 1);
      setPendingUploadCount((current) => Math.max(0, current - 1));
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
    if (
      (!text.trim() && !selectedFiles.some((item) => item.uploadedId)) ||
      disabled ||
      isStreaming ||
      pendingUploadCountRef.current > 0
    )
      return;

    // Get file IDs from uploaded files
    const uploadedFiles = selectedFiles.flatMap((item) =>
      item.uploadedFile ? [item.uploadedFile] : [],
    );

    setInput('');
    setSelectedFiles([]);
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }

    await onSend(text, uploadedFiles);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  const canSend =
    (input.trim() || selectedFiles.some((f) => f.uploadedFile)) &&
    !disabled &&
    !isStreaming &&
    !isUploading;

  const iconButton = cn(
    'flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full sm:h-9 sm:w-9',
    'text-text-tertiary transition-colors hover:bg-white/[0.08] hover:text-text-primary',
    'disabled:cursor-not-allowed disabled:opacity-40',
  );

  return (
    <div
      className={cn(
        'rounded-[28px] border border-stroke bg-bg-tertiary',
        'transition-colors focus-within:border-white/25',
      )}
    >
      {/* File preview bar */}
      {selectedFiles.length > 0 && (
        <div className="px-3 pt-3">
          <FilePreview
            files={selectedFiles}
            onRemove={handleRemoveFile}
            disabled={disabled || isStreaming}
          />
        </div>
      )}

      {/* The text sits on its own line above the controls so a long draft grows
          the pill downward instead of squeezing the buttons. */}
      <textarea
        ref={inputRef}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled || isStreaming}
        rows={1}
        className={cn(
          'no-scrollbar w-full resize-none bg-transparent px-5 pt-4',
          'text-text-primary placeholder:text-text-quaternary',
          'focus:outline-none',
          'disabled:cursor-not-allowed disabled:opacity-50',
          'max-h-[200px]',
        )}
      />

      <div className="flex items-center gap-1 px-2.5 pb-2.5 pt-1">
        {/* File attach button */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={
            disabled || isStreaming || isUploading || selectedFiles.length >= MAX_FILES
          }
          className={iconButton}
          title={
            selectedFiles.length >= MAX_FILES ? `Max ${MAX_FILES} files` : 'Attach file'
          }
          aria-label="Attach file"
        >
          <Paperclip className="h-[18px] w-[18px]" />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ALLOWED_EXTENSIONS}
          onChange={handleFileSelect}
          className="hidden"
        />

        {/* Dictation: types for you. */}
        <InlineVoiceRecorder
          onTranscript={handleVoiceTranscript}
          disabled={disabled || isStreaming}
        />

        <div className="flex-1" />

        {/* Live conversation: sits beside send because it is the other way to
            put something into the thread. Once it is running the mark takes
            over the button and meters the room. */}
        {recording && (
          <button
            onClick={recording.isActive ? recording.onStop : recording.onStart}
            disabled={disabled || recording.disabled}
            className={cn(
              iconButton,
              recording.isActive &&
                'bg-white/[0.10] text-text-primary hover:bg-white/[0.16]',
            )}
            title={recording.isActive ? 'Stop conversation' : 'Start a live conversation'}
            aria-label={
              recording.isActive ? 'Stop conversation' : 'Start a live conversation'
            }
          >
            <OmiPulseMark
              level={recording.isActive ? Math.min(0.3, Math.max(0, recording.level)) : 0}
              size={20}
              active={recording.isActive}
              testId="composer-live-mark"
            />
          </button>
        )}

        {/* Send button */}
        <button
          onClick={() => void handleSend()}
          disabled={!canSend}
          className={cn(
            'flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full sm:h-9 sm:w-9',
            'bg-text-primary text-bg-primary transition-opacity hover:opacity-90',
            'disabled:cursor-not-allowed disabled:opacity-25',
          )}
          aria-label="Send message"
        >
          <ArrowUp className="h-[18px] w-[18px]" strokeWidth={2.5} />
        </button>
      </div>
    </div>
  );
}
