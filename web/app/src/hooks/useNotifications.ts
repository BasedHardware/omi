'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import type {
  OmiNotification,
  NotificationType,
  NotificationPermissionStatus,
} from '@/types/notification';
import {
  requestNotificationPermission,
  getCurrentFCMToken,
  onForegroundMessage,
  getNotificationPermission,
} from '@/lib/firebase';
import { registerFCMToken, unregisterFCMToken } from '@/lib/api';
import type { MessagePayload } from 'firebase/messaging';

// Constants
const STORAGE_KEY = 'omi-notifications';
const MAX_NOTIFICATIONS = 100;
const FCM_TOKEN_KEY = 'omi-fcm-token';

/**
 * Load notifications from localStorage
 */
function loadNotifications(): OmiNotification[] {
  if (typeof window === 'undefined') return [];

  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return [];
    return JSON.parse(stored);
  } catch {
    return [];
  }
}

/**
 * Save notifications to localStorage
 */
function saveNotifications(notifications: OmiNotification[]): void {
  if (typeof window === 'undefined') return;

  try {
    // Limit to max notifications
    const trimmed = notifications.slice(0, MAX_NOTIFICATIONS);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch (error) {
    console.error('Failed to save notifications:', error);
  }
}

/**
 * Get stored FCM token
 */
function getStoredFCMToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(FCM_TOKEN_KEY);
}

/**
 * Store FCM token
 */
