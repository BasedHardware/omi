import { describe, expect, it } from 'vitest';
import { getNotificationRoute } from '@/features/notifications/model';
import type { OmiNotification } from '@/types/notification';

function notification(navigate_to?: string): OmiNotification {
  return {
    id: 'n1',
    type: 'announcement',
    title: 't',
    body: 'b',
    timestamp: '2026-01-01T00:00:00Z',
    read: false,
    navigate_to,
  };
}

describe('getNotificationRoute', () => {
  it('sends recaps to the conversations timeline', () => {
    expect(getNotificationRoute(notification('/daily-summary/r1'))).toBe(
      '/conversations?recap=r1',
    );
    expect(getNotificationRoute(notification('/recaps/r2'))).toBe(
      '/conversations?recap=r2',
    );
  });

  it('opens chat capability notifications on home', () => {
    expect(getNotificationRoute(notification('/chat/app-9'))).toBe('/home?chatApp=app-9');
  });

  it('falls back to home when there is no target', () => {
    expect(getNotificationRoute(notification())).toBe('/');
  });
});
