import type { OmiNotification } from '@/types/notification';

/**
 * In-app path for a notification's `navigate_to`. Recaps land on Timeline
 * (`/conversations?recap=`): `/recaps` was removed, not redirected.
 */
export function getNotificationRoute(notification: OmiNotification): string {
  const navigateTo = notification.navigate_to;

  if (!navigateTo) return '/';

  if (navigateTo.startsWith('/tasks')) {
    const taskId = navigateTo.split('/').pop();
    return taskId ? `/tasks?highlight=${taskId}` : '/tasks';
  }

  if (navigateTo.startsWith('/daily-summary')) {
    const recapId = navigateTo.split('/').pop();
    return recapId ? `/conversations?recap=${recapId}` : '/conversations';
  }

  if (navigateTo.startsWith('/recaps')) {
    const recapId = navigateTo.split('/').pop();
    return recapId ? `/conversations?recap=${recapId}` : '/conversations';
  }

  if (navigateTo.startsWith('/conversations')) {
    return navigateTo.replace('/conversations', '/conversations');
  }

  if (navigateTo.startsWith('/apps')) {
    const appId = navigateTo.split('/').pop();
    return appId ? `/apps?id=${appId}` : '/apps';
  }

  if (navigateTo.startsWith('/chat/')) {
    const appId = navigateTo.split('/').pop();
    return appId ? `/home?chatApp=${appId}` : '/home';
  }

  return navigateTo;
}
