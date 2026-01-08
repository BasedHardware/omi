'use client';

import { useRef, useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Send, Sparkles, Trash2, Brain, Paperclip, ArrowLeft } from 'lucide-react';
import { useChat as useChatContext } from './ChatContext';
import { useChat } from '@/hooks/useChat';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { FilePreview, ALLOWED_EXTENSIONS, MAX_FILES } from './FilePreview';
import { InlineVoiceRecorder } from './VoiceRecorder';
import { uploadChatFiles, getChatApps } from '@/lib/api';
import type { App } from '@/lib/api';
import { cn } from '@/lib/utils';
import { MixpanelManager } from '@/lib/analytics/mixpanel';

interface FilePreviewItem {
  file: File;
  preview?: string;
  uploading?: boolean;
  uploadedId?: string;
}

// Quick prompts based on context
function getQuickPrompts(contextType: string | undefined): string[] {
  switch (contextType) {
    case 'conversation':
      return [
        'Summarize this conversation',
        'What action items came from this?',
        'What were the key decisions?',
      ];
    case 'task':
      return [
        'Help me complete this task',
        'Break this down into steps',
        'Set a reminder for this',
      ];
    case 'memory':
      return [
        'Tell me more about this',
        'When did I mention this?',
        'Related memories',
      ];
    default:
      return [
        'What did I talk about today?',
        'Show my pending tasks',
        'What should I remember?',
      ];
  }
}

