'use client';

import { MessageCircle, X } from 'lucide-react';
import { useChat } from './ChatContext';
import { cn } from '@/lib/utils';

export function ChatBubble() {
  const { isOpen, toggleChat } = useChat();

  return (
    <button
      onClick={toggleChat}
      className={cn(
        'fixed bottom-20 lg:bottom-6 right-6 z-50',
        'w-14 h-14 rounded-full',
        'flex items-center justify-center',
        'shadow-lg shadow-black/40',
        'transition-colors duration-200',
        isOpen
          ? 'bg-bg-tertiary hover:bg-bg-quaternary'
          : 'bg-text-primary text-bg-primary hover:bg-text-primary/80',
      )}
      aria-label={isOpen ? 'Close chat' : 'Open chat'}
    >
      {isOpen ? (
        <X className="w-6 h-6 text-text-primary" />
      ) : (
        // The closed pill is white, so the icon has to be the dark token — a
        // white icon on it is white on white.
        <MessageCircle className="w-6 h-6 text-bg-primary" />
      )}
    </button>
  );
}
