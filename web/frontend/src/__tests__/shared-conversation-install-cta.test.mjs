import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import { getConversationSharePlatformLink } from '../lib/conversation-share-platform-link.mjs';

const pageSource = readFileSync(
  new URL('../app/memories/[id]/page.tsx', import.meta.url),
  'utf8',
);
const conversationNotFoundSource = readFileSync(
  new URL('../app/memories/[id]/not-found.tsx', import.meta.url),
  'utf8',
);
const groupNotFoundSource = readFileSync(
  new URL('../app/memories/not-found.tsx', import.meta.url),
  'utf8',
);
const ctaSource = readFileSync(
  new URL('../components/memories/shared-conversation-install-cta.tsx', import.meta.url),
  'utf8',
);
const headerSource = readFileSync(
  new URL('../components/memories/memory-header.tsx', import.meta.url),
  'utf8',
);
const summarySource = readFileSync(
  new URL('../components/memories/summary/sumary.tsx', import.meta.url),
  'utf8',
);

const CONVERSATION_ID = 'abc-123';
const PLAY_FALLBACK = encodeURIComponent(
  'https://play.google.com/store/apps/details?id=com.friend.ios',
);

describe('getConversationSharePlatformLink (behavioral)', () => {
  it('returns Android intent:// with Play Store fallback', () => {
    const href = getConversationSharePlatformLink(
      'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36',
      CONVERSATION_ID,
    );
    assert.equal(
      href,
      `intent://h.omi.me/conversations/${CONVERSATION_ID}#Intent;scheme=https;package=com.friend.ios;S.browser_fallback_url=${PLAY_FALLBACK};end`,
    );
  });

  it('returns iOS omi:// custom scheme', () => {
    const href = getConversationSharePlatformLink(
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
      CONVERSATION_ID,
    );
    assert.equal(href, `omi://h.omi.me/conversations/${CONVERSATION_ID}`);
  });

  it('returns desktop https://omi.me', () => {
    const href = getConversationSharePlatformLink(
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15',
      CONVERSATION_ID,
    );
    assert.equal(href, 'https://omi.me');
  });
});

describe('shared conversation install conversion contract', () => {
  it('exposes Open in Omi + store badges via a shared CTA component', () => {
    assert.match(ctaSource, /Open in Omi/);
    assert.match(ctaSource, /app-store-badge\.svg/);
    assert.match(ctaSource, /google-play-badge\.png/);
    assert.match(ctaSource, /getConversationSharePlatformLink/);
    assert.match(ctaSource, /conversation-share-platform-link\.mjs/);
  });

  it('wires the CTA and Shared from Omi eyebrow onto the public conversation page', () => {
    assert.match(pageSource, /SharedConversationInstallCta/);
    assert.match(pageSource, /getConversationSharePlatformLink/);
    assert.match(pageSource, /MemoryHeader/);
    assert.match(headerSource, /Shared from Omi/);
    assert.match(pageSource, /\/conversations\/\$\{params\.id\}/);
    assert.match(pageSource, /apple-itunes-app/);
    assert.match(pageSource, /google-play-app/);
  });

  it('surfaces structured overview on the Summary tab', () => {
    assert.match(summarySource, /structured\?\.overview/);
    assert.match(summarySource, /\{overview\}/);
  });

  it('scopes conversation not-found copy to memories/[id]', () => {
    assert.doesNotMatch(
      conversationNotFoundSource,
      /We are working in this feature, please come back later/,
    );
    assert.match(conversationNotFoundSource, /isn&apos;t available/);
    assert.match(conversationNotFoundSource, /SharedConversationInstallCta/);
    assert.match(conversationNotFoundSource, /private, expired, or removed/);

    assert.doesNotMatch(groupNotFoundSource, /This conversation/);
    assert.match(groupNotFoundSource, /Page not found/);
  });
});
