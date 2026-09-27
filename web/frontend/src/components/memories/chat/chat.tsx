'use client';

import { useState, useRef, useEffect } from 'react';
import { TranscriptSegment } from '@/src/types/memory.types';
import chatWithMemory from '@/src/actions/memories/chat-with-memory';
import { Send, UserCircle, Message, ArrowDown } from 'iconoir-react';
import Markdown from 'markdown-to-jsx';

interface ChatProps {
  conversationId: string;
  transcript: TranscriptSegment[];
  onClearChatRef?: (clearFn: () => void) => void;
  onMessagesChange?: (hasMessages: boolean) => void;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export default function Chat({
  conversationId,
  transcript,
  onClearChatRef,
  onMessagesChange,
}: ChatProps) {
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
        conversationId,
        history: messages.slice(-8),
        question: userMessage.content,
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
      <p className="sn-muted" style={{ marginTop: 24 }}>
        There&apos;s no transcript to ask about for this note.
      </p>
    );
  }

  return (
    <div>
      <div className="sn-chat">
        {/* Messages Container */}
        <div
          ref={messagesContainerRef}
          onScroll={handleScroll}
          className="chat-messages-container sn-chat-scroll"
        >
          <div>
            {messages.length === 0 && (
              <>
                <div className="sn-chat-row">
                  <span className="sn-chat-avatar" aria-hidden="true">
                    <Message />
                  </span>
                  <div className="sn-chat-bubble">
                    Ask me anything about this conversation — key points, decisions, or a
                    follow-up email.
                  </div>
                </div>
                {/* Suggestion Questions */}
                <div className="sn-suggestions">
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
                            conversationId,
                            history: messages.slice(-8),
                            question: userMessage.content,
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
                                content:
                                  'Sorry, I encountered an error. Please try again.',
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
                      type="button"
                      className="sn-suggestion"
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
                className={`sn-chat-row${
                  message.role === 'user' ? ' sn-chat-row-user' : ''
                }`}
              >
                <span className="sn-chat-avatar" aria-hidden="true">
                  {message.role === 'user' ? <UserCircle /> : <Message />}
                </span>
                <div className="sn-chat-bubble">
                  {message.role === 'assistant' ? (
                    <Markdown className="sn-md">{message.content}</Markdown>
                  ) : (
                    message.content
                  )}
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="sn-chat-row">
                <span className="sn-chat-avatar" aria-hidden="true">
                  <Message />
                </span>
                <div className="sn-chat-bubble">
                  <span className="sn-typing">
                    <span className="sn-typing-dot" />
                    <span className="sn-typing-dot" />
                    <span className="sn-typing-dot" />
                    Thinking…
                  </span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Scroll to bottom button */}
          {showScrollButton && (
            <button
              onClick={() => scrollToBottom()}
              type="button"
              className="sn-icon-btn sn-chat-jump"
              aria-label="Scroll to bottom"
            >
              <ArrowDown />
            </button>
          )}
        </div>

        {/* Input Area - Fixed at bottom */}
        <div className="sn-chat-compose">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about this conversation…"
            aria-label="Ask about this conversation"
            className="sn-chat-input"
            rows={1}
            disabled={isLoading}
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="sn-chat-send"
            title="Send message"
            aria-label="Send message"
          >
            <Send />
          </button>
        </div>
      </div>
    </div>
  );
}
