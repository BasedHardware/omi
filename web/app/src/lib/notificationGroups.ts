import type { OmiNotification } from '@/types/notification';

export interface NotificationDateGroup {
  label: 'Today' | 'Yesterday' | 'Earlier';
  notifications: OmiNotification[];
}

function startOfLocalDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

/**
 * Group notifications into Today, Yesterday, and Earlier.
 *
 * Yesterday is the previous local calendar day, not midnight minus 24 hours.
 * A daylight-saving fallback makes that day 25 hours long, so on the next
 * morning a fixed 24 hour step lands an hour after yesterday's midnight and
 * the whole day falls through to Earlier. `now` is injectable for tests.
 */
export function groupNotificationsByDate(
  notifications: readonly OmiNotification[],
  now: Date = new Date(),
): NotificationDateGroup[] {
  const today = startOfLocalDay(now);
  const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);

  const groups: NotificationDateGroup[] = [
    { label: 'Today', notifications: [] },
    { label: 'Yesterday', notifications: [] },
    { label: 'Earlier', notifications: [] },
  ];

  for (const notification of notifications) {
    const notifDate = new Date(notification.timestamp);
    if (Number.isNaN(notifDate.getTime())) {
      groups[2].notifications.push(notification);
      continue;
    }
    const notifDay = startOfLocalDay(notifDate).getTime();
    if (notifDay >= today.getTime()) {
      groups[0].notifications.push(notification);
    } else if (notifDay >= yesterday.getTime()) {
      groups[1].notifications.push(notification);
    } else {
      groups[2].notifications.push(notification);
    }
  }

  return groups.filter((group) => group.notifications.length > 0);
}
