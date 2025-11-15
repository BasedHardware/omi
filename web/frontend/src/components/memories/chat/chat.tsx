'use client';

import { useState, useRef, useEffect } from 'react';
import { TranscriptSegment } from '@/src/types/memory.types';
import chatWithMemory from '@/src/actions/memories/chat-with-memory';
import { Send, UserCircle, Message, ArrowDown } from 'iconoir-react';
import Markdown from 'markdown-to-jsx';

interface ChatProps {
  transcript: TranscriptSegment[];
  onClearChatRef?: (clearFn: () => void) => void;
  onMessagesChange?: (hasMessages: boolean) => void;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export default function Chat({ transcript, onClearChatRef, onMessagesChange }: ChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Add custom scrollbar styles
  useEffect(() => {
    const style = document.createElement('style');
    style.textContent = `
      .chat-messages-container::-webkit-scrollbar {
        width: 8px;
      }
      .chat-messages-container::-webkit-scrollbar-track {
        background: transparent;
      }
      .chat-messages-container::-webkit-scrollbar-thumb {
        background: #3f3f46;
        border-radius: 4px;
      }
      .chat-messages-container::-webkit-scrollbar-thumb:hover {
        background: #52525b;
      }
    `;
    document.head.appendChild(style);
    return () => {
      document.head.removeChild(style);
    };
  }, []);

  // Convert transcript segments to a readable string
  const transcriptText = transcript
    .map((segment) => {
      const speaker = segment.is_user ? 'Owner' : `Speaker ${segment.speaker_id}`;
      return `${speaker}: ${segment.text}`;
    })
    .join('\n\n');

  const scrollToBottom = (smooth = true) => {
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTo({
        top: messagesContainerRef.current.scrollHeight,
        behavior: smooth ? 'smooth' : 'auto',
      });
    }
  };

