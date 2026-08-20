'use client';

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useMemo,
  ReactNode,
} from 'react';
import { useChat as useChatSession } from '@/hooks/useChat';

type SharedChat = ReturnType<typeof useChatSession>;

interface ChatContext {
  // Panel state
  isOpen: boolean;
  openChat: () => void;
  closeChat: () => void;
  toggleChat: () => void;

  // Context awareness
  currentContext: ChatContextInfo | null;
  setContext: (context: ChatContextInfo | null) => void;

  /**
   * The chat session being read, or `null` for the default shared thread.
   * Owned here because both the panel and Home render the same transcript;
   * a selection held by either one alone could not move the other.
   */
  selectedChatSessionId: string | null;
  selectChatSession: (sessionId: string | null) => void;
  chat: SharedChat;

  // App-specific chat (for notification routing)
  selectedAppId: string | null;
  selectApp: (appId: string | null) => void;
  openChatWithApp: (appId: string) => void;
  clearAppContext: () => void;
}

export interface ChatContextInfo {
  type: 'conversation' | 'task' | 'memory' | 'recap' | 'general';
  id?: string;
  title?: string;
  summary?: string;
  /** ISO datetime with offset; hard-scopes chat retrieval (#4515). */
  start_date?: string;
  end_date?: string;
}

const ChatContext = createContext<ChatContext | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [currentContext, setCurrentContext] = useState<ChatContextInfo | null>(null);
  const [selectedAppId, setSelectedAppId] = useState<string | null>(null);
  const [selectedChatSessionId, setSelectedChatSessionId] = useState<string | null>(null);
  const chat = useChatSession({
    appId: selectedAppId ?? undefined,
    chatSessionId: selectedChatSessionId,
  });

  const openChat = useCallback(() => setIsOpen(true), []);
  const closeChat = useCallback(() => setIsOpen(false), []);
  const toggleChat = useCallback(() => setIsOpen((prev) => !prev), []);

  const setContext = useCallback((context: ChatContextInfo | null) => {
    setCurrentContext(context);
  }, []);

  const selectChatSession = useCallback((sessionId: string | null) => {
    setSelectedChatSessionId(sessionId);
  }, []);

  const selectApp = useCallback((appId: string | null) => {
    setSelectedAppId(appId);
  }, []);

  // Open chat with a specific app context
  const openChatWithApp = useCallback((appId: string) => {
    setSelectedAppId(appId);
    setIsOpen(true);
  }, []);

  // Clear app context and return to general Omi chat
  const clearAppContext = useCallback(() => {
    setSelectedAppId(null);
  }, []);

  // Memoize context value to prevent cascading re-renders of all consumers
  const value = useMemo(
    () => ({
      isOpen,
      openChat,
      closeChat,
      toggleChat,
      currentContext,
      setContext,
      selectedChatSessionId,
      selectChatSession,
      chat,
      selectedAppId,
      selectApp,
      openChatWithApp,
      clearAppContext,
    }),
    [
      isOpen,
      openChat,
      closeChat,
      toggleChat,
      currentContext,
      setContext,
      selectedChatSessionId,
      selectChatSession,
      chat,
      selectedAppId,
      selectApp,
      openChatWithApp,
      clearAppContext,
    ],
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat() {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
}
