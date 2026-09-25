'use client';

import { useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import Image from '@tschk/moonshine-next/image';
import { Brain } from 'lucide-react';
import type { ClientMessage } from '@/types/conversation';
import { cn } from '@/lib/utils';
import { parseChatEvidenceFromRecord } from '@/lib/chatEvidence';
import {
  nearestVerticalScroller,
  scrollEdgesOf,
  shouldFollowLiveEdge,
} from '@/lib/scrollEdges';
import { ChatMarkdown } from './ChatMarkdown';
import { ChatEvidenceCard } from './ChatEvidenceCard';

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
    <div className="h-10 w-10 flex-shrink-0">
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
          className={cn(size, 'animate-bounce rounded-full bg-text-quaternary')}
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
  const placedExchangeRef = useRef(false);

  // Follow the live edge only while the reader is already there. Home's
  // history sits in the same overflow ancestor, so a blanket scrollIntoView
  // here is what yanks an upward history gesture back down.
  useEffect(() => {
    if (!autoScroll) {
      placedExchangeRef.current = false;
      return;
    }
    const end = messagesEndRef.current;
    if (!end) return;
    const scroller = nearestVerticalScroller(end.parentElement);
    const pinnedToBottom = scroller
      ? scrollEdgesOf({
          scrollTop: scroller.scrollTop,
          scrollHeight: scroller.scrollHeight,
          clientHeight: scroller.clientHeight,
        }).atBottom
      : true;
    const force = !placedExchangeRef.current;
    if (!shouldFollowLiveEdge({ pinnedToBottom, force })) return;
    placedExchangeRef.current = true;
    end.scrollIntoView({ behavior: force ? 'auto' : 'smooth' });
  }, [autoScroll, messages, streamingText, isStreaming, currentThinking]);

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
            <div className="flex max-w-[85%] gap-3 sm:max-w-[75%]">
              <OmiAvatar />
              <div className="min-w-0 flex-1">
                <div className="rounded-2xl border border-stroke bg-bg-secondary px-5 py-3 text-text-primary">
                  {/* Show attached files if any */}
                  {message.files && message.files.length > 0 && (
                    <div className="mb-2 flex flex-wrap gap-2">
                      {message.files.map((file) => (
                        <div
                          key={file.id}
                          className="rounded bg-bg-tertiary px-2 py-1 text-xs"
                        >
                          {file.name}
                        </div>
                      ))}
                    </div>
                  )}
                  <ChatMarkdown>{message.text}</ChatMarkdown>
                </div>
                <ChatEvidenceCard envelope={parseChatEvidenceFromRecord(message)} />
                <span className="mt-1 block text-xs text-text-quaternary">
                  {formatMessageTime(message.created_at)}
                </span>
              </div>
            </div>
          ) : (
            /* Human message */
            <div className="max-w-[85%] sm:max-w-[75%]">
              {/* Desktop's user bubble is a neutral raised surface
                  (OmiColors.chatUserBubble #2C2C33), not a coloured fill. */}
              <div className="rounded-2xl bg-[#2C2C33] px-5 py-3 text-text-primary">
                {/* Show attached files if any */}
                {message.files && message.files.length > 0 && (
                  <div className="mb-2 flex flex-wrap gap-2">
                    {message.files.map((file) => (
                      <div
                        key={file.id}
                        className="rounded bg-white/10 px-2 py-1 text-xs"
                      >
                        {file.name}
                      </div>
                    ))}
                  </div>
                )}
                <p className="whitespace-pre-wrap text-sm leading-relaxed">
                  {message.text}
                </p>
              </div>
              <span className="mt-1 block text-right text-xs text-text-quaternary">
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
          <div className="flex max-w-[85%] gap-3 sm:max-w-[75%]">
            <OmiAvatar />
            <div className="rounded-2xl border border-stroke bg-bg-secondary/50 px-5 py-3">
              <div className="mb-2 flex items-center gap-2 text-text-secondary">
                <Brain className="h-4 w-4" />
                <span className="text-sm font-medium">Thinking...</span>
              </div>
              <p className="line-clamp-4 whitespace-pre-wrap text-xs text-text-quaternary">
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
          <div className="flex max-w-[85%] gap-3 sm:max-w-[75%]">
            <OmiAvatar />
            <div className="rounded-2xl border border-stroke bg-bg-secondary px-5 py-3 text-text-primary">
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
            <div className="rounded-2xl border border-stroke bg-bg-secondary px-5 py-4">
              <BouncingDots />
            </div>
          </div>
        </div>
      )}

      <div ref={messagesEndRef} />
    </div>
  );
}