  // Handle scroll to check if user is at bottom
  const handleScroll = () => {
    if (messagesContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
      setShowScrollButton(!isNearBottom && messages.length > 0);
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      const newHeight = Math.min(textareaRef.current.scrollHeight, 120);
      textareaRef.current.style.height = `${newHeight}px`;
    }
  }, [input]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      role: 'user',
      content: input.trim(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await chatWithMemory({
        messages: [...messages, userMessage],
        transcript: transcriptText,
      });

      if (response) {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: response.message,
          },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: 'Sorry, I encountered an error. Please try again.',
          },
        ]);
      }
    } catch (error) {
      console.error('Error sending message:', error);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Sorry, I encountered an error. Please try again.',
        },
      ]);
    } finally {
      setIsLoading(false);
      textareaRef.current?.focus();
    }
  };

  const handleClearChat = () => {
    setMessages([]);
    setInput('');
    textareaRef.current?.focus();
  };

  // Expose clear chat function to parent
  useEffect(() => {
    if (onClearChatRef) {
      onClearChatRef(handleClearChat);
    }
  }, [onClearChatRef]);

  // Notify parent when messages change
  useEffect(() => {
    if (onMessagesChange) {
      onMessagesChange(messages.length > 0);
    }
  }, [messages.length, onMessagesChange]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (transcript.length === 0) {
    return (
      <div className="px-4 md:px-12">
        <p className="mt-4 text-gray-400">No transcript available for chat.</p>
      </div>
    );
  }

  return (
    <div className="px-4 pb-8 md:px-12">
      <div className="flex flex-col rounded-lg border border-zinc-800/50 bg-zinc-900/20">
        {/* Messages Container */}
        <div
          ref={messagesContainerRef}
          onScroll={handleScroll}
          className={`chat-messages-container relative overflow-y-auto ${messages.length === 0 ? 'pb-2 pt-4 px-4 md:pt-6 md:px-6' : 'p-4 md:p-6'}`}
          style={{
            height: '400px',
            overflowY: 'auto',
            WebkitOverflowScrolling: 'touch',
            scrollBehavior: 'smooth',
            // Custom scrollbar styling for Firefox
            scrollbarWidth: 'thin',
            scrollbarColor: '#3f3f46 transparent'
          }}
        >
          <div className={messages.length === 0 ? 'space-y-0' : 'space-y-6'}>
            {messages.length === 0 && (
              <>
                <div className="mb-4 flex gap-4">
                  {/* Avatar */}
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-purple-500 to-purple-600">
                    <Message className="h-5 w-5 text-white" />
                  </div>

                  {/* Message Content */}
                  <div className="flex flex-col gap-1">
                    <div className="max-w-[85%] rounded-2xl bg-zinc-800/80 px-4 py-3 text-gray-100 shadow-lg">
                      <p className="text-sm leading-relaxed md:text-base">
                        Hi! I can help you explore this conversation. Ask me questions about the transcript, key points, or any details you'd like to know more about.
                      </p>
                    </div>
                  </div>
                </div>
                {/* Suggestion Questions */}
                <div className="flex flex-wrap gap-2 pl-0 md:pl-12">
                  {[
                    'What are 3 key takeaways?',
                    'What are 3 top action items?',
                    'Write follow up email',
                  ].map((suggestion, index) => (
                    <button
                      key={index}
                      onClick={async () => {
                        const userMessage: ChatMessage = {
                          role: 'user',
                          content: suggestion,
                        };
                        setMessages((prev) => [...prev, userMessage]);
                        setInput('');
                        setIsLoading(true);

                        try {
                          const response = await chatWithMemory({
                            messages: [...messages, userMessage],
                            transcript: transcriptText,
                          });

                          if (response) {
                            setMessages((prev) => [
                              ...prev,
                              {
                                role: 'assistant',
                                content: response.message,
                              },
                            ]);
                          } else {
                            setMessages((prev) => [
                              ...prev,
                              {
                                role: 'assistant',
                                content: 'Sorry, I encountered an error. Please try again.',
                              },
                            ]);
                          }
                        } catch (error) {
                          console.error('Error sending message:', error);
                          setMessages((prev) => [
                            ...prev,
                            {
                              role: 'assistant',
                              content: 'Sorry, I encountered an error. Please try again.',
                            },
                          ]);
                        } finally {
                          setIsLoading(false);
                          textareaRef.current?.focus();
                        }
                      }}
                      className="inline-flex items-center rounded-full bg-zinc-800/50 px-3 py-1 text-xs text-zinc-400 ring-1 ring-inset ring-zinc-800 transition-all hover:bg-zinc-800 hover:text-zinc-300 md:text-sm"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </>
            )}
            {messages.map((message, index) => (
                <div
                  key={index}
                  className={`flex gap-4 ${
                    message.role === 'user' ? 'flex-row-reverse' : 'flex-row'
                  }`}
                >
                  {/* Avatar */}
                  <div
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                      message.role === 'user'
                        ? 'bg-gradient-to-br from-blue-500 to-blue-600'
                        : 'bg-gradient-to-br from-purple-500 to-purple-600'
                    }`}
                  >
                    {message.role === 'user' ? (
                      <UserCircle className="h-5 w-5 text-white" />
                    ) : (
                      <Message className="h-5 w-5 text-white" />
                    )}
                  </div>

                  {/* Message Content */}
                  <div
                    className={`flex min-w-0 flex-1 flex-col gap-1 ${
                      message.role === 'user' ? 'items-end' : 'items-start'
                    }`}
                  >
                    <div
                      className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                        message.role === 'user'
                          ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white shadow-lg'
                          : 'bg-zinc-800/80 text-gray-100 shadow-lg'
                      }`}
                    >
                      {message.role === 'assistant' ? (
                        <div className="prose prose-sm max-w-none dark:prose-invert prose-headings:text-gray-100 prose-p:text-gray-100 prose-p:leading-relaxed prose-strong:text-gray-100 prose-ul:text-gray-100 prose-ol:text-gray-100 prose-li:text-gray-100 prose-code:text-blue-300 prose-pre:bg-zinc-900 prose-pre:text-gray-200 prose-a:text-blue-400 prose-a:no-underline hover:prose-a:underline prose-blockquote:text-gray-100 prose-blockquote:border-l-blue-500 text-gray-100">
                          <Markdown>{message.content}</Markdown>
                        </div>
                      ) : (
                        <p className="whitespace-pre-wrap text-sm leading-relaxed md:text-base">
                          {message.content}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
              {isLoading && (
                <div className="flex gap-4">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-purple-500 to-purple-600">
                    <Message className="h-5 w-5 text-white" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <div className="rounded-2xl bg-zinc-800/80 px-4 py-3 shadow-lg">
                      <div className="flex items-center gap-2">
                        <div className="flex gap-1">
                          <div className="h-2 w-2 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.3s]"></div>
                          <div className="h-2 w-2 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.15s]"></div>
                          <div className="h-2 w-2 animate-bounce rounded-full bg-gray-400"></div>
                        </div>
                        <span className="text-sm text-gray-400">Thinking...</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
          </div>

          {/* Scroll to bottom button */}
          {showScrollButton && (
            <button
              onClick={() => scrollToBottom()}
              className="absolute bottom-4 right-4 flex h-10 w-10 items-center justify-center rounded-full bg-blue-600 text-white shadow-lg transition-all hover:bg-blue-700 hover:shadow-xl active:scale-95"
              aria-label="Scroll to bottom"
            >
              <ArrowDown className="h-5 w-5" />
            </button>
          )}
        </div>

        {/* Input Area - Fixed at bottom */}
        <div className="shrink-0 border-t border-zinc-800/50 bg-zinc-900/30 p-3 backdrop-blur-sm md:p-4">
          <div className="flex items-center gap-2 md:gap-3">
            <div className="relative flex-1">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask a question about this conversation..."
                className="w-full resize-none rounded-xl border border-zinc-700/50 bg-zinc-900/80 px-3 py-2.5 text-sm text-white placeholder:text-gray-500 focus:border-blue-500/50 focus:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition-all md:px-4 md:py-3 md:text-base"
                rows={1}
                disabled={isLoading}
                style={{
                  minHeight: '44px',
                  maxHeight: '120px',
                  overflow: 'hidden'
                }}
              />
            </div>
            <button
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-blue-700 text-white shadow-lg transition-all hover:from-blue-700 hover:to-blue-800 hover:shadow-xl active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:shadow-lg disabled:active:scale-100"
              title="Send message"
              aria-label="Send message"
            >
              <Send className="h-5 w-5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

