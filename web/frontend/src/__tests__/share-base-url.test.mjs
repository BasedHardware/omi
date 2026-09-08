import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { DEFAULT_SHARE_BASE_URL, shareBaseUrl, shareHost } from '../lib/share-base-url.mjs';
import { getOmiPlatformDeepLink } from '../lib/conversation-share-platform-link.mjs';

describe('shareBaseUrl (#4339)', () => {
  it('defaults to production h.omi.me', () => {
    assert.equal(shareBaseUrl(''), DEFAULT_SHARE_BASE_URL);
    assert.equal(shareBaseUrl(undefined), DEFAULT_SHARE_BASE_URL);
  });

  it('honors overrides and strips trailing slash', () => {
    assert.equal(shareBaseUrl('https://share.example.com/'), 'https://share.example.com');
    assert.equal(shareBaseUrl('share.example.com'), 'https://share.example.com');
    assert.equal(shareBaseUrl('https://share.example.com/omi/'), 'https://share.example.com/omi');
  });

  it('rejects query, fragment, and userinfo', () => {
    assert.equal(shareBaseUrl('https://share.example.com?x=1'), DEFAULT_SHARE_BASE_URL);
    assert.equal(shareBaseUrl('https://share.example.com#frag'), DEFAULT_SHARE_BASE_URL);
    assert.equal(shareBaseUrl('https://user:pass@share.example.com'), DEFAULT_SHARE_BASE_URL);
  });

  it('exposes hostname for deep links', () => {
    assert.equal(shareHost('https://share.example.com/omi/'), 'share.example.com');
  });
});

describe('getOmiPlatformDeepLink share host override', () => {
  it('uses a custom host when provided', () => {
    const href = getOmiPlatformDeepLink(
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
      'chat/tok',
      { shareHost: 'share.example.com' },
    );
    assert.equal(href, 'omi://share.example.com/chat/tok');
  });
});
