import assert from 'node:assert/strict';
import test from 'node:test';
import {
  attributedCtaHref,
  chatActionProperties,
  ctaTarget,
  deviceClass,
  shareId,
  shareSource,
  shareSurface,
} from '../lib/share-analytics.mjs';

test('shared-chat actions keep only bounded fields', () => {
  assert.deepEqual(
    chatActionProperties({ type: 'question_asked', text: 'private question' }),
    {
      action: 'question_asked',
    },
  );
  assert.deepEqual(
    chatActionProperties({
      type: 'limit_card_shown',
      reason: 'free_questions_exhausted',
    }),
    {
      action: 'limit_card_shown',
      reason: 'free_questions_exhausted',
    },
  );
  assert.deepEqual(
    chatActionProperties({
      type: 'upsell_clicked',
      target: 'pendant',
      transcript: 'private',
    }),
    {
      action: 'upsell_clicked',
      target: 'pendant',
    },
  );
  assert.equal(
    chatActionProperties({ type: 'limit_card_shown', reason: 'private string' }),
    null,
  );
  assert.equal(
    chatActionProperties({ type: 'question_failed', text: 'private question' }),
    null,
  );
});

test('only public share paths produce a bounded surface', () => {
  assert.equal(shareSurface('/conversations/abc'), 'conversation');
  assert.equal(shareSurface('/memories/abc'), 'conversation');
  assert.equal(shareSurface('/chat/token'), 'chat');
  assert.equal(shareSurface('/tasks/token'), 'tasks');
  assert.equal(shareSurface('/recaps/id'), 'recap');
  assert.equal(shareSurface('/apps/id'), 'app');
  assert.equal(shareSurface('/wrapped'), 'wrapped');
  assert.equal(shareSurface('/unlimited'), 'unlimited');
  assert.equal(shareSurface('/apps'), null);
});

test('attribution fields are allowlisted', () => {
  assert.equal(shareSource('ios'), 'ios');
  assert.equal(shareSource('sender@email.test'), 'unknown');
  assert.equal(shareId('abc12345_X'), 'abc12345_X');
  assert.equal(shareId('email@example.com'), undefined);
  assert.equal(deviceClass('WhatsApp/2.0'), 'bot');
  assert.equal(deviceClass('Mozilla iPhone'), 'mobile');
});

test('CTA destination is a fixed category, never a raw URL', () => {
  assert.equal(ctaTarget('https://apps.apple.com/us/app/id123'), 'app_store');
  assert.equal(
    ctaTarget('https://play.google.com/store/apps/details?id=x'),
    'play_store',
  );
  assert.equal(ctaTarget('omi://h.omi.me/conversations/abc'), 'open_in_omi');
  assert.equal(ctaTarget('https://omi.me/download/mac'), 'mac');
  assert.equal(ctaTarget('https://omi.me/products/omi'), 'pendant');
  assert.equal(ctaTarget('https://example.com/private'), null);
});

test('store and marketing clicks carry bounded acquisition attribution', () => {
  const appStore = new URL(
    attributedCtaHref(
      'https://apps.apple.com/us/app/id123',
      'conversation',
      'ios',
      'sid12345',
    ),
  );
  assert.equal(appStore.searchParams.get('ct'), 'share_conversation');
  assert.equal(appStore.searchParams.has('pt'), false);

  const play = new URL(
    attributedCtaHref(
      'https://play.google.com/store/apps/details?id=com.friend.ios',
      'tasks',
      'android',
      'sid12345',
    ),
  );
  assert.deepEqual(
    Object.fromEntries(new URLSearchParams(play.searchParams.get('referrer'))),
    {
      utm_source: 'android',
      utm_medium: 'share',
      utm_campaign: 'share_tasks',
      sid: 'sid12345',
    },
  );

  const website = new URL(
    attributedCtaHref('https://omi.me', 'wrapped', 'mac', 'sid12345'),
  );
  assert.equal(website.searchParams.get('utm_campaign'), 'share_wrapped');
  assert.equal(website.searchParams.get('utm_content'), 'sid12345');
});

test('Android open-in-app keeps its store fallback attributable', () => {
  const intent =
    'intent://h.omi.me/conversations/abc#Intent;scheme=https;package=com.friend.ios;S.browser_fallback_url=https%3A%2F%2Fplay.google.com%2Fstore%2Fapps%2Fdetails%3Fid%3Dcom.friend.ios;end';
  const tagged = attributedCtaHref(intent, 'conversation', 'android', 'sid12345');
  const encoded = tagged.match(/S\.browser_fallback_url=([^;]+)/)?.[1];
  const fallback = new URL(decodeURIComponent(encoded));
  assert.equal(
    new URLSearchParams(fallback.searchParams.get('referrer')).get('utm_campaign'),
    'share_conversation',
  );
  assert.equal(
    attributedCtaHref('omi://h.omi.me/conversations/abc', 'conversation', 'ios'),
    'omi://h.omi.me/conversations/abc',
  );
});
