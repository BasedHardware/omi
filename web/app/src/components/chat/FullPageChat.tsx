'use client';

import { useEffect, useState, useCallback } from 'react';
import { Sparkles, Trash2, Brain } from 'lucide-react';
import { GenerativeMarkdown } from '@/components/generative-ui/GenerativeMarkdown';
import { useChat } from '@/hooks/useChat';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Button } from '@/components/ui/button';
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from '@/components/ai-elements/conversation';
import {
  Message,
  MessageContent,
} from '@/components/ai-elements/message';
import {
  Suggestions,
  Suggestion,
} from '@/components/ai-elements/suggestion';
import {
  PromptInput,
  PromptInputTextarea,
  PromptInputFooter,
  PromptInputTools,
  PromptInputSubmit,
  PromptInputActionMenu,
  PromptInputActionMenuTrigger,
  PromptInputActionMenuContent,
  PromptInputActionAddAttachments,
  type PromptInputMessage,
} from '@/components/ai-elements/prompt-input';
import { ALLOWED_EXTENSIONS, MAX_FILES } from './FilePreview';
import { InlineVoiceRecorder } from './VoiceRecorder';
import { AppSelector } from './AppSelector';
import { cn } from '@/lib/utils';
import { PageHeader } from '@/components/layout/PageHeader';

const quickPrompts = [
  'What did I talk about today?',
  'Show my pending tasks',
  'What should I remember?',
  'Summarize my recent conversations',
];

