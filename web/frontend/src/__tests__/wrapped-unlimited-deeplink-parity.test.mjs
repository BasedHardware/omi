import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import {
  getConversationSharePlatformLink,
  getOmiPlatformDeepLink,
} from '../lib/conversation-share-platform-link.mjs';

const PLAY_FALLBACK = encodeURIComponent(
  'https://play.google.com/store/apps/details?id=com.friend.ios',
);
const wrappedSource = readFileSync(new URL('../app/wrapped/page.tsx', import.meta.url), 'utf8');
const unlimitedSource = readFileSync(
  new URL('../app/unlimited/page.tsx', import.meta.url),
  'utf8',
);
const manifestSource = readFileSync(
  new URL('../../../../app/android/app/src/main/AndroidManifest.xml', import.meta.url),
  'utf8',
);

describe('getOmiPlatformDeepLink (behavioral)', () => {
  it('returns Android intent:// with Play Store fallback for marketing paths', () => {
    const href = getOmiPlatformDeepLink(
      'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36',
      'unlimited',
    );
    assert.equal(
      href,
      `intent://h.omi.me/unlimited#Intent;scheme=https;package=com.friend.ios;S.browser_fallback_url=${PLAY_FALLBACK};end`,
    );
  });

  it('returns iOS omi:// custom scheme for wrapped', () => {
    const href = getOmiPlatformDeepLink(
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
      'wrapped',
    );
    assert.equal(href, 'omi://h.omi.me/wrapped');
  });

  it('returns desktop https://omi.me', () => {
    const href = getOmiPlatformDeepLink(
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15',
      'unlimited',
    );
    assert.equal(href, 'https://omi.me');
  });

  it('keeps conversation share links on the shared helper', () => {
    const href = getConversationSharePlatformLink(
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
      'abc-123',
    );
    assert.equal(href, 'omi://h.omi.me/conversations/abc-123');
  });
});

describe('wrapped / unlimited acquisition parity contract', () => {
  it('wires Open in Omi through getOmiPlatformDeepLink on /wrapped', () => {
    assert.match(wrappedSource, /getOmiPlatformDeepLink/);
    assert.match(wrappedSource, /Open in Omi/);
    assert.match(wrappedSource, /['"]wrapped['"]/);
    assert.match(wrappedSource, /apple-itunes-app/);
    assert.doesNotMatch(wrappedSource, /Get the Omi App/);
  });

  it('uses platform deep-links on /unlimited instead of iOS-only omi://', () => {
    assert.match(unlimitedSource, /getOmiPlatformDeepLink/);
    assert.match(unlimitedSource, /['"]unlimited['"]/);
    assert.match(unlimitedSource, /apple-itunes-app/);
    assert.doesNotMatch(unlimitedSource, /omi:\/\/h\.omi\.me\/unlimited/);
  });

  it('routes chat and tasks Open-in-Omi through the shared deep-link helper', () => {
    const chatSource = readFileSync(new URL('../app/chat/[token]/page.tsx', import.meta.url), 'utf8');
    const tasksSource = readFileSync(
      new URL('../app/tasks/[token]/page.tsx', import.meta.url),
      'utf8',
    );
    assert.match(chatSource, /getOmiPlatformDeepLink/);
    assert.match(tasksSource, /getOmiPlatformDeepLink/);
    assert.doesNotMatch(chatSource, /intent:\/\/h\.omi\.me\/chat/);
    assert.doesNotMatch(tasksSource, /omi:\/\/h\.omi\.me\/tasks/);
  });

  it('registers Android App Link for /wrapped', () => {
    assert.match(manifestSource, /android:path="\/wrapped"/);
    assert.match(manifestSource, /android:path="\/unlimited"/);
  });
});