export function ChatPanel() {
  const { isOpen, closeChat, currentContext, selectedAppId, clearAppContext } = useChatContext();
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
  const [selectedApp, setSelectedApp] = useState<App | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch app info when selectedAppId changes
  useEffect(() => {
    if (selectedAppId) {
      getChatApps().then((apps) => {
        const app = apps.find((a) => a.id === selectedAppId);
        setSelectedApp(app || null);
      }).catch(() => setSelectedApp(null));
    } else {
      setSelectedApp(null);
    }
  }, [selectedAppId]);

  // Load history when panel opens
  useEffect(() => {
    if (isOpen) {
      loadHistory();
    }
  }, [isOpen, loadHistory]);

  // Scroll to bottom when messages change or streaming text updates
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingText]);

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 300);
    }
  }, [isOpen]);

  const quickPrompts = getQuickPrompts(currentContext?.type);

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
      const uploadedFiles = await uploadChatFiles(filesToAdd);

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

    MixpanelManager.track('Chat Message Sent', {
      message_length: text.length,
      has_files: fileIds.length > 0,
      file_count: fileIds.length,
    });

    setInput('');
    setSelectedFiles([]);
    await sendMessage(text, fileIds, currentContext);
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
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Mobile backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 bg-black/30 z-40 sm:hidden"
            onClick={closeChat}
          />

          {/* Panel - push/slide animation */}
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: 400 }}
            exit={{ width: 0 }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className={cn(
              'h-full flex-shrink-0 overflow-hidden',
              'bg-bg-secondary border-l border-bg-tertiary',
              'max-sm:fixed max-sm:inset-0 max-sm:z-50 max-sm:w-full'
            )}
          >
            <div className={cn(
              'w-[400px] h-full flex flex-col',
              'max-sm:w-full'
            )}>
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-bg-tertiary">
              <div className="flex items-center gap-3">
                {/* Back button when in app-specific chat */}
                {selectedAppId && (
                  <button
                    onClick={clearAppContext}
                    className="p-1.5 -ml-1 rounded-lg hover:bg-bg-tertiary transition-colors"
                    aria-label="Back to Omi chat"
                    title="Back to Omi"
                  >
                    <ArrowLeft className="w-4 h-4 text-text-tertiary" />
                  </button>
                )}
                <div className="w-8 h-8 rounded-full bg-purple-primary/20 flex items-center justify-center">
                  <Sparkles className="w-4 h-4 text-purple-primary" />
                </div>
                <div>
                  <h2 className="font-semibold text-text-primary">
                    {selectedApp ? `Chat with ${selectedApp.name}` : 'Chat with Omi'}
                  </h2>
                  {currentContext?.title && !selectedAppId && (
                    <p className="text-xs text-text-tertiary truncate max-w-[250px]">
                      Context: {currentContext.title}
                    </p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-1">
                {messages.length > 0 && (
                  <button
                    onClick={() => setShowClearDialog(true)}
                    className="p-2 rounded-lg hover:bg-bg-tertiary transition-colors"
                    aria-label="Clear chat"
                    title="Clear chat history"
                  >
                    <Trash2 className="w-4 h-4 text-text-quaternary hover:text-text-secondary" />
                  </button>
                )}
                <button
                  onClick={closeChat}
                  className="p-2 rounded-lg hover:bg-bg-tertiary transition-colors"
                  aria-label="Close chat"
                >
                  <X className="w-5 h-5 text-text-secondary" />
                </button>
              </div>
            </div>

            {/* Error banner */}
            {error && (
              <div className="px-4 py-2 bg-error/10 border-b border-error/20">
                <p className="text-sm text-error">{error}</p>
              </div>
            )}

            {/* Quick prompts (shown when no messages) */}
            {messages.length === 0 && !isLoading && (
              <div className="p-4 border-b border-bg-tertiary">
                <p className="text-xs text-text-quaternary mb-2">Quick prompts:</p>
                <div className="flex flex-wrap gap-2">
                  {quickPrompts.map((prompt, i) => (
                    <button
                      key={i}
                      onClick={() => handleSend(prompt)}
                      disabled={isStreaming}
                      className={cn(
                        'px-3 py-1.5 rounded-full text-sm',
                        'bg-bg-tertiary hover:bg-bg-quaternary',
                        'text-text-secondary hover:text-text-primary',
                        'transition-colors',
                        'disabled:opacity-50 disabled:cursor-not-allowed'
                      )}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.length === 0 && !isLoading ? (
                <div className="flex flex-col items-center justify-center h-full text-center">
                  <div className="w-16 h-16 rounded-full bg-purple-primary/10 flex items-center justify-center mb-4">
                    <Sparkles className="w-8 h-8 text-purple-primary" />
                  </div>
                  <h3 className="text-lg font-medium text-text-primary mb-2">
                    Hi! I&apos;m Omi
                  </h3>
                  <p className="text-text-tertiary max-w-[280px]">
                    Ask me anything about your conversations, tasks, or memories.
                  </p>
                </div>
              ) : (
                <>
                  {/* Rendered messages */}
                  {messages.map((message) => (
                    <div
                      key={message.id}
                      className={cn(
                        'flex',
                        message.sender === 'human' ? 'justify-end' : 'justify-start'
                      )}
                    >
                      <div
                        className={cn(
                          'max-w-[80%] rounded-2xl px-4 py-2.5',
                          message.sender === 'human'
                            ? 'bg-purple-primary text-white'
                            : 'bg-bg-tertiary text-text-primary'
                        )}
                      >
                        <p className="text-sm whitespace-pre-wrap">{message.text}</p>
                      </div>
                    </div>
                  ))}

                  {/* Thinking indicator */}
                  {currentThinking && (
                    <div className="flex justify-start">
                      <div className="max-w-[80%] rounded-2xl px-4 py-2.5 bg-bg-tertiary/50 border border-purple-primary/20">
                        <div className="flex items-center gap-2 text-purple-primary mb-1">
                          <Brain className="w-3 h-3" />
                          <span className="text-xs font-medium">Thinking...</span>
                        </div>
                        <p className="text-xs text-text-quaternary whitespace-pre-wrap line-clamp-3">
                          {currentThinking}
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Streaming text (AI response in progress) */}
                  {streamingText && (
                    <div className="flex justify-start">
                      <div className="max-w-[80%] rounded-2xl px-4 py-2.5 bg-bg-tertiary text-text-primary">
                        <p className="text-sm whitespace-pre-wrap">{streamingText}</p>
                        <span className="inline-block w-2 h-4 bg-purple-primary/50 animate-pulse ml-0.5" />
                      </div>
                    </div>
                  )}

                  {/* Loading indicator (before streaming starts) */}
                  {isStreaming && !streamingText && !currentThinking && (
                    <div className="flex justify-start">
                      <div className="bg-bg-tertiary rounded-2xl px-4 py-3">
                        <div className="flex gap-1">
                          <div className="w-2 h-2 bg-text-quaternary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                          <div className="w-2 h-2 bg-text-quaternary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                          <div className="w-2 h-2 bg-text-quaternary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )}

              {/* Loading state when fetching history */}
              {isLoading && messages.length === 0 && (
                <div className="flex justify-center py-8">
                  <div className="flex gap-1">
                    <div className="w-2 h-2 bg-text-quaternary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <div className="w-2 h-2 bg-text-quaternary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <div className="w-2 h-2 bg-text-quaternary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Input area */}
            <div className="border-t border-bg-tertiary">
              {/* File preview bar */}
              {selectedFiles.length > 0 && (
                <FilePreview
                  files={selectedFiles}
                  onRemove={handleRemoveFile}
                  disabled={isStreaming}
                />
              )}

              <div className="p-4">
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
                  <input
                    ref={inputRef}
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask anything..."
                    disabled={isStreaming}
                    className={cn(
                      'flex-1 px-4 py-3 rounded-xl',
                      'bg-bg-tertiary border border-bg-quaternary',
                      'text-text-primary placeholder:text-text-quaternary',
                      'focus:outline-none focus:ring-2 focus:ring-purple-primary/50',
                      'transition-shadow',
                      'disabled:opacity-50 disabled:cursor-not-allowed'
                    )}
                  />

                  {/* Inline voice recorder */}
                  <InlineVoiceRecorder
                    onTranscript={handleVoiceTranscript}
                    disabled={isStreaming}
                  />

                  {/* Send button */}
                  <button
                    onClick={() => handleSend()}
                    disabled={!canSend}
                    className={cn(
                      'p-3 rounded-xl flex-shrink-0',
                      'bg-purple-primary hover:bg-purple-secondary',
                      'disabled:opacity-50 disabled:cursor-not-allowed',
                      'transition-colors'
                    )}
                    aria-label="Send message"
                  >
                    <Send className="w-5 h-5 text-white" />
                  </button>
                </div>
              </div>
            </div>
            </div>
          </motion.div>

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
        </>
      )}
    </AnimatePresence>
  );
}
