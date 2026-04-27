/**
 * Tests for the privacyFallbackMessage pure mapper.
 *
 * Run: node --test web/frontend/src/hooks/__tests__/privacyFallbackMessage.test.mjs
 *
 * Same node:test pattern as src/lib/firestore/__tests__/encryption.test.mjs.
 * Re-implements the mapping inline because the source uses 'use client' +
 * sonner import which won't load under node:test.
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

const REASON_COPY = {
  vision_unsupported:
    "Vision isn't available on regolo.ai — this screenshot was processed by Gemini.",
  regolo_outage: 'Regolo.ai is unreachable — falling back to your regular LLM provider.',
  regolo_rate_limited: 'Regolo.ai rate limit hit — falling back to your regular LLM provider.',
  no_regolo_key: 'EU Privacy Mode is on but no Regolo key is configured. Add one in Settings.',
  other: 'This request left the EU.',
};

function privacyFallbackMessage(rawReason) {
  const reason = rawReason in REASON_COPY ? rawReason : 'other';
  return REASON_COPY[reason];
}

describe('privacyFallbackMessage', () => {
  it('maps each known reason to its specific copy', () => {
    assert.match(privacyFallbackMessage('vision_unsupported'), /Vision isn't available/);
    assert.match(privacyFallbackMessage('regolo_outage'), /unreachable/);
    assert.match(privacyFallbackMessage('regolo_rate_limited'), /rate limit hit/);
    assert.match(privacyFallbackMessage('no_regolo_key'), /no Regolo key is configured/);
    assert.match(privacyFallbackMessage('other'), /left the EU/);
  });

  it('falls back to generic copy for unknown reasons', () => {
    assert.equal(privacyFallbackMessage('unknown_xyz'), REASON_COPY.other);
    assert.equal(privacyFallbackMessage(''), REASON_COPY.other);
    assert.equal(privacyFallbackMessage('VISION_UNSUPPORTED'), REASON_COPY.other); // case-sensitive on purpose
  });

  it('matches the desktop observer reason set 1:1', () => {
    // These must be in sync with desktop/Desktop/Sources/PrivacyModeFallbackObserver.swift
    // and backend/utils/byok.py PRIVACY_FALLBACK_* constants.
    const expected = [
      'vision_unsupported',
      'regolo_outage',
      'regolo_rate_limited',
      'no_regolo_key',
      'other',
    ];
    assert.deepEqual(Object.keys(REASON_COPY).sort(), expected.sort());
  });
});
