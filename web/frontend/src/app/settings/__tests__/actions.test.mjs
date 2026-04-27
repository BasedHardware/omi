/**
 * Tests for the BYOK validation request shape per provider.
 *
 * Run: node --test web/frontend/src/app/settings/__tests__/actions.test.mjs
 *
 * Same node:test pattern as the other web frontend tests. Re-implements
 * the per-provider header / URL logic inline because the source file is
 * a 'use server' module that imports Firestore — too heavy to load under
 * node:test. Contract is the testBYOKConnection function in actions.ts;
 * keep the inline mapping in sync if endpoints or auth shapes change.
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

const PROVIDER_VALIDATION_ENDPOINT = {
  openai: 'https://api.openai.com/v1/models',
  anthropic: 'https://api.anthropic.com/v1/models',
  gemini: 'https://generativelanguage.googleapis.com/v1beta/models',
  deepgram: 'https://api.deepgram.com/v1/projects',
  regolo: 'https://api.regolo.ai/v1/models',
};

function buildValidationRequest(provider, plaintextKey) {
  if (!plaintextKey || !plaintextKey.trim()) {
    return { ok: false, error: 'Key is empty' };
  }
  const endpoint = PROVIDER_VALIDATION_ENDPOINT[provider];
  if (!endpoint) return { ok: false, error: `No validation endpoint for ${provider}` };

  const trimmed = plaintextKey.trim();
  const init = { method: 'GET', cache: 'no-store' };
  let url = endpoint;

  if (provider === 'anthropic') {
    init.headers = { 'x-api-key': trimmed, 'anthropic-version': '2023-06-01' };
  } else if (provider === 'gemini') {
    url = `${endpoint}?key=${encodeURIComponent(trimmed)}`;
  } else if (provider === 'deepgram') {
    init.headers = { Authorization: `Token ${trimmed}` };
  } else {
    init.headers = { Authorization: `Bearer ${trimmed}` };
  }
  return { url, init };
}

describe('testBYOKConnection request shape', () => {
  it('rejects empty / whitespace-only keys before any HTTP call', () => {
    assert.deepEqual(buildValidationRequest('openai', ''), { ok: false, error: 'Key is empty' });
    assert.deepEqual(buildValidationRequest('openai', '   '), { ok: false, error: 'Key is empty' });
  });

  it('OpenAI uses Bearer auth on /v1/models', () => {
    const r = buildValidationRequest('openai', 'sk-test-abc');
    assert.equal(r.url, 'https://api.openai.com/v1/models');
    assert.equal(r.init.headers.Authorization, 'Bearer sk-test-abc');
  });

  it('Regolo uses Bearer auth on its /v1/models', () => {
    const r = buildValidationRequest('regolo', 'reg-test-xyz');
    assert.equal(r.url, 'https://api.regolo.ai/v1/models');
    assert.equal(r.init.headers.Authorization, 'Bearer reg-test-xyz');
  });

  it('Anthropic uses x-api-key + anthropic-version header (NOT Bearer)', () => {
    const r = buildValidationRequest('anthropic', 'ant-test');
    assert.equal(r.url, 'https://api.anthropic.com/v1/models');
    assert.equal(r.init.headers['x-api-key'], 'ant-test');
    assert.equal(r.init.headers['anthropic-version'], '2023-06-01');
    assert.equal(r.init.headers.Authorization, undefined);
  });

  it('Gemini uses query-string key (key=...) NOT a header', () => {
    const r = buildValidationRequest('gemini', 'gem-test+special chars');
    assert.match(r.url, /^https:\/\/generativelanguage\.googleapis\.com\/v1beta\/models\?key=/);
    assert.match(r.url, /gem-test%2Bspecial%20chars/);
    assert.equal(r.init.headers, undefined);
  });

  it('Deepgram uses Token auth scheme (NOT Bearer)', () => {
    const r = buildValidationRequest('deepgram', 'dg-test');
    assert.equal(r.url, 'https://api.deepgram.com/v1/projects');
    assert.equal(r.init.headers.Authorization, 'Token dg-test');
  });

  it('trims surrounding whitespace before sending', () => {
    const r = buildValidationRequest('openai', '  sk-test-abc  ');
    assert.equal(r.init.headers.Authorization, 'Bearer sk-test-abc');
  });

  it('rejects unknown provider', () => {
    const r = buildValidationRequest('not-a-provider', 'k');
    assert.equal(r.ok, false);
    assert.match(r.error, /No validation endpoint/);
  });
});
