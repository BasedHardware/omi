/**
 * Tests for the regolo-forwarder pure header-assembly logic.
 *
 * Run: node --test web/frontend/src/lib/api/__tests__/regolo-forwarder.test.mjs
 *
 * Same node:test pattern as the M4.1 + M4.5 tests. Re-implements the pure
 * mapping inline because the source uses Next.js path aliases (@/src/...)
 * that node:test can't resolve. Contract is documented at the top of
 * regolo-forwarder.ts; keep the inline copy in sync.
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

const BYOK_PROVIDERS = ['openai', 'anthropic', 'gemini', 'deepgram', 'regolo'];

const PROVIDER_HEADER = {
  openai: 'X-BYOK-OpenAI',
  anthropic: 'X-BYOK-Anthropic',
  gemini: 'X-BYOK-Gemini',
  deepgram: 'X-BYOK-Deepgram',
  regolo: 'X-BYOK-Regolo',
};

function buildHeadersFromSettings(settings, idToken, resolveByokKey, options = {}) {
  if (!idToken) throw new Error('idToken is required for backend header forwarding');

  const headers = new Headers(options.extraHeaders);
  headers.set('Authorization', `Bearer ${idToken}`);

  for (const provider of BYOK_PROVIDERS) {
    if (!settings.byok_keys[provider]) continue;
    const plaintext = resolveByokKey(provider);
    if (plaintext) headers.set(PROVIDER_HEADER[provider], plaintext);
  }

  if (settings.eu_privacy_mode) {
    headers.set('X-Privacy-Mode', 'on');
  }

  return headers;
}

const stubResolver = (keys) => (provider) => keys[provider] ?? null;

describe('buildHeadersFromSettings', () => {
  it('always sets Authorization Bearer with the id token', () => {
    const h = buildHeadersFromSettings(
      { eu_privacy_mode: false, byok_keys: {} },
      'tok-abc',
      stubResolver({}),
    );
    assert.equal(h.get('authorization'), 'Bearer tok-abc');
  });

  it('throws when idToken is empty', () => {
    assert.throws(
      () =>
        buildHeadersFromSettings({ eu_privacy_mode: false, byok_keys: {} }, '', stubResolver({})),
      /idToken is required/,
    );
  });

  it('omits Privacy Mode header when toggle is off', () => {
    const h = buildHeadersFromSettings(
      { eu_privacy_mode: false, byok_keys: {} },
      'tok-abc',
      stubResolver({}),
    );
    assert.equal(h.get('x-privacy-mode'), null);
  });

  it('sets X-Privacy-Mode: on when toggle is true', () => {
    const h = buildHeadersFromSettings(
      { eu_privacy_mode: true, byok_keys: {} },
      'tok-abc',
      stubResolver({}),
    );
    assert.equal(h.get('x-privacy-mode'), 'on');
  });

  it('forwards X-BYOK-* headers for configured providers only', () => {
    const settings = {
      eu_privacy_mode: false,
      byok_keys: {
        // Three providers configured (these would be encrypted shapes in real
        // Firestore docs; presence/absence is what drives header inclusion).
        openai: { ciphertext: 'x', iv: 'y', hash: 'z' },
        regolo: { ciphertext: 'x', iv: 'y', hash: 'z' },
        anthropic: { ciphertext: 'x', iv: 'y', hash: 'z' },
      },
    };
    const h = buildHeadersFromSettings(
      settings,
      'tok-abc',
      stubResolver({
        openai: 'sk-openai-plain',
        regolo: 'reg-plain',
        anthropic: 'ant-plain',
      }),
    );
    assert.equal(h.get('x-byok-openai'), 'sk-openai-plain');
    assert.equal(h.get('x-byok-anthropic'), 'ant-plain');
    assert.equal(h.get('x-byok-regolo'), 'reg-plain');
    // Unconfigured providers must NOT have a header.
    assert.equal(h.get('x-byok-gemini'), null);
    assert.equal(h.get('x-byok-deepgram'), null);
  });

  it('skips a configured provider whose decryption returned null', () => {
    // E.g. ciphertext is present but the pepper rotated and decryption
    // failed gracefully. Forwarder should not send a malformed empty header.
    const settings = {
      eu_privacy_mode: false,
      byok_keys: { openai: { ciphertext: 'x', iv: 'y', hash: 'z' } },
    };
    const h = buildHeadersFromSettings(
      settings,
      'tok-abc',
      stubResolver({ openai: null }),
    );
    assert.equal(h.get('x-byok-openai'), null);
    // Authorization still set.
    assert.equal(h.get('authorization'), 'Bearer tok-abc');
  });

  it('merges caller-supplied extra headers, never overwrites Authorization', () => {
    const h = buildHeadersFromSettings(
      { eu_privacy_mode: false, byok_keys: {} },
      'tok-abc',
      stubResolver({}),
      { extraHeaders: { 'Content-Type': 'application/json', Authorization: 'Bearer SHOULD-LOSE' } },
    );
    assert.equal(h.get('content-type'), 'application/json');
    // Forwarder's Authorization wins over caller's.
    assert.equal(h.get('authorization'), 'Bearer tok-abc');
  });

  it('combines BYOK forwarding + Privacy Mode + extra headers in one call', () => {
    const settings = {
      eu_privacy_mode: true,
      byok_keys: {
        regolo: { ciphertext: 'x', iv: 'y', hash: 'z' },
      },
    };
    const h = buildHeadersFromSettings(
      settings,
      'tok-abc',
      stubResolver({ regolo: 'reg-plain' }),
      { extraHeaders: { 'X-Trace-Id': 'trace-42' } },
    );
    assert.equal(h.get('authorization'), 'Bearer tok-abc');
    assert.equal(h.get('x-byok-regolo'), 'reg-plain');
    assert.equal(h.get('x-privacy-mode'), 'on');
    assert.equal(h.get('x-trace-id'), 'trace-42');
  });
});
