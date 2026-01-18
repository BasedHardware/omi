'use client';

import { MessageCircle, X } from 'lucide-react';
import { usePathname } from 'next/navigation';
import { useChat } from './ChatContext';
import { cn } from '@/lib/utils';

export function ChatBubble() {
  const { isOpen, toggleChat } = useChat();
  const pathname = usePathname();

  // Hide on chat page since it already has a full chat interface
  if (pathname === '/chat') {
    return null;
  }

  return (
    <button
      onClick={toggleChat}
      className={cn(
        'fixed bottom-6 right-6 z-50',
        'w-14 h-14 rounded-full',
        'flex items-center justify-center',
        'shadow-lg shadow-purple-primary/25',
        'transition-colors duration-200',
        isOpen
          ? 'bg-bg-tertiary hover:bg-bg-quaternary'
          : 'bg-purple-primary hover:bg-purple-secondary'
      )}
      aria-label={isOpen ? 'Close chat' : 'Open chat'}
    >
      {isOpen ? (
        <X className="w-6 h-6 text-text-primary" />
      ) : (
        <MessageCircle className="w-6 h-6 text-white" />
      )}
    </button>
  );
}

