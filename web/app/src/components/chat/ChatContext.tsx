'use client';

import { createContext, useContext, useState, useCallback, ReactNode } from 'react';

interface ChatContext {
  // Panel state
  isOpen: boolean;
  openChat: () => void;
  closeChat: () => void;
  toggleChat: () => void;

  // Context awareness
  currentContext: ChatContextInfo | null;
  setContext: (context: ChatContextInfo | null) => void;
}

export interface ChatContextInfo {
  type: 'conversation' | 'task' | 'memory' | 'general';
  id?: string;
  title?: string;
  summary?: string;
}

const ChatContext = createContext<ChatContext | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [currentContext, setCurrentContext] = useState<ChatContextInfo | null>(null);

  const openChat = useCallback(() => setIsOpen(true), []);
  const closeChat = useCallback(() => setIsOpen(false), []);
  const toggleChat = useCallback(() => setIsOpen((prev) => !prev), []);

  const setContext = useCallback((context: ChatContextInfo | null) => {
    setCurrentContext(context);
  }, []);

  return (
    <ChatContext.Provider
      value={{
        isOpen,
        openChat,
        closeChat,
        toggleChat,
        currentContext,
        setContext,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
}
