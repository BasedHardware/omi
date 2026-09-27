'use client';

import { useState, useRef, useEffect } from 'react';
import { TranscriptSegment } from '@/src/types/memory.types';
import chatWithMemory, { ChatLimitReason } from '@/src/actions/memories/chat-with-memory';
import { getOmiInstallLink } from '@/src/lib/conversation-share-platform-link.mjs';
import { useAuth } from '@/src/hooks/useAuth';
import { Send, UserCircle, Message, ArrowDown } from 'iconoir-react';
import Markdown from 'markdown-to-jsx';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export type SharedChatEvent =
  | { type: 'question_asked' | 'answered' | 'signin_clicked' | 'signin_completed' }
  | { type: 'limit_card_shown'; reason: ChatLimitReason }
  | { type: 'upsell_clicked'; target: 'phone_app' | 'mac_app' | 'pendant' };

interface ChatProps {
  conversationId: string;
  transcript: TranscriptSegment[];
  onClearChatRef?: (clearFn: () => void) => void;
  onMessagesChange?: (hasMessages: boolean) => void;
  onChatEvent?: (event: SharedChatEvent) => void;
}

const APP_STORE = 'https://apps.apple.com/us/app/friend-ai-wearable/id6502156163';
const PLAY_STORE = 'https://play.google.com/store/apps/details?id=com.friend.ios';
const CAMPAIGN =
  'utm_source=omi_share&utm_medium=shared_conversation&utm_campaign=ask_omi_limit';

