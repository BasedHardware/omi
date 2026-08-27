'use client';

import { useCallback, useEffect, useMemo, useRef } from 'react';
import { createSignal } from '@tschk/moonshine';
import { useRouter } from '@tschk/moonshine-next/navigation';
import { useSignalValue } from '@/lib/signals';
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
import { registerFCMToken, unregisterFCMToken } from '@/features/notifications/api';
import { getNotificationRoute } from '@/features/notifications/model';
import type { MessagePayload } from 'firebase/messaging';

const STORAGE_KEY = 'omi-notifications';
const MAX_NOTIFICATIONS = 100;
const FCM_TOKEN_KEY = 'omi-fcm-token';

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

function saveNotifications(notifications: OmiNotification[]): void {
  if (typeof window === 'undefined') return;

  try {
    const trimmed = notifications.slice(0, MAX_NOTIFICATIONS);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch (error) {
    console.error('Failed to save notifications:', error);
  }
}

function getStoredFCMToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(FCM_TOKEN_KEY);
}

function storeFCMToken(token: string | null): void {
  if (typeof window === 'undefined') return;

  if (token) {
    localStorage.setItem(FCM_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(FCM_TOKEN_KEY);
  }
}

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

export interface UseNotificationsReturn {
  notifications: OmiNotification[];
  unreadCount: number;
  permission: NotificationPermissionStatus;
  isSupported: boolean;
  isLoading: boolean;
  fcmToken: string | null;
  requestPermission: () => Promise<boolean>;
  markAsRead: (notificationId: string) => void;
  markAllAsRead: () => void;
  clearNotification: (notificationId: string) => void;
  clearAllNotifications: () => void;
  navigateToNotification: (notification: OmiNotification) => void;
  unregisterToken: () => Promise<void>;
  sendTestNotification: () => void;
}

export function createNotificationsStore() {
  const notifications = createSignal<OmiNotification[]>(loadNotifications());
  const permission = createSignal<NotificationPermissionStatus>('default');
  const isSupported = createSignal(false);
  const isLoading = createSignal(true);
  const fcmToken = createSignal<string | null>(null);

  const commit = (next: OmiNotification[]) => {
    const trimmed = next.slice(0, MAX_NOTIFICATIONS);
    notifications.set(trimmed);
    saveNotifications(trimmed);
  };

  const prepend = (notification: OmiNotification) => {
    commit([notification, ...notifications.peek()]);
  };

  const markAsRead = (notificationId: string) => {
    commit(
      notifications.peek().map((n) => (n.id === notificationId ? { ...n, read: true } : n)),
    );
  };

  const markAllAsRead = () => {
    commit(notifications.peek().map((n) => ({ ...n, read: true })));
  };

  const clearNotification = (notificationId: string) => {
    commit(notifications.peek().filter((n) => n.id !== notificationId));
  };

  const clearAll = () => {
    commit([]);
  };

  return {
    notifications,
    permission,
    isSupported,
    isLoading,
    fcmToken,
    prepend,
    markAsRead,
    markAllAsRead,
    clearNotification,
    clearAll,
  };
}

export function useNotifications(): UseNotificationsReturn {
  const router = useRouter();
  const store = useMemo(() => createNotificationsStore(), []);
  const unsubscribeRef = useRef<(() => void) | null>(null);

  const notifications = useSignalValue(store.notifications);
  const permission = useSignalValue(store.permission);
  const isSupported = useSignalValue(store.isSupported);
  const isLoading = useSignalValue(store.isLoading);
  const fcmToken = useSignalValue(store.fcmToken);
  const unreadCount = notifications.filter((n) => !n.read).length;

  const handleForegroundMessage = useCallback(
    (payload: MessagePayload) => {
      const notification = payloadToNotification(payload);
      store.prepend(notification);

      if (Notification.permission === 'granted') {
        const browserNotif = new Notification(notification.title, {
          body: notification.body,
          icon: '/logo.png',
          tag: notification.id,
        });

        browserNotif.onclick = () => {
          window.focus();
          router.push(getNotificationRoute(notification));
          browserNotif.close();
        };
      }
    },
    [router, store],
  );

  useEffect(() => {
    async function init() {
      store.isLoading.set(true);
      store.notifications.set(loadNotifications());

      const hasNotificationSupport =
        typeof window !== 'undefined' &&
        'Notification' in window &&
        'serviceWorker' in navigator;
      store.isSupported.set(hasNotificationSupport);

      const perm = getNotificationPermission();
      store.permission.set(perm);

      if (perm === 'granted' && hasNotificationSupport) {
        try {
          const storedToken = getStoredFCMToken();
          const token = await getCurrentFCMToken();

          if (token) {
            store.fcmToken.set(token);

            if (token !== storedToken) {
              try {
                await registerFCMToken(token);
                storeFCMToken(token);
              } catch (error) {
                console.error('Failed to register FCM token:', error);
              }
            }

            const unsubscribe = await onForegroundMessage(handleForegroundMessage);
            if (unsubscribe) {
              unsubscribeRef.current = unsubscribe;
            }
          }
        } catch (error) {
          console.error('Failed to initialize FCM:', error);
        }
      }

      store.isLoading.set(false);
    }

    void init();

    return () => {
      if (unsubscribeRef.current) {
        unsubscribeRef.current();
      }
    };
  }, [handleForegroundMessage, store]);

  const requestPermissionHandler = useCallback(async (): Promise<boolean> => {
    if (!store.isSupported.peek()) return false;

    store.isLoading.set(true);

    try {
      const token = await requestNotificationPermission();

      if (token) {
        store.fcmToken.set(token);
        storeFCMToken(token);
        store.permission.set('granted');
        await registerFCMToken(token);

        const unsubscribe = await onForegroundMessage(handleForegroundMessage);
        if (unsubscribe) {
          unsubscribeRef.current = unsubscribe;
        }

        store.isLoading.set(false);
        return true;
      }

      store.permission.set(getNotificationPermission());
      store.isLoading.set(false);
      return false;
    } catch (error) {
      console.error('Failed to request notification permission:', error);
      store.isLoading.set(false);
      return false;
    }
  }, [handleForegroundMessage, store]);

  const navigateToNotification = useCallback(
    (notification: OmiNotification) => {
      store.markAsRead(notification.id);
      router.push(getNotificationRoute(notification));
    },
    [router, store],
  );

  const unregisterToken = useCallback(async () => {
    const token = store.fcmToken.peek() || getStoredFCMToken();
    if (token) {
      await unregisterFCMToken(token);
      storeFCMToken(null);
      store.fcmToken.set(null);
    }

    if (unsubscribeRef.current) {
      unsubscribeRef.current();
      unsubscribeRef.current = null;
    }
  }, [store]);

  const sendTestNotification = useCallback(() => {
    const testNotification: OmiNotification = {
      id: `test-${Date.now()}`,
      type: 'announcement',
      title: 'Test Notification',
      body: 'This is a test notification to verify the UI is working correctly.',
      timestamp: new Date().toISOString(),
      read: false,
    };

    store.prepend(testNotification);

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
  }, [store]);

  return {
    notifications,
    unreadCount,
    permission,
    isSupported,
    isLoading,
    fcmToken,
    requestPermission: requestPermissionHandler,
    markAsRead: useCallback((id: string) => store.markAsRead(id), [store]),
    markAllAsRead: useCallback(() => store.markAllAsRead(), [store]),
    clearNotification: useCallback((id: string) => store.clearNotification(id), [store]),
    clearAllNotifications: useCallback(() => store.clearAll(), [store]),
    navigateToNotification,
    unregisterToken,
    sendTestNotification,
  };
}