function formatMessageTime(isoDate: string): string {
  return new Date(isoDate).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

export function FullPageChat() {
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

  const [showClearDialog, setShowClearDialog] = useState(false);
  const [isClearing, setIsClearing] = useState(false);

  useEffect(() => {
    loadHistory();
  }, [loadHistory, selectedAppId]);

  const handleAppChange = useCallback((appId: string | null) => {
    setSelectedAppId(appId);
  }, []);

  const handleVoiceTranscript = (transcript: string) => {
    // Voice transcript will be handled via the PromptInput provider if needed
    // For now, directly send the transcript
    if (transcript.trim()) {
      sendMessage(transcript);
    }
  };

  // Called by PromptInput form onSubmit
  const handlePromptSubmit = async (message: PromptInputMessage) => {
    if (!message.text.trim() || isStreaming) return;
    await sendMessage(message.text);
  };

  // Called by Suggestion clicks
  const handleSend = async (text: string) => {
    if (!text.trim() || isStreaming) return;
    await sendMessage(text);
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

  const hasMessages = messages.length > 0 || isLoading;

  return (
    <div className="flex flex-col h-full bg-bg-primary">
      {/* Page Header */}
      <PageHeader title="Chat" icon={Sparkles} />

      {/* Toolbar: App Selector + Clear */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-white/10 bg-bg-secondary">
        <AppSelector
          selectedAppId={selectedAppId}
          onSelectApp={handleAppChange}
          disabled={isStreaming}
        />
        {messages.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowClearDialog(true)}
            title="Clear chat history"
            className="text-muted-foreground hover:text-foreground"
          >
            <Trash2 className="w-4 h-4" />
            <span className="hidden sm:inline">Clear chat</span>
          </Button>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="px-6 py-3 bg-destructive/10 border-b border-destructive/20">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      {/* Messages area — using AI SDK Conversation for auto-scroll */}
      <Conversation className="flex-1">
        <ConversationContent className="max-w-5xl mx-auto w-full px-4 py-6">
          {!hasMessages ? (
            /* Empty state with suggestions */
            <ConversationEmptyState className="min-h-[60vh]">
              <div className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center mb-6">
                <Sparkles className="w-10 h-10 text-primary" />
              </div>
              <h2 className="text-2xl text-foreground mb-3">
                <span className="font-display font-semibold">Hi! I&apos;m</span>{' '}
                <span className="font-serif italic font-medium">Nooto</span>
              </h2>
              <p className="text-muted-foreground max-w-md mb-8">
                I can help you explore your conversations, find tasks, recall memories,
                and answer questions about your life captured through Nooto.
              </p>

              <Suggestions className="justify-center max-w-lg">
                {quickPrompts.map((prompt) => (
                  <Suggestion
                    key={prompt}
                    suggestion={prompt}
                    onClick={handleSend}
                    disabled={isStreaming}
                    className="hover:border-primary/30"
                  />
                ))}
              </Suggestions>
            </ConversationEmptyState>
          ) : (
            <>
              {/* Rendered messages */}
              {messages.map((msg) => (
                <Message
                  key={msg.id}
                  from={msg.sender === 'human' ? 'user' : 'assistant'}
                >
                  <MessageContent
                    className={cn(
                      msg.sender === 'human'
                        ? 'bg-primary text-primary-foreground rounded-2xl'
                        : 'bg-card border border-border rounded-2xl px-5 py-3'
                    )}
                  >
                    {/* Attached files */}
                    {msg.files && msg.files.length > 0 && (
                      <div className="flex flex-wrap gap-2 mb-2">
                        {msg.files.map((file) => (
                          <div
                            key={file.id}
                            className={cn(
                              'text-xs px-2 py-1 rounded',
                              msg.sender === 'human' ? 'bg-white/20' : 'bg-secondary'
                            )}
                          >
                            {file.name}
                          </div>
                        ))}
                      </div>
                    )}
                    {msg.sender === 'ai' ? (
                      <GenerativeMarkdown content={msg.text} />
                    ) : (
                      <p className="text-sm whitespace-pre-wrap leading-relaxed">
                        {msg.text}
                      </p>
                    )}
                  </MessageContent>
                  <span className={cn(
                    'text-xs text-muted-foreground',
                    msg.sender === 'human' && 'text-right'
                  )}>
                    {formatMessageTime(msg.created_at)}
                  </span>
                </Message>
              ))}

              {/* Thinking indicator */}
              {currentThinking && (
                <Message from="assistant">
                  <MessageContent className="rounded-2xl bg-secondary/50 border border-primary/20 px-5 py-3">
                    <div className="flex items-center gap-2 text-primary mb-2">
                      <Brain className="w-4 h-4" />
                      <span className="text-sm font-medium">Thinking...</span>
                    </div>
                    <p className="text-xs text-muted-foreground whitespace-pre-wrap line-clamp-4">
                      {currentThinking}
                    </p>
                  </MessageContent>
                </Message>
              )}

              {/* Streaming response */}
              {streamingText && (
                <Message from="assistant">
                  <MessageContent className="rounded-2xl bg-card border border-border px-5 py-3">
                    <GenerativeMarkdown content={streamingText} />
                    <span className="inline-block w-2 h-4 bg-primary/50 animate-pulse ml-0.5" />
                  </MessageContent>
                </Message>
              )}

              {/* Loading dots */}
              {isStreaming && !streamingText && !currentThinking && (
                <Message from="assistant">
                  <MessageContent className="rounded-2xl bg-card border border-border px-5 py-4">
                    <div className="flex gap-1.5">
                      <div className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <div className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <div className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                  </MessageContent>
                </Message>
              )}

              {/* History loading */}
              {isLoading && messages.length === 0 && (
                <div className="flex justify-center py-12">
                  <div className="flex gap-1.5">
                    <div className="w-2.5 h-2.5 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <div className="w-2.5 h-2.5 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <div className="w-2.5 h-2.5 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              )}
            </>
          )}
        </ConversationContent>

        <ConversationScrollButton className="border-border" />
      </Conversation>

      {/* Input area — PromptInput from AI SDK Elements */}
      <div className="border-t border-border bg-bg-secondary">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <PromptInput
            onSubmit={handlePromptSubmit}
            accept={ALLOWED_EXTENSIONS}
            multiple
            maxFiles={MAX_FILES}
            className="bg-bg-secondary"
          >
            <PromptInputTextarea
              placeholder="Ask anything..."
              disabled={isStreaming}
              autoFocus
            />
            <PromptInputFooter>
              <PromptInputTools>
                <PromptInputActionMenu>
                  <PromptInputActionMenuTrigger tooltip="Attach" disabled={isStreaming} />
                  <PromptInputActionMenuContent>
                    <PromptInputActionAddAttachments label="Upload files" />
                  </PromptInputActionMenuContent>
                </PromptInputActionMenu>

                <InlineVoiceRecorder
                  onTranscript={handleVoiceTranscript}
                  disabled={isStreaming}
                />
              </PromptInputTools>

              <PromptInputSubmit
                status={isStreaming ? 'streaming' : undefined}
                disabled={isStreaming}
              />
            </PromptInputFooter>
          </PromptInput>
        </div>
      </div>

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
