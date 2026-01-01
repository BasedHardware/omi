'use client';

import { useRef, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Send, Sparkles, Trash2, Brain } from 'lucide-react';
import { useChat } from '@/hooks/useChat';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { cn } from '@/lib/utils';

// Quick prompts for the chat
const quickPrompts = [
  'What did I talk about today?',
  'Show my pending tasks',
  'What should I remember?',
  'Summarize my recent conversations',
];

export function FullPageChat() {
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
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Load history on mount
  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

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

  const handleSend = async (text: string = input) => {
    if (!text.trim() || isStreaming) return;
    setInput('');
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }
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
    <div className="flex flex-col h-full bg-bg-primary">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-bg-tertiary bg-bg-secondary">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-purple-primary/20 flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-purple-primary" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-text-primary">Chat with Omi</h1>
            <p className="text-sm text-text-tertiary">
              Ask me anything about your conversations, tasks, or memories
            </p>
          </div>
        </div>
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
        <div className="max-w-3xl mx-auto px-4 py-6">
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
                  <div
                    className={cn(
                      'max-w-[85%] sm:max-w-[75%] rounded-2xl px-5 py-3',
                      message.sender === 'human'
                        ? 'bg-purple-primary text-white'
                        : 'bg-bg-secondary border border-bg-tertiary text-text-primary'
                    )}
                  >
                    <p className="text-sm whitespace-pre-wrap leading-relaxed">
                      {message.text}
                    </p>
                  </div>
                </motion.div>
              ))}

              {/* Thinking indicator */}
              {currentThinking && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex justify-start"
                >
                  <div className="max-w-[85%] sm:max-w-[75%] rounded-2xl px-5 py-3 bg-bg-secondary/50 border border-purple-primary/20">
                    <div className="flex items-center gap-2 text-purple-primary mb-2">
                      <Brain className="w-4 h-4" />
                      <span className="text-sm font-medium">Thinking...</span>
                    </div>
                    <p className="text-xs text-text-quaternary whitespace-pre-wrap line-clamp-4">
                      {currentThinking}
                    </p>
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
                  <div className="max-w-[85%] sm:max-w-[75%] rounded-2xl px-5 py-3 bg-bg-secondary border border-bg-tertiary text-text-primary">
                    <p className="text-sm whitespace-pre-wrap leading-relaxed">
                      {streamingText}
                    </p>
                    <span className="inline-block w-2 h-4 bg-purple-primary/50 animate-pulse ml-0.5" />
                  </div>
                </motion.div>
              )}

              {/* Loading indicator (before streaming starts) */}
              {isStreaming && !streamingText && !currentThinking && (
                <div className="flex justify-start">
                  <div className="bg-bg-secondary border border-bg-tertiary rounded-2xl px-5 py-4">
                    <div className="flex gap-1.5">
                      <div className="w-2 h-2 bg-text-quaternary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <div className="w-2 h-2 bg-text-quaternary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <div className="w-2 h-2 bg-text-quaternary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
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
        <div className="max-w-3xl mx-auto px-4 py-4">
          <div className="flex items-center gap-3">
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
            <button
              onClick={() => handleSend()}
              disabled={!input.trim() || isStreaming}
              className={cn(
                'w-[48px] h-[48px] rounded-xl flex-shrink-0',
                'flex items-center justify-center',
                'bg-purple-primary hover:bg-purple-secondary',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'transition-colors'
              )}
              aria-label="Send message"
            >
              <Send className="w-5 h-5 text-white" />
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
