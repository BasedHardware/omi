import assert from 'node:assert/strict';
import test from 'node:test';
import {
  ctaTarget,
  deviceClass,
  shareId,
  shareSource,
  shareSurface,
} from '../lib/share-analytics.mjs';

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
  assert.equal(ctaTarget('https://example.com/private'), null);
});
