'use client';

import { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';
import { useNotifications, UseNotificationsReturn } from '@/hooks/useNotifications';
import { getInstalledApps, type App } from '@/lib/api';
import type { OmiNotification } from '@/types/notification';

interface NotificationContextType extends UseNotificationsReturn {
  // Panel state
  isOpen: boolean;
  openNotificationCenter: () => void;
  closeNotificationCenter: () => void;
  toggleNotificationCenter: () => void;
  // App image lookup for plugin notifications
  getAppImage: (appId: string | undefined) => string | undefined;
}

const NotificationContext = createContext<NotificationContextType | null>(null);

interface NotificationProviderProps {
  children: ReactNode;
}

export function NotificationProvider({ children }: NotificationProviderProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [installedApps, setInstalledApps] = useState<Map<string, App>>(new Map());
  const notificationHook = useNotifications();

  // Load installed apps on mount for image lookup
  useEffect(() => {
    async function loadApps() {
      try {
        const response = await getInstalledApps();
        const appsMap = new Map<string, App>();
        response.data.forEach((app) => {
          appsMap.set(app.id, app);
        });
        setInstalledApps(appsMap);
      } catch (error) {
        console.error('Failed to load installed apps for notifications:', error);
      }
    }
    loadApps();
  }, []);

  const openNotificationCenter = useCallback(() => setIsOpen(true), []);
  const closeNotificationCenter = useCallback(() => setIsOpen(false), []);
  const toggleNotificationCenter = useCallback(() => setIsOpen((prev) => !prev), []);

  // Get app image for plugin notifications
  const getAppImage = useCallback(
    (appId: string | undefined): string | undefined => {
      if (!appId) return undefined;
      const app = installedApps.get(appId);
      return app?.image || undefined;
    },
    [installedApps]
  );

  // Override navigateToNotification to also close the panel
  const navigateToNotification = useCallback(
    (notification: OmiNotification) => {
      notificationHook.navigateToNotification(notification);
      setIsOpen(false);
    },
    [notificationHook]
  );

  return (
    <NotificationContext.Provider
      value={{
        ...notificationHook,
        navigateToNotification,
        isOpen,
        openNotificationCenter,
        closeNotificationCenter,
        toggleNotificationCenter,
        getAppImage,
      }}
    >
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotificationContext() {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error('useNotificationContext must be used within a NotificationProvider');
  }
  return context;
}
