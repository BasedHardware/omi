'use client';

import Image from '@tschk/moonshine-next/image';
import {
  Clock,
  CalendarDays,
  Puzzle,
  Megaphone,
  GitMerge,
  Edit,
  Trash2,
  Bell,
  X,
} from 'lucide-react';
import { cn, formatNotificationTimestamp } from '@/lib/utils';
import type { OmiNotification, NotificationType } from '@/types/notification';

interface NotificationItemProps {
  notification: OmiNotification;
  onClick: () => void;
  onMarkAsRead: () => void;
  onClear: () => void;
  appImage?: string; // App image URL for plugin notifications
}

/**
 * Get icon for notification type
 */
function getNotificationIcon(type: NotificationType) {
  switch (type) {
    case 'action_item_reminder':
      return Clock;
    case 'action_item_update':
      return Edit;
    case 'action_item_delete':
      return Trash2;
    case 'daily_summary':
      return CalendarDays;
    case 'plugin':
      return Puzzle;
    case 'merge_completed':
      return GitMerge;
    case 'announcement':
      return Megaphone;
    default:
      return Bell;
  }
}

/**
 * Get icon color for notification type
 */
function getNotificationIconColor(type: NotificationType): string {
  switch (type) {
    case 'action_item_reminder':
      return 'text-orange-400';
    case 'action_item_update':
    case 'action_item_delete':
      return 'text-blue-400';
    case 'daily_summary':
      return 'text-text-secondary';
    case 'plugin':
      return 'text-green-400';
    case 'merge_completed':
      return 'text-cyan-400';
    case 'announcement':
      return 'text-yellow-400';
    default:
      return 'text-text-tertiary';
  }
}

export function NotificationItem({
  notification,
  onClick,
  onMarkAsRead,
  onClear,
  appImage,
}: NotificationItemProps) {
  const Icon = getNotificationIcon(notification.type);
  const iconColor = getNotificationIconColor(notification.type);

  // Use app image for plugin notifications if available
  const showAppImage = notification.type === 'plugin' && appImage;

  const handleClear = (e: React.MouseEvent) => {
    e.stopPropagation();
    onClear();
  };

  const handleMarkAsRead = (e: React.MouseEvent) => {
    e.stopPropagation();
    onMarkAsRead();
  };

  return (
    <div
      onClick={onClick}
      className={cn(
        'flex cursor-pointer items-start gap-3 px-4 py-3',
        'transition-colors hover:bg-bg-tertiary/50',
        'group relative',
        !notification.read && 'bg-white/[0.08]',
      )}
    >
      {/* Icon or App Image */}
      <div
        className={cn(
          'flex h-9 w-9 flex-shrink-0 items-center justify-center overflow-hidden rounded-full',
          'bg-bg-tertiary',
        )}
      >
        {showAppImage ? (
          <Image
            src={appImage}
            alt=""
            width={36}
            height={36}
            className="h-full w-full object-cover"
          />
        ) : (
          <Icon className={cn('h-4 w-4', iconColor)} />
        )}
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <p
            className={cn(
              'truncate text-sm font-medium',
              notification.read ? 'text-text-secondary' : 'text-text-primary',
            )}
          >
            {notification.title}
          </p>
          <span className="flex-shrink-0 text-xs text-text-quaternary">
            {formatNotificationTimestamp(new Date(notification.timestamp))}
          </span>
        </div>
        <p
          className={cn(
            'mt-0.5 line-clamp-2 text-sm',
            notification.read ? 'text-text-quaternary' : 'text-text-tertiary',
          )}
        >
          {notification.body}
        </p>
      </div>

      {/* Unread indicator */}
      {!notification.read && (
        <div
          className="mt-2 h-2 w-2 flex-shrink-0 rounded-full bg-text-primary"
          title="Unread"
        />
      )}

      {/* Actions (visible on hover) */}
      <div
        className={cn(
          'absolute right-2 top-1/2 -translate-y-1/2',
          'flex items-center gap-1',
          'opacity-0 transition-opacity group-hover:opacity-100',
          'rounded-lg bg-bg-secondary/90 px-1 py-1 backdrop-blur-sm',
        )}
      >
        {!notification.read && (
          <button
            onClick={handleMarkAsRead}
            className="rounded-md p-1.5 transition-colors hover:bg-bg-tertiary"
            title="Mark as read"
          >
            <Clock className="h-3.5 w-3.5 text-text-quaternary" />
          </button>
        )}
        <button
          onClick={handleClear}
          className="rounded-md p-1.5 transition-colors hover:bg-bg-tertiary"
          title="Remove"
        >
          <X className="h-3.5 w-3.5 text-text-quaternary" />
        </button>
      </div>
    </div>
  );
}
