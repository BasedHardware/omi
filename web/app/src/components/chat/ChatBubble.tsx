'use client';

import { useEffect, useRef, useState } from 'react';
import { Bell, MessageCircle, X } from 'lucide-react';
import { Liquid } from 'liquid-gooey';
import { useReducedMotion } from 'framer-motion';
import { useChat } from './ChatContext';
import { useNotificationContext } from '@/components/notifications/NotificationContext';
import { cn } from '@/lib/utils';

const fabClass =
  'flex h-14 w-14 items-center justify-center rounded-full bg-transparent text-bg-primary';

function ChatIconButton({
  isOpen,
  onClick,
}: {
  isOpen: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(fabClass, 'pointer-events-auto')}
      aria-label={isOpen ? 'Close chat' : 'Open chat'}
    >
      <span className="t-icon-swap" data-state={isOpen ? 'b' : 'a'}>
        <span className="t-icon" data-icon="a">
          <MessageCircle className="h-6 w-6" />
        </span>
        <span className="t-icon" data-icon="b">
          <X className="h-6 w-6" />
        </span>
      </span>
    </button>
  );
}

export function ChatBubble() {
  const { isOpen, toggleChat } = useChat();
  const { toggleNotificationCenter, unreadCount } = useNotificationContext();
  const reduceMotion = useReducedMotion();
  const [hovered, setHovered] = useState(false);
  const [coarse, setCoarse] = useState(false);
  const notifyRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const media = window.matchMedia('(pointer: coarse)');
    const sync = () => setCoarse(media.matches);
    sync();
    media.addEventListener('change', sync);
    return () => media.removeEventListener('change', sync);
  }, []);

  const fan = coarse || hovered;

  useEffect(() => {
    if (fan) return;
    const notify = notifyRef.current;
    if (notify && document.activeElement === notify) {
      notify.blur();
    }
  }, [fan]);

  if (reduceMotion) {
    return (
      <div className="fixed bottom-20 right-6 z-50 flex flex-col items-center gap-3 lg:bottom-6">
        <button
          type="button"
          onClick={toggleNotificationCenter}
          className={cn(
            'relative flex h-14 w-14 items-center justify-center rounded-full',
            'bg-text-primary text-bg-primary shadow-lg shadow-black/40 hover:bg-text-primary/80',
          )}
          aria-label="Notifications"
        >
          <Bell className="h-6 w-6" />
          <span className="t-badge" data-open={unreadCount > 0 ? 'true' : 'false'}>
            <span className="t-badge-dot flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          </span>
        </button>
        <button
          type="button"
          onClick={toggleChat}
          className={cn(
            'flex h-14 w-14 items-center justify-center rounded-full',
            'shadow-lg shadow-black/40',
            isOpen
              ? 'bg-bg-tertiary text-text-primary hover:bg-bg-quaternary'
              : 'bg-text-primary text-bg-primary hover:bg-text-primary/80',
          )}
          aria-label={isOpen ? 'Close chat' : 'Open chat'}
        >
          {isOpen ? <X className="h-6 w-6" /> : <MessageCircle className="h-6 w-6" />}
        </button>
      </div>
    );
  }

  return (
    <div
      className="pointer-events-none fixed bottom-20 right-6 z-50 h-[136px] w-14 lg:bottom-6"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <Liquid
        className="h-full w-full"
        blur={fan ? 6 : 0}
        contrast={fan ? 18 : 1}
        fill="#ffffff"
        shadow="0 10px 15px -3px rgba(0,0,0,0.4)"
        filterPadding={fan ? 80 : 0}
      >
        <Liquid.Item x={0} y={fan ? -72 : 0} transition="bouncy">
          <button
            ref={notifyRef}
            type="button"
            onClick={toggleNotificationCenter}
            className={cn(fabClass, fan ? 'pointer-events-auto' : 'pointer-events-none opacity-0')}
            aria-label="Notifications"
            tabIndex={fan ? 0 : -1}
            aria-hidden={!fan}
            inert={!fan}
          >
            <span className="relative">
              <Bell className="h-6 w-6" />
              <span className="t-badge" data-open={unreadCount > 0 ? 'true' : 'false'}>
                <span className="t-badge-dot flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
                  {unreadCount > 99 ? '99+' : unreadCount}
                </span>
              </span>
            </span>
          </button>
        </Liquid.Item>
        <Liquid.Item>
          <ChatIconButton isOpen={isOpen} onClick={toggleChat} />
        </Liquid.Item>
      </Liquid>
    </div>
  );
}
