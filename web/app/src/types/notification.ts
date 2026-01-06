/**
 * Notification types matching the mobile app
 */
export type NotificationType =
  | 'action_item_reminder'
  | 'action_item_update'
  | 'action_item_delete'
  | 'merge_completed'
  | 'plugin'
  | 'daily_summary'
  | 'announcement';

/**
 * A notification stored in the notification center
 */
export interface OmiNotification {
  id: string;
  type: NotificationType;
  title: string;
  body: string;
  timestamp: string; // ISO date string
  read: boolean;
  navigate_to?: string; // Deep link path
  data?: Record<string, unknown>;
  appImage?: string; // App image URL for plugin notifications
}

/**
 * FCM message payload structure
 */
export interface NotificationPayload {
  notification?: {
    title: string;
    body: string;
    icon?: string;
  };
  data?: {
    notification_type?: NotificationType;
    notification_id?: string;
    navigate_to?: string;
    title?: string;
    body?: string;
    [key: string]: unknown;
  };
}

/**
 * Notification permission status
 */
export type NotificationPermissionStatus =
  | 'default' // User hasn't been asked yet
  | 'granted' // User allowed notifications
  | 'denied' // User blocked notifications
  | 'unsupported'; // Browser doesn't support notifications

/**
 * Notification settings state
 */
export interface NotificationSettings {
  enabled: boolean;
  permission: NotificationPermissionStatus;
  fcmToken: string | null;
}
