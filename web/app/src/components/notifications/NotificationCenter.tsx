'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { X, Bell, CheckCheck, Trash2 } from 'lucide-react';
import { useNotificationContext } from './NotificationContext';
import { NotificationList } from './NotificationList';
import { cn } from '@/lib/utils';

export function NotificationCenter() {
  const {
    isOpen,
    closeNotificationCenter,
    notifications,
    unreadCount,
    markAllAsRead,
    clearAllNotifications,
  } = useNotificationContext();

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Mobile backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40 bg-black/30 sm:hidden"
            onClick={closeNotificationCenter}
          />

          {/* Panel - push/slide animation */}
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: 400 }}
            exit={{ width: 0 }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className={cn(
              'h-full flex-shrink-0 overflow-hidden',
              'border-l border-bg-tertiary bg-bg-secondary',
              'max-sm:fixed max-sm:inset-0 max-sm:z-50 max-sm:w-full',
            )}
          >
            <div className={cn('flex h-full w-[400px] flex-col', 'max-sm:w-full')}>
              {/* Header */}
              <div className="flex items-center justify-between border-b border-bg-tertiary p-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white/[0.14]">
                    <Bell className="h-4 w-4 text-text-primary" />
                  </div>
                  <div>
                    <h2 className="font-semibold text-text-primary">Notifications</h2>
                    {unreadCount > 0 && (
                      <p className="text-xs text-text-tertiary">{unreadCount} unread</p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  {unreadCount > 0 && (
                    <button
                      onClick={markAllAsRead}
                      className="rounded-lg p-2 transition-colors hover:bg-bg-tertiary"
                      aria-label="Mark all as read"
                      title="Mark all as read"
                    >
                      <CheckCheck className="h-4 w-4 text-text-quaternary hover:text-text-secondary" />
                    </button>
                  )}
                  {notifications.length > 0 && (
                    <button
                      onClick={clearAllNotifications}
                      className="rounded-lg p-2 transition-colors hover:bg-bg-tertiary"
                      aria-label="Clear all notifications"
                      title="Clear all notifications"
                    >
                      <Trash2 className="h-4 w-4 text-text-quaternary hover:text-text-secondary" />
                    </button>
                  )}
                  <button
                    onClick={closeNotificationCenter}
                    className="rounded-lg p-2 transition-colors hover:bg-bg-tertiary"
                    aria-label="Close notifications"
                  >
                    <X className="h-5 w-5 text-text-secondary" />
                  </button>
                </div>
              </div>

              {/* Body: banner + grouped list + empty state */}
              <NotificationList />
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
