'use client';

import Image from 'next/image';
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
      return 'text-purple-400';
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
        'flex items-start gap-3 px-4 py-3 cursor-pointer',
        'hover:bg-bg-tertiary/50 transition-colors',
        'group relative',
        !notification.read && 'bg-purple-primary/5'
      )}
    >
      {/* Icon or App Image */}
      <div
        className={cn(
          'w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 overflow-hidden',
          'bg-bg-tertiary'
        )}
      >
        {showAppImage ? (
          <Image
            src={appImage}
            alt=""
            width={36}
            height={36}
            className="w-full h-full object-cover"
          />
        ) : (
          <Icon className={cn('w-4 h-4', iconColor)} />
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <p
            className={cn(
              'text-sm font-medium truncate',
              notification.read ? 'text-text-secondary' : 'text-text-primary'
            )}
          >
            {notification.title}
          </p>
          <span className="text-xs text-text-quaternary flex-shrink-0">
            {formatNotificationTimestamp(new Date(notification.timestamp))}
          </span>
        </div>
        <p
          className={cn(
            'text-sm mt-0.5 line-clamp-2',
            notification.read ? 'text-text-quaternary' : 'text-text-tertiary'
          )}
        >
          {notification.body}
        </p>
      </div>

      {/* Unread indicator */}
      {!notification.read && (
        <div
          className="w-2 h-2 rounded-full bg-purple-primary flex-shrink-0 mt-2"
          title="Unread"
        />
      )}

      {/* Actions (visible on hover) */}
      <div
        className={cn(
          'absolute right-2 top-1/2 -translate-y-1/2',
          'flex items-center gap-1',
          'opacity-0 group-hover:opacity-100 transition-opacity',
          'bg-bg-secondary/90 backdrop-blur-sm rounded-lg px-1 py-1'
        )}
      >
        {!notification.read && (
          <button
            onClick={handleMarkAsRead}
            className="p-1.5 rounded-md hover:bg-bg-tertiary transition-colors"
            title="Mark as read"
          >
            <Clock className="w-3.5 h-3.5 text-text-quaternary" />
          </button>
        )}
        <button
          onClick={handleClear}
          className="p-1.5 rounded-md hover:bg-bg-tertiary transition-colors"
          title="Remove"
        >
          <X className="w-3.5 h-3.5 text-text-quaternary" />
        </button>
      </div>
    </div>
  );
}