function storeFCMToken(token: string | null): void {
  if (typeof window === 'undefined') return;

  if (token) {
    localStorage.setItem(FCM_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(FCM_TOKEN_KEY);
  }
}

/**
 * Convert FCM payload to OmiNotification
 */
function payloadToNotification(payload: MessagePayload): OmiNotification {
  const data = payload.data || {};
  const notification = payload.notification || {};

  return {
    id: data.notification_id || `notif-${Date.now()}`,
    type: (data.notification_type as NotificationType) || 'announcement',
    title: notification.title || data.title || 'Omi',
    body: notification.body || data.body || '',
    timestamp: new Date().toISOString(),
    read: false,
    navigate_to: data.navigate_to,
    data,
  };
}

/**
 * Get the route for a notification based on its type and navigate_to value
 */
function getNotificationRoute(notification: OmiNotification): string {
  const navigateTo = notification.navigate_to;

  if (!navigateTo) return '/';

  // Handle different notification types and their routes
  if (navigateTo.startsWith('/tasks')) {
    const taskId = navigateTo.split('/').pop();
    return taskId ? `/tasks?highlight=${taskId}` : '/tasks';
  }

  if (navigateTo.startsWith('/daily-summary')) {
    const recapId = navigateTo.split('/').pop();
    return recapId ? `/recaps?id=${recapId}` : '/recaps';
  }

  if (navigateTo.startsWith('/recaps')) {
    const recapId = navigateTo.split('/').pop();
    return recapId ? `/recaps?id=${recapId}` : '/recaps';
  }

  if (navigateTo.startsWith('/conversations')) {
    return navigateTo;
  }

  if (navigateTo.startsWith('/apps')) {
    const appId = navigateTo.split('/').pop();
    return appId ? `/apps?id=${appId}` : '/apps';
  }

  // Handle /chat/{app_id} routes - use query param for capability-aware routing
  // MainLayout's ChatAppRouter will check if app has chat capability:
  // - If yes: open chat panel with that app
  // - If no: open notification center (notification-only apps like Bitcoin)
  if (navigateTo.startsWith('/chat/')) {
    const appId = navigateTo.split('/').pop();
    return appId ? `/?chatApp=${appId}` : '/';
  }

  return navigateTo;
}

export interface UseNotificationsReturn {
  // State
  notifications: OmiNotification[];
  unreadCount: number;
  permission: NotificationPermissionStatus;
  isSupported: boolean;
  isLoading: boolean;
  fcmToken: string | null;

  // Actions
  requestPermission: () => Promise<boolean>;
  markAsRead: (notificationId: string) => void;
  markAllAsRead: () => void;
  clearNotification: (notificationId: string) => void;
  clearAllNotifications: () => void;

  // Navigation
  navigateToNotification: (notification: OmiNotification) => void;

  // Cleanup
  unregisterToken: () => Promise<void>;

  // Debug - send a test notification to verify UI works
  sendTestNotification: () => void;
}

/**
 * Hook for managing notifications
 */
export function useNotifications(): UseNotificationsReturn {
  const router = useRouter();
  const [notifications, setNotifications] = useState<OmiNotification[]>([]);
  const [permission, setPermission] = useState<NotificationPermissionStatus>('default');
  const [isSupported, setIsSupported] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [fcmToken, setFcmToken] = useState<string | null>(null);
  const unsubscribeRef = useRef<(() => void) | null>(null);

  // Calculate unread count
  const unreadCount = notifications.filter((n) => !n.read).length;

  // Handle foreground message (defined before useEffect that uses it)
  const handleForegroundMessage = useCallback((payload: MessagePayload) => {
    console.log('Foreground message received:', payload);

    const notification = payloadToNotification(payload);

    setNotifications((prev) => {
      const updated = [notification, ...prev].slice(0, MAX_NOTIFICATIONS);
      saveNotifications(updated);
      return updated;
    });

    // Show browser notification for foreground messages
    if (Notification.permission === 'granted') {
      const browserNotif = new Notification(notification.title, {
        body: notification.body,
        icon: '/logo.png',
        tag: notification.id,
      });

      browserNotif.onclick = () => {
        window.focus();
        const route = getNotificationRoute(notification);
        router.push(route);
        browserNotif.close();
      };
    }
  }, [router]);

  // Initialize on mount
  useEffect(() => {
    async function init() {
      setIsLoading(true);

      // Load stored notifications
      const stored = loadNotifications();
      setNotifications(stored);

      // Check basic browser support (without triggering Firebase initialization)
      const hasNotificationSupport = typeof window !== 'undefined'
        && 'Notification' in window
        && 'serviceWorker' in navigator;
      setIsSupported(hasNotificationSupport);

      // Get current permission status
      const perm = getNotificationPermission();
      setPermission(perm);

      // Only try to get token if permission already granted
      // This will initialize the service worker and messaging
      if (perm === 'granted' && hasNotificationSupport) {
        try {
          // Get stored token BEFORE getting new one to compare
          const storedToken = getStoredFCMToken();
          const token = await getCurrentFCMToken();

          if (token) {
            setFcmToken(token);

            // Register with backend if token changed or first time
            if (token !== storedToken) {
              try {
                console.log('Registering FCM token with backend...');
                await registerFCMToken(token);
                storeFCMToken(token);
                console.log('FCM token registered successfully');
              } catch (error) {
                console.error('Failed to register FCM token:', error);
              }
            } else {
              console.log('FCM token unchanged, skipping registration');
            }

            // Subscribe to foreground messages
            const unsubscribe = await onForegroundMessage(handleForegroundMessage);
            if (unsubscribe) {
              unsubscribeRef.current = unsubscribe;
            }
          }
        } catch (error) {
          console.error('Failed to initialize FCM:', error);
        }
      }

      setIsLoading(false);
    }

    init();

    return () => {
      if (unsubscribeRef.current) {
        unsubscribeRef.current();
      }
    };
  }, [handleForegroundMessage]);

  // Request notification permission
  const requestPermissionHandler = useCallback(async (): Promise<boolean> => {
    if (!isSupported) return false;

    setIsLoading(true);

    try {
      const token = await requestNotificationPermission();

      if (token) {
        setFcmToken(token);
        storeFCMToken(token);
        setPermission('granted');

        // Register token with backend
        console.log('Registering new FCM token with backend...');
        await registerFCMToken(token);
        console.log('FCM token registered successfully');

        // Subscribe to foreground messages
        const unsubscribe = await onForegroundMessage(handleForegroundMessage);
        if (unsubscribe) {
          unsubscribeRef.current = unsubscribe;
        }

        setIsLoading(false);
        return true;
      } else {
        // Permission was denied
        setPermission(getNotificationPermission());
        setIsLoading(false);
        return false;
      }
    } catch (error) {
      console.error('Failed to request notification permission:', error);
      setIsLoading(false);
      return false;
    }
  }, [isSupported, handleForegroundMessage]);

  // Mark notification as read
  const markAsRead = useCallback((notificationId: string) => {
    setNotifications((prev) => {
      const updated = prev.map((n) =>
        n.id === notificationId ? { ...n, read: true } : n
      );
      saveNotifications(updated);
      return updated;
    });
  }, []);

  // Mark all as read
  const markAllAsRead = useCallback(() => {
    setNotifications((prev) => {
      const updated = prev.map((n) => ({ ...n, read: true }));
      saveNotifications(updated);
      return updated;
    });
  }, []);

  // Clear a notification
  const clearNotification = useCallback((notificationId: string) => {
    setNotifications((prev) => {
      const updated = prev.filter((n) => n.id !== notificationId);
      saveNotifications(updated);
      return updated;
    });
  }, []);

  // Clear all notifications
  const clearAllNotifications = useCallback(() => {
    setNotifications([]);
    saveNotifications([]);
  }, []);

  // Navigate to notification
  const navigateToNotification = useCallback(
    (notification: OmiNotification) => {
      markAsRead(notification.id);
      const route = getNotificationRoute(notification);
      router.push(route);
    },
    [router, markAsRead]
  );

  // Unregister token (for logout)
  const unregisterToken = useCallback(async () => {
    const token = fcmToken || getStoredFCMToken();
    if (token) {
      await unregisterFCMToken(token);
      storeFCMToken(null);
      setFcmToken(null);
    }

    if (unsubscribeRef.current) {
      unsubscribeRef.current();
      unsubscribeRef.current = null;
    }
  }, [fcmToken]);

  // Send a test notification (for debugging)
  const sendTestNotification = useCallback(() => {
    const testNotification: OmiNotification = {
      id: `test-${Date.now()}`,
      type: 'announcement',
      title: 'Test Notification',
      body: 'This is a test notification to verify the UI is working correctly.',
      timestamp: new Date().toISOString(),
      read: false,
    };

    setNotifications((prev) => {
      const updated = [testNotification, ...prev].slice(0, MAX_NOTIFICATIONS);
      saveNotifications(updated);
      return updated;
    });

    // Also show a browser notification
    if (Notification.permission === 'granted') {
      const browserNotif = new Notification(testNotification.title, {
        body: testNotification.body,
        icon: '/logo.png',
        tag: testNotification.id,
      });

      browserNotif.onclick = () => {
        window.focus();
        browserNotif.close();
      };
    }

    console.log('Test notification sent:', testNotification);
  }, []);

  return {
    notifications,
    unreadCount,
    permission,
    isSupported,
    isLoading,
    fcmToken,
    requestPermission: requestPermissionHandler,
    markAsRead,
    markAllAsRead,
    clearNotification,
    clearAllNotifications,
    navigateToNotification,
    unregisterToken,
    sendTestNotification,
  };
}
