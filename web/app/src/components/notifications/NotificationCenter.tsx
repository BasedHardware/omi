'use client';

import { useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Bell, CheckCheck, Trash2 } from 'lucide-react';
import { useNotificationContext } from './NotificationContext';
import { NotificationItem } from './NotificationItem';
import { NotificationPermissionBanner } from './NotificationPermissionBanner';
import { cn } from '@/lib/utils';
import type { OmiNotification } from '@/types/notification';

/**
 * Group notifications by date (Today, Yesterday, Earlier)
 */
function groupNotificationsByDate(notifications: OmiNotification[]) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);

  const groups: { label: string; notifications: OmiNotification[] }[] = [
    { label: 'Today', notifications: [] },
    { label: 'Yesterday', notifications: [] },
    { label: 'Earlier', notifications: [] },
  ];

  notifications.forEach((notification) => {
    const notifDate = new Date(notification.timestamp);
    const notifDay = new Date(
      notifDate.getFullYear(),
      notifDate.getMonth(),
      notifDate.getDate()
    );

    if (notifDay.getTime() >= today.getTime()) {
      groups[0].notifications.push(notification);
    } else if (notifDay.getTime() >= yesterday.getTime()) {
      groups[1].notifications.push(notification);
    } else {
      groups[2].notifications.push(notification);
    }
  });

  // Filter out empty groups
  return groups.filter((g) => g.notifications.length > 0);
}

export function NotificationCenter() {
  const {
    isOpen,
    closeNotificationCenter,
    notifications,
    unreadCount,
    permission,
    isSupported,
    markAllAsRead,
    clearAllNotifications,
    navigateToNotification,
    markAsRead,
    clearNotification,
    getAppImage,
  } = useNotificationContext();

  const groupedNotifications = useMemo(
    () => groupNotificationsByDate(notifications),
    [notifications]
  );

  const showPermissionBanner =
    isSupported && (permission === 'default' || permission === 'denied');

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
            className="fixed inset-0 bg-black/30 z-40 sm:hidden"
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
              'bg-bg-secondary border-l border-border/50',
              'max-sm:fixed max-sm:inset-0 max-sm:z-50 max-sm:w-full'
            )}
          >
            <div
              className={cn('w-[400px] h-full flex flex-col', 'max-sm:w-full')}
            >
              {/* Header — matches page header */}
              <div className="flex items-center justify-between px-3 h-16 border-b border-border/50">
                <div className="flex items-center gap-2">
                  <Bell className="w-3.5 h-3.5 text-muted-foreground" />
                  <span className="text-sm font-medium text-foreground">Notifications</span>
                  {unreadCount > 0 && (
                    <span className="text-xs text-muted-foreground">{unreadCount}</span>
                  )}
                </div>
                <div className="flex items-center gap-0.5">
                  {unreadCount > 0 && (
                    <button
                      onClick={markAllAsRead}
                      className="p-1.5 rounded-md hover:bg-accent transition-colors"
                      aria-label="Mark all read"
                      title="Mark all read"
                    >
                      <CheckCheck className="w-3.5 h-3.5 text-muted-foreground" />
                    </button>
                  )}
                  {notifications.length > 0 && (
                    <button
                      onClick={clearAllNotifications}
                      className="p-1.5 rounded-md hover:bg-accent transition-colors"
                      aria-label="Clear all"
                      title="Clear all"
                    >
                      <Trash2 className="w-3.5 h-3.5 text-muted-foreground" />
                    </button>
                  )}
                  <button
                    onClick={closeNotificationCenter}
                    className="p-1.5 rounded-md hover:bg-accent transition-colors"
                    aria-label="Close"
                  >
                    <X className="w-3.5 h-3.5 text-muted-foreground" />
                  </button>
                </div>
              </div>

              {/* Permission banner */}
              {showPermissionBanner && <NotificationPermissionBanner />}

              {/* Notifications list */}
              <div className="flex-1 overflow-y-auto">
                {notifications.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full px-4 py-12 text-center">
                    <div className="w-16 h-16 rounded-full bg-bg-tertiary flex items-center justify-center mb-4">
                      <Bell className="w-8 h-8 text-muted-foreground" />
                    </div>
                    <p className="text-text-secondary font-medium mb-1">
                      No notifications yet
                    </p>
                    <p className="text-sm text-muted-foreground">
                      When you receive notifications, they&apos;ll appear here
                    </p>
                  </div>
                ) : (
                  <div className="divide-y divide-bg-tertiary">
                    {groupedNotifications.map((group) => (
                      <div key={group.label}>
                        <div className="px-4 py-2 bg-bg-primary/50 sticky top-0">
                          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                            {group.label}
                          </p>
                        </div>
                        <div>
                          {group.notifications.map((notification) => {
                            // Extract app_id from notification data for image lookup
                            // Try multiple sources: direct data fields, or extract from navigate_to
                            let appId = notification.data?.app_id as string | undefined
                              || notification.data?.plugin_id as string | undefined;

                            // Fallback: extract from navigate_to (e.g., /chat/bitcoin-live)
                            if (!appId && notification.navigate_to?.startsWith('/chat/')) {
                              appId = notification.navigate_to.split('/').pop();
                            }

                            return (
                              <NotificationItem
                                key={notification.id}
                                notification={notification}
                                onClick={() =>
                                  navigateToNotification(notification)
                                }
                                onMarkAsRead={() => markAsRead(notification.id)}
                                onClear={() => clearNotification(notification.id)}
                                appImage={getAppImage(appId)}
                              />
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
