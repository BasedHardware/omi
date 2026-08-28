'use client';

import { useMemo } from 'react';
import { Bell } from 'lucide-react';
import { useNotificationContext } from './NotificationContext';
import { NotificationItem } from './NotificationItem';
import { NotificationPermissionBanner } from './NotificationPermissionBanner';
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
      notifDate.getDate(),
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

/**
 * The scrollable body of a notifications surface: permission banner, the
 * grouped list, and the empty state. Pure view over NotificationContext — no
 * open/close chrome — so the side panel and the mobile menu rail render the
 * exact same list.
 */
export function NotificationList() {
  const {
    notifications,
    permission,
    isSupported,
    navigateToNotification,
    markAsRead,
    clearNotification,
    getAppImage,
  } = useNotificationContext();

  const groupedNotifications = useMemo(
    () => groupNotificationsByDate(notifications),
    [notifications],
  );

  const showPermissionBanner =
    isSupported && (permission === 'default' || permission === 'denied');

  return (
    <div className="flex h-full flex-col">
      {/* Permission banner */}
      {showPermissionBanner && <NotificationPermissionBanner />}

      {/* Notifications list */}
      <div className="flex-1 overflow-y-auto">
        {notifications.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center px-4 py-12 text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-bg-tertiary">
              <Bell className="h-8 w-8 text-text-quaternary" />
            </div>
            <p className="mb-1 font-medium text-text-secondary">No notifications yet</p>
            <p className="text-sm text-text-quaternary">
              When you receive notifications, they&apos;ll appear here
            </p>
          </div>
        ) : (
          <div className="divide-y divide-bg-tertiary">
            {groupedNotifications.map((group) => (
              <div key={group.label}>
                <div className="sticky top-0 bg-bg-primary/50 px-4 py-2">
                  <p className="text-xs font-medium uppercase tracking-wide text-text-quaternary">
                    {group.label}
                  </p>
                </div>
                <div>
                  {group.notifications.map((notification) => {
                    // Extract app_id from notification data for image lookup
                    // Try multiple sources: direct data fields, or extract from navigate_to
                    let appId =
                      (notification.data?.app_id as string | undefined) ||
                      (notification.data?.plugin_id as string | undefined);

                    // Fallback: extract from navigate_to (e.g., /chat/bitcoin-live)
                    if (!appId && notification.navigate_to?.startsWith('/chat/')) {
                      appId = notification.navigate_to.split('/').pop();
                    }

                    return (
                      <NotificationItem
                        key={notification.id}
                        notification={notification}
                        onClick={() => navigateToNotification(notification)}
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
  );
}
