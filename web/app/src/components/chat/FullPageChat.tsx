'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import Image from 'next/image';
import { Send, Sparkles, Trash2, Brain, Paperclip, X } from 'lucide-react';
import { useChat } from '@/hooks/useChat';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { FilePreview, ALLOWED_EXTENSIONS, MAX_FILES } from './FilePreview';
import { InlineVoiceRecorder } from './VoiceRecorder';
import { AppSelector } from './AppSelector';
import { uploadChatFiles } from '@/lib/api';
import type { MessageFile } from '@/types/conversation';
import { cn } from '@/lib/utils';
import { PageHeader } from '@/components/layout/PageHeader';

// Quick prompts for the chat
const quickPrompts = [
  'What did I talk about today?',
  'Show my pending tasks',
  'What should I remember?',
  'Summarize my recent conversations',
];

// Format timestamp for display (e.g., "12:32 AM")
function formatMessageTime(isoDate: string): string {
  return new Date(isoDate).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

interface FilePreviewItem {
  file: File;
  preview?: string;
  uploading?: boolean;
  uploadedId?: string;
}

export function FullPageChat() {
  // App selection state
  const [selectedAppId, setSelectedAppId] = useState<string | null>(null);

  const {
    messages,
    isLoading,
    isStreaming,
    streamingText,
    currentThinking,
    error,
    sendMessage,
    clearHistory,
    loadHistory,
  } = useChat({ appId: selectedAppId || undefined });

  const [input, setInput] = useState('');
  const [showClearDialog, setShowClearDialog] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<FilePreviewItem[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load history on mount and when app changes
  useEffect(() => {
    loadHistory();
  }, [loadHistory, selectedAppId]);

  // Scroll to bottom when messages change or streaming text updates
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingText]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Auto-resize textarea
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  // Handle app selection change
  const handleAppChange = useCallback((appId: string | null) => {
    setSelectedAppId(appId);
    // Clear messages when switching apps - they'll reload via useEffect
  }, []);

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
      })
    );

    setSelectedFiles((prev) => [...prev, ...newItems]);

    // Upload files
    setIsUploading(true);
    try {
      const uploadedFiles = await uploadChatFiles(
        filesToAdd,
        selectedAppId || undefined
      );

      // Update items with uploaded IDs
      setSelectedFiles((prev) =>
        prev.map((item) => {
          const uploadedFile = uploadedFiles.find(
            (f) => f.name === item.file.name
          );
          if (uploadedFile) {
            return { ...item, uploading: false, uploadedId: uploadedFile.id };
          }
          return item;
        })
      );
    } catch (err) {
      console.error('Failed to upload files:', err);
      // Remove failed uploads
      setSelectedFiles((prev) =>
        prev.filter((item) => !filesToAdd.includes(item.file))
      );
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

  const handleSend = async (text: string = input) => {
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

    await sendMessage(text, fileIds);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleClear = async () => {
    setIsClearing(true);
    try {
      await clearHistory();
      setShowClearDialog(false);
    } finally {
      setIsClearing(false);
    }
  };

  const canSend = (input.trim() || selectedFiles.some((f) => f.uploadedId)) && !isStreaming && !isUploading;

  return (
    <div className="flex flex-col h-full bg-bg-primary">
      {/* Page Header */}
      <PageHeader title="Chat" icon={Sparkles} />

      {/* Toolbar: App Selector + Clear */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-bg-tertiary bg-bg-secondary">
        {/* App Selector */}
        <AppSelector
          selectedAppId={selectedAppId}
          onSelectApp={handleAppChange}
          disabled={isStreaming}
        />
        {messages.length > 0 && (
          <button
            onClick={() => setShowClearDialog(true)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-bg-tertiary transition-colors text-text-secondary hover:text-text-primary"
            title="Clear chat history"
          >
            <Trash2 className="w-4 h-4" />
            <span className="text-sm hidden sm:inline">Clear chat</span>
          </button>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="px-6 py-3 bg-error/10 border-b border-error/20">
          <p className="text-sm text-error">{error}</p>
        </div>
      )}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-4 py-6">
          {messages.length === 0 && !isLoading ? (
            /* Empty state */
            <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
              <div className="w-20 h-20 rounded-full bg-purple-primary/10 flex items-center justify-center mb-6">
                <Sparkles className="w-10 h-10 text-purple-primary" />
              </div>
              <h2 className="text-2xl font-semibold text-text-primary mb-3">
                Hi! I&apos;m Omi
              </h2>
              <p className="text-text-tertiary max-w-md mb-8">
                I can help you explore your conversations, find tasks, recall memories,
                and answer questions about your life captured through Omi.
              </p>

              {/* Quick prompts */}
              <div className="flex flex-wrap justify-center gap-2 max-w-lg">
                {quickPrompts.map((prompt, i) => (
                  <button
                    key={i}
                    onClick={() => handleSend(prompt)}
                    disabled={isStreaming}
                    className={cn(
                      'px-4 py-2 rounded-full text-sm',
                      'bg-bg-tertiary hover:bg-bg-quaternary',
                      'text-text-secondary hover:text-text-primary',
                      'border border-bg-quaternary hover:border-purple-primary/30',
                      'transition-all',
                      'disabled:opacity-50 disabled:cursor-not-allowed'
                    )}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            /* Messages list */
            <div className="space-y-6">
              {messages.map((message) => (
                <motion.div
                  key={message.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2 }}
                  className={cn(
                    'flex',
                    message.sender === 'human' ? 'justify-end' : 'justify-start'
                  )}
                >
                  {message.sender === 'ai' ? (
                    /* AI message with Omi icon */
                    <div className="flex gap-3 max-w-[85%] sm:max-w-[75%]">
                      <div className="flex-shrink-0 w-10 h-10">
                        <Image
                          src="/logo.png"
                          alt="Omi"
                          width={40}
                          height={40}
                          className="rounded-full"
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="rounded-2xl px-5 py-3 bg-bg-secondary border border-bg-tertiary text-text-primary">
                          {/* Show attached files if any */}
                          {message.files && message.files.length > 0 && (
                            <div className="flex flex-wrap gap-2 mb-2">
                              {message.files.map((file) => (
                                <div
                                  key={file.id}
                                  className="text-xs px-2 py-1 rounded bg-bg-tertiary"
                                >
                                  {file.name}
                                </div>
                              ))}
                            </div>
                          )}
                          <p className="text-sm whitespace-pre-wrap leading-relaxed">
                            {message.text}
                          </p>
                        </div>
                        <span className="text-xs text-text-quaternary mt-1 block">
                          {formatMessageTime(message.created_at)}
                        </span>
                      </div>
                    </div>
                  ) : (
                    /* Human message */
                    <div className="max-w-[85%] sm:max-w-[75%]">
                      <div className="rounded-2xl px-5 py-3 bg-purple-primary text-white">
                        {/* Show attached files if any */}
                        {message.files && message.files.length > 0 && (
                          <div className="flex flex-wrap gap-2 mb-2">
                            {message.files.map((file) => (
                              <div
                                key={file.id}
                                className="text-xs px-2 py-1 rounded bg-white/20"
                              >
                                {file.name}
                              </div>
                            ))}
                          </div>
                        )}
                        <p className="text-sm whitespace-pre-wrap leading-relaxed">
                          {message.text}
                        </p>
                      </div>
                      <span className="text-xs text-text-quaternary mt-1 block text-right">
                        {formatMessageTime(message.created_at)}
                      </span>
                    </div>
                  )}
                </motion.div>
              ))}

              {/* Thinking indicator */}
              {currentThinking && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex justify-start"
                >
                  <div className="flex gap-3 max-w-[85%] sm:max-w-[75%]">
                    <div className="flex-shrink-0 w-10 h-10">
                      <Image
                        src="/logo.png"
                        alt="Omi"
                        width={40}
                        height={40}
                        className="rounded-full"
                      />
                    </div>
                    <div className="rounded-2xl px-5 py-3 bg-bg-secondary/50 border border-purple-primary/20">
                      <div className="flex items-center gap-2 text-purple-primary mb-2">
                        <Brain className="w-4 h-4" />
                        <span className="text-sm font-medium">Thinking...</span>
                      </div>
                      <p className="text-xs text-text-quaternary whitespace-pre-wrap line-clamp-4">
                        {currentThinking}
                      </p>
                    </div>
                  </div>
                </motion.div>
              )}

              {/* Streaming text (AI response in progress) */}
              {streamingText && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex justify-start"
                >
                  <div className="flex gap-3 max-w-[85%] sm:max-w-[75%]">
                    <div className="flex-shrink-0 w-10 h-10">
                      <Image
                        src="/logo.png"
                        alt="Omi"
                        width={40}
                        height={40}
                        className="rounded-full"
                      />
                    </div>
                    <div className="rounded-2xl px-5 py-3 bg-bg-secondary border border-bg-tertiary text-text-primary">
                      <p className="text-sm whitespace-pre-wrap leading-relaxed">
                        {streamingText}
                      </p>
                      <span className="inline-block w-2 h-4 bg-purple-primary/50 animate-pulse ml-0.5" />
                    </div>
                  </div>
                </motion.div>
              )}

              {/* Loading indicator (before streaming starts) */}
              {isStreaming && !streamingText && !currentThinking && (
                <div className="flex justify-start">
                  <div className="flex gap-3">
                    <div className="flex-shrink-0 w-10 h-10">
                      <Image
                        src="/logo.png"
                        alt="Omi"
                        width={40}
                        height={40}
                        className="rounded-full"
                      />
                    </div>
                    <div className="bg-bg-secondary border border-bg-tertiary rounded-2xl px-5 py-4">
                      <div className="flex gap-1.5">
                        <div className="w-2 h-2 bg-text-quaternary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                        <div className="w-2 h-2 bg-text-quaternary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                        <div className="w-2 h-2 bg-text-quaternary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}

          {/* Loading state when fetching history */}
          {isLoading && messages.length === 0 && (
            <div className="flex justify-center py-12">
              <div className="flex gap-1.5">
                <div className="w-2.5 h-2.5 bg-text-quaternary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-2.5 h-2.5 bg-text-quaternary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-2.5 h-2.5 bg-text-quaternary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Input area */}
      <div className="border-t border-bg-tertiary bg-bg-secondary">
        {/* File preview bar */}
        {selectedFiles.length > 0 && (
          <FilePreview
            files={selectedFiles}
            onRemove={handleRemoveFile}
            disabled={isStreaming}
          />
        )}

        <div className="max-w-5xl mx-auto px-4 py-4">
          <div className="flex items-center gap-2">
            {/* File attach button */}
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isStreaming || selectedFiles.length >= MAX_FILES}
              className={cn(
                'p-2 rounded-lg flex-shrink-0',
                'text-text-tertiary hover:text-purple-primary hover:bg-bg-tertiary',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'transition-colors'
              )}
              title={selectedFiles.length >= MAX_FILES ? `Max ${MAX_FILES} files` : 'Attach file'}
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
              placeholder="Ask anything..."
              disabled={isStreaming}
              rows={1}
              className={cn(
                'flex-1 px-4 py-3 rounded-xl resize-none',
                'bg-bg-tertiary border border-bg-quaternary',
                'text-text-primary placeholder:text-text-quaternary',
                'focus:outline-none focus:ring-2 focus:ring-purple-primary/50 focus:border-purple-primary/50',
                'transition-all',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'h-[48px] max-h-[200px]'
              )}
            />

            {/* Inline voice recorder - always visible */}
            <InlineVoiceRecorder
              onTranscript={handleVoiceTranscript}
              disabled={isStreaming}
            />

            {/* Send button */}
            <button
              onClick={() => handleSend()}
              disabled={!canSend}
              className={cn(
                'w-[48px] h-[48px] rounded-xl flex-shrink-0',
                'flex items-center justify-center',
                'bg-purple-primary hover:bg-purple-secondary',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'transition-colors'
              )}
              aria-label="Send message"
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
          <p className="text-xs text-text-quaternary mt-2 text-center">
            Press Enter to send, Shift+Enter for new line
          </p>
        </div>
      </div>

      {/* Clear chat confirmation dialog */}
      <ConfirmDialog
        open={showClearDialog}
        onOpenChange={setShowClearDialog}
        title="Clear chat history?"
        description="This will permanently delete all messages in this conversation. This action cannot be undone."
        confirmLabel="Clear history"
        cancelLabel="Cancel"
        variant="danger"
        onConfirm={handleClear}
        isLoading={isClearing}
      />
    </div>
  );
}
