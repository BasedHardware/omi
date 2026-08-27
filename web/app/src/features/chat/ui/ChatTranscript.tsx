'use client';

import { useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import Image from '@tschk/moonshine-next/image';
import { Brain } from 'lucide-react';
import type { ClientMessage } from '@/types/conversation';
import { cn } from '@/lib/utils';
import { ChatMarkdown } from './ChatMarkdown';

/**
 * The chat transcript, with no chrome of its own.
 *
 * Desktop renders the transcript as a bare column inside the Home stage
 * (`ChatMessagesView`, `contentColumnWidth: 760`) rather than as a card, so it
 * can sit directly on whichever surface hosts it.
 */

// Format timestamp for display (e.g., "12:32 AM")
function formatMessageTime(isoDate: string): string {
  return new Date(isoDate).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

function OmiAvatar() {
  return (
    <div className="flex-shrink-0 w-10 h-10">
      <Image src="/logo.png" alt="Omi" width={40} height={40} className="rounded-full" />
    </div>
  );
}

function BouncingDots({ size = 'w-2 h-2' }: { size?: string }) {
  return (
    <div className="flex gap-1.5">
      {[0, 150, 300].map((delay) => (
        <div
          key={delay}
          className={cn(size, 'bg-text-quaternary rounded-full animate-bounce')}
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  );
}

interface ChatTranscriptProps {
  messages: ClientMessage[];
  isLoading: boolean;
  isStreaming: boolean;
  streamingText: string;
  currentThinking: string;
  autoScroll?: boolean;
}

export function ChatTranscript({
  messages,
  isLoading,
  isStreaming,
  streamingText,
  currentThinking,
  autoScroll = true,
}: ChatTranscriptProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom when messages change or streaming text updates
  useEffect(() => {
    if (autoScroll) messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [autoScroll, messages, streamingText]);

  if (isLoading && messages.length === 0) {
    return (
      <div className="flex justify-center py-12">
        <BouncingDots size="w-2.5 h-2.5" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {messages.map((message) => (
        <motion.div
          key={message.id}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
          className={cn(
            'flex',
            message.sender === 'human' ? 'justify-end' : 'justify-start',
          )}
        >
          {message.sender === 'ai' ? (
            /* AI message with Omi icon */
            <div className="flex gap-3 max-w-[85%] sm:max-w-[75%]">
              <OmiAvatar />
              <div className="flex-1 min-w-0">
                <div className="rounded-2xl px-5 py-3 bg-bg-secondary border border-stroke text-text-primary">
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
                  <ChatMarkdown>{message.text}</ChatMarkdown>
                </div>
                <span className="text-xs text-text-quaternary mt-1 block">
                  {formatMessageTime(message.created_at)}
                </span>
              </div>
            </div>
          ) : (
            /* Human message */
            <div className="max-w-[85%] sm:max-w-[75%]">
              {/* Desktop's user bubble is a neutral raised surface
                  (OmiColors.chatUserBubble #2C2C33), not a coloured fill. */}
              <div className="rounded-2xl px-5 py-3 bg-[#2C2C33] text-text-primary">
                {/* Show attached files if any */}
                {message.files && message.files.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-2">
                    {message.files.map((file) => (
                      <div
                        key={file.id}
                        className="text-xs px-2 py-1 rounded bg-white/10"
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
            <OmiAvatar />
            <div className="rounded-2xl px-5 py-3 bg-bg-secondary/50 border border-stroke">
              <div className="flex items-center gap-2 text-text-secondary mb-2">
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
            <OmiAvatar />
            <div className="rounded-2xl px-5 py-3 bg-bg-secondary border border-stroke text-text-primary">
              <ChatMarkdown isStreaming>{streamingText}</ChatMarkdown>
            </div>
          </div>
        </motion.div>
      )}

      {/* Loading indicator (before streaming starts) */}
      {isStreaming && !streamingText && !currentThinking && (
        <div className="flex justify-start">
          <div className="flex gap-3">
            <OmiAvatar />
            <div className="bg-bg-secondary border border-stroke rounded-2xl px-5 py-4">
              <BouncingDots />
            </div>
          </div>
        </div>
      )}

      <div ref={messagesEndRef} />
    </div>
  );
}
