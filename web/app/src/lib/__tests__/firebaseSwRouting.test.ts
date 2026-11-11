import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * The background half of notification routing.
 *
 * A recap notification clicked while the app is backgrounded is handled by the
 * service worker, not by `useNotifications`. `/recaps` was removed and not
 * redirected, so a worker still pointing there lands the click on a 404 even
 * though the in-app mapping is correct.
 */

const templatePath = path.join(
  import.meta.dirname,
  '..',
  '..',
  '..',
  'public',
  'firebase-messaging-sw.js.template',
);

type ClickHandler = (event: {
  notification: { data: Record<string, string>; close: () => void };
  waitUntil: (value: unknown) => void;
}) => void;

const ORIGIN = 'https://app.omi.me';

function notificationClickHandler(): { run: ClickHandler; openedUrls: string[] } {
  const listeners = new Map<string, ClickHandler>();
  const openedUrls: string[] = [];

  const self = {
    location: { origin: ORIGIN },
    registration: { showNotification: () => {} },
    skipWaiting: () => {},
    addEventListener: (type: string, handler: ClickHandler) =>
      listeners.set(type, handler),
  };
  const clients = {
    matchAll: async () => [],
    openWindow: async (url: string) => {
      openedUrls.push(url);
    },
    claim: async () => {},
  };
  const firebase = {
    initializeApp: () => {},
    messaging: () => ({ onBackgroundMessage: () => {} }),
  };

  const source = readFileSync(templatePath, 'utf8');
  new Function('self', 'clients', 'firebase', 'importScripts', 'console', source)(
    self,
    clients,
    firebase,
    () => {},
    { log: () => {} },
  );

  const handler = listeners.get('notificationclick');
  if (!handler) throw new Error('service worker registered no notificationclick');
  return { run: handler, openedUrls };
}

async function clickTarget(navigateTo: string): Promise<string> {
  const { run, openedUrls } = notificationClickHandler();
  const waited: unknown[] = [];
  run({
    notification: { data: { navigate_to: navigateTo }, close: () => {} },
    waitUntil: (value) => waited.push(value),
  });
  await Promise.all(waited);
  return openedUrls[0] ?? '';
}

describe('firebase messaging service worker routing', () => {
  it('opens a backgrounded recap notification on the timeline', async () => {
    expect(await clickTarget('/daily-summary/recap-7')).toBe(
      `${ORIGIN}/conversations?recap=recap-7`,
    );
  });

  it('opens the legacy /recaps payload on the timeline too', async () => {
    expect(await clickTarget('/recaps/recap-7')).toBe(
      `${ORIGIN}/conversations?recap=recap-7`,
    );
  });
});
