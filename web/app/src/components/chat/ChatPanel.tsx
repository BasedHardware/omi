'use client';

import { useRef, useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Send, Sparkles, Trash2, Brain } from 'lucide-react';
import { useChat as useChatContext } from './ChatContext';
import { useChat } from '@/hooks/useChat';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { cn } from '@/lib/utils';

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
  const { isOpen, closeChat, currentContext } = useChatContext();
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
  } = useChat();

  const [input, setInput] = useState('');
  const [showClearDialog, setShowClearDialog] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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

  const handleSend = async (text: string = input) => {
    if (!text.trim() || isStreaming) return;
    setInput('');
    await sendMessage(text);
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

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 bg-black/30 z-40 lg:hidden"
            onClick={closeChat}
          />

          {/* Panel */}
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className={cn(
              'fixed top-0 right-0 bottom-0 z-50',
              'w-full sm:w-[400px]',
              'bg-bg-secondary border-l border-bg-tertiary',
              'flex flex-col',
              'shadow-2xl'
            )}
          >
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-bg-tertiary">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-purple-primary/20 flex items-center justify-center">
                  <Sparkles className="w-4 h-4 text-purple-primary" />
                </div>
                <div>
                  <h2 className="font-semibold text-text-primary">Chat with Omi</h2>
                  {currentContext?.title && (
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

            {/* Input */}
            <div className="p-4 border-t border-bg-tertiary">
              <div className="flex items-center gap-2">
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
                <button
                  onClick={() => handleSend()}
                  disabled={!input.trim() || isStreaming}
                  className={cn(
                    'p-3 rounded-xl',
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