export default function Chat({
  conversationId,
  transcript,
  onClearChatRef,
  onMessagesChange,
  onChatEvent,
}: ChatProps) {
  const { user, signIn, loading: authLoading } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [limitReason, setLimitReason] = useState<ChatLimitReason | null>(null);
  const [remaining, setRemaining] = useState(3);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [userAgent, setUserAgent] = useState('');
  const pendingQuestion = useRef<{ question: string; history: ChatMessage[] } | null>(
    null,
  );
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setUserAgent(navigator.userAgent);
  }, []);
  useEffect(() => {
    messagesContainerRef.current?.scrollTo({
      top: messagesContainerRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [messages, isLoading]);
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(
        textareaRef.current.scrollHeight,
        120,
      )}px`;
    }
  }, [input]);
  useEffect(() => {
    onMessagesChange?.(messages.length > 0);
  }, [messages.length, onMessagesChange]);

  const submitQuestion = async (
    question: string,
    history: ChatMessage[],
    token?: string,
    retry = false,
  ) => {
    if (isLoading) return;
    if (!retry) {
      setMessages((previous) => [...previous, { role: 'user', content: question }]);
      setInput('');
      onChatEvent?.({ type: 'question_asked' });
    }
    setIsLoading(true);
    try {
      const userIdToken = token ?? (user ? await user.getIdToken() : undefined);
      const response = await chatWithMemory({
        conversationId,
        history: history.slice(-8),
        question,
        userIdToken,
      });
      if (response.status === 'ok') {
        setMessages((previous) => [
          ...previous,
          { role: 'assistant', content: response.message },
        ]);
        onChatEvent?.({ type: 'answered' });
        pendingQuestion.current = null;
        if (response.remainingFreeQuestions !== undefined) {
          setRemaining(response.remainingFreeQuestions);
          if (response.remainingFreeQuestions === 0) {
            setLimitReason('free_questions_exhausted');
            onChatEvent?.({
              type: 'limit_card_shown',
              reason: 'free_questions_exhausted',
            });
          }
        } else {
          setLimitReason(null);
        }
      } else if (response.status === 'rate_limited') {
        pendingQuestion.current = { question, history };
        setLimitReason(response.reason);
        onChatEvent?.({ type: 'limit_card_shown', reason: response.reason });
      } else {
        setMessages((previous) => [
          ...previous,
          { role: 'assistant', content: response.message },
        ]);
      }
    } catch {
      setMessages((previous) => [
        ...previous,
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

  const handleSend = () => {
    const question = input.trim();
    if (question && !isLoading && !authLoading && !limitReason)
      void submitQuestion(question, messages);
  };

  const handleSignIn = async () => {
    onChatEvent?.({ type: 'signin_clicked' });
    const signedInUser = await signIn();
    if (!signedInUser) return;
    onChatEvent?.({ type: 'signin_completed' });
    const token = await signedInUser.getIdToken();
    const pending = pendingQuestion.current;
    setLimitReason(null);
    if (pending) void submitQuestion(pending.question, pending.history, token, true);
  };

  useEffect(() => {
    onClearChatRef?.(() => {
      setMessages([]);
      setInput('');
      pendingQuestion.current = null;
    });
  }, [onClearChatRef]);

  if (transcript.length === 0) {
    return (
      <p className="sn-muted" style={{ marginTop: 24 }}>
        There&apos;s no transcript to ask about for this note.
      </p>
    );
  }

  const installLink = getOmiInstallLink(userAgent);
  const phoneLinks =
    installLink === APP_STORE
      ? [{ label: 'App Store', href: APP_STORE }]
      : installLink === PLAY_STORE
      ? [{ label: 'Play Store', href: PLAY_STORE }]
      : [
          { label: 'App Store', href: APP_STORE },
          { label: 'Play Store', href: PLAY_STORE },
        ];
  const showSignIn = limitReason !== 'no_omi_account';

  return (
    <div className="sn-chat">
      <div
        ref={messagesContainerRef}
        onScroll={(event) => {
          const node = event.currentTarget;
          setShowScrollButton(
            node.scrollHeight - node.scrollTop - node.clientHeight > 100 &&
              messages.length > 0,
          );
        }}
        className="chat-messages-container sn-chat-scroll"
      >
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
            <div className="sn-suggestions">
              {[
                'What are 3 key takeaways?',
                'What are 3 top action items?',
                'Write follow up email',
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  className="sn-suggestion"
                  disabled={!!limitReason || isLoading || authLoading}
                  onClick={() => void submitQuestion(suggestion, messages)}
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
            className={`sn-chat-row${message.role === 'user' ? ' sn-chat-row-user' : ''}`}
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
        {showScrollButton && (
          <button
            type="button"
            className="sn-icon-btn sn-chat-jump"
            aria-label="Scroll to bottom"
            onClick={() =>
              messagesContainerRef.current?.scrollTo({
                top: messagesContainerRef.current.scrollHeight,
                behavior: 'smooth',
              })
            }
          >
            <ArrowDown />
          </button>
        )}
      </div>
      {limitReason ? (
        <div className="sn-chat-limit" role="status">
          <h3 className="sn-cta-title">Keep asking with Omi</h3>
          <p className="sn-cta-copy">
            You can explore this conversation further with Omi.
          </p>
          {showSignIn && (
            <button
              type="button"
              className="sn-cta-button"
              disabled={authLoading}
              onClick={() => void handleSignIn()}
            >
              Sign in with Omi to keep asking
            </button>
          )}
          <div className="sn-chat-upsell">
            <strong>New to Omi?</strong>
            <span>Get the phone app, Mac app, or pendant.</span>
            <div className="sn-chat-upsell-links">
              {phoneLinks.map(({ label, href }) => (
                <a
                  key={label}
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() =>
                    onChatEvent?.({ type: 'upsell_clicked', target: 'phone_app' })
                  }
                >
                  {label}
                </a>
              ))}
              <a
                href={`https://www.omi.me/pages/download?${CAMPAIGN}`}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() =>
                  onChatEvent?.({ type: 'upsell_clicked', target: 'mac_app' })
                }
              >
                Mac app
              </a>
              <a
                href={`https://www.omi.me/products/omi?${CAMPAIGN}`}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() =>
                  onChatEvent?.({ type: 'upsell_clicked', target: 'pendant' })
                }
              >
                Pendant
              </a>
            </div>
          </div>
        </div>
      ) : (
        <>
          <div className="sn-chat-compose">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Ask about this conversation…"
              aria-label="Ask about this conversation"
              className="sn-chat-input"
              rows={1}
              disabled={isLoading || authLoading}
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={!input.trim() || isLoading || authLoading}
              className="sn-chat-send"
              title="Send message"
              aria-label="Send message"
            >
              <Send />
            </button>
          </div>
          <p className="sn-chat-budget" aria-live="polite">
            {user
              ? 'Signed in with Omi'
              : `${remaining} free question${remaining === 1 ? '' : 's'} left`}
          </p>
        </>
      )}
    </div>
  );
}
