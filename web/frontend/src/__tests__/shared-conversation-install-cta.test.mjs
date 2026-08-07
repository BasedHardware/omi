import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

const pageSource = readFileSync(
  new URL('../app/memories/[id]/page.tsx', import.meta.url),
  'utf8',
);
const notFoundSource = readFileSync(
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

describe('shared conversation install conversion contract', () => {
  it('exposes Open in Omi + store badges via a shared CTA component', () => {
    assert.match(ctaSource, /Open in Omi/);
    assert.match(ctaSource, /app-store-badge\.svg/);
    assert.match(ctaSource, /google-play-badge\.png/);
    assert.match(ctaSource, /getConversationSharePlatformLink/);
    assert.match(ctaSource, /omi:\/\/h\.omi\.me\/conversations\//);
    assert.match(ctaSource, /intent:\/\/h\.omi\.me\/conversations\//);
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

  it('renders structured overview on the Summary tab', () => {
    assert.match(summarySource, /structured\?\.overview/);
    assert.match(summarySource, /overview/);
  });

  it('replaces the misleading not-found copy with install CTAs', () => {
    assert.doesNotMatch(
      notFoundSource,
      /We are working in this feature, please come back later/,
    );
    assert.match(
      notFoundSource,
      /isn&apos;t available|isn't available|isn\\'t available/,
    );
    assert.match(notFoundSource, /SharedConversationInstallCta/);
    assert.match(notFoundSource, /private, expired, or removed/);
  });
});
