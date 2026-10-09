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
  buttonRef,
}: {
  isOpen: boolean;
  onClick: () => void;
  buttonRef?: React.Ref<HTMLButtonElement>;
}) {
  return (
    <button
      ref={buttonRef}
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

function NotificationIconButton({
  unreadCount,
  onClick,
  buttonRef,
  variant,
  available,
}: {
  unreadCount: number;
  onClick: () => void;
  buttonRef?: React.Ref<HTMLButtonElement>;
  /** `gooey` sits on the liquid blob, which is the white surface itself. */
  variant: 'gooey' | 'plain';
  /** False while the control is collapsed and must not be reachable. */
  available: boolean;
}) {
  return (
    <button
      ref={buttonRef}
      type="button"
      onClick={onClick}
      className={cn(
        fabClass,
        'relative',
        available ? 'pointer-events-auto' : 'pointer-events-none',
        variant === 'plain' &&
          'bg-text-primary shadow-lg shadow-black/40 hover:bg-text-primary/80',
      )}
      aria-label="Notifications"
      aria-hidden={!available}
      inert={!available}
      tabIndex={available ? 0 : -1}
    >
      <Bell className="h-6 w-6" />
      <span className="t-badge" data-open={unreadCount > 0 ? 'true' : 'false'}>
        <span className="t-badge-dot flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
          {unreadCount > 99 ? '99+' : unreadCount}
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
  const chatRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const media = window.matchMedia('(pointer: coarse)');
    const sync = () => setCoarse(media.matches);
    sync();
    media.addEventListener('change', sync);
    return () => media.removeEventListener('change', sync);
  }, []);

  /**
   * The notifications control is a second circle next to the chat button, so it
   * is out only when it can be reached and has something to say: while the
   * pointer hovers the corner, or on a touch screen with something unread. A
   * phone cannot hover, and an unread count of zero left two identical circles
   * stacked in the corner.
   */
  const fan = hovered || (coarse && unreadCount > 0);

  const handleMouseLeave = () => {
    // The fan collapses under the pointer; if the bell held focus, hand it to
    // the control that stays on screen instead of dropping it to the document.
    if (document.activeElement === notifyRef.current) chatRef.current?.focus();
    setHovered(false);
  };

  if (reduceMotion) {
    return (
      <div
        className="fixed bottom-20 right-6 z-50 flex flex-col items-center gap-3 lg:bottom-6"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={handleMouseLeave}
      >
        {fan && (
          <NotificationIconButton
            variant="plain"
            available
            unreadCount={unreadCount}
            onClick={toggleNotificationCenter}
            buttonRef={notifyRef}
          />
        )}
        <ChatIconButton isOpen={isOpen} onClick={toggleChat} buttonRef={chatRef} />
      </div>
    );
  }

  return (
    <div
      className="pointer-events-none fixed bottom-20 right-6 z-50 h-[136px] w-14 lg:bottom-6"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={handleMouseLeave}
    >
      <Liquid
        className="h-full w-full"
        blur={fan ? 6 : 0}
        contrast={fan ? 18 : 1}
        fill="#ffffff"
        shadow="0 10px 15px -3px rgba(0,0,0,0.4)"
        filterPadding={fan ? 80 : 0}
      >
        {/* Both items stay mounted so the column keeps its shape and the chat
            button keeps its corner: the gooey layer paints one white blob per
            item, and it paints that blob for an item that is merely transparent
            — which is what left a blank white circle stacked on the chat
            button. Scaling the collapsed item away takes its blob with it.

            The fan lifts the bell one small step (16px clear of the chat
            button) rather than a full body height, so the two read as one
            control that opened instead of two circles in opposite corners. */}
        <Liquid.Item x={0} y={fan ? -16 : 0} scale={fan ? 1 : 0} transition="bouncy">
          <NotificationIconButton
            variant="gooey"
            available={fan}
            unreadCount={unreadCount}
            onClick={toggleNotificationCenter}
            buttonRef={notifyRef}
          />
        </Liquid.Item>
        <Liquid.Item>
          <ChatIconButton isOpen={isOpen} onClick={toggleChat} buttonRef={chatRef} />
        </Liquid.Item>
      </Liquid>
    </div>
  );
}
