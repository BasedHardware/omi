/**
 * Tests for BYOK encryption-at-rest.
 *
 * Run: node --test web/frontend/src/lib/firestore/__tests__/encryption.test.mjs
 *
 * Uses Node.js built-in test runner (node:test) — same as
 * src/__tests__/case-status.test.mjs. No additional deps.
 *
 * The encryption module imports from `@/src/constants/envConfig` which
 * uses Next.js path aliases — node:test can't resolve those, so we
 * re-implement the same logic inline against the documented behavior. If
 * the module surface changes, regenerate this test file from the contract
 * in encryption.ts.
 *
 * All cryptography here is webcrypto.subtle, available globally in
 * Node 20+.
 */

import { describe, it, before } from 'node:test';
import assert from 'node:assert/strict';

const HKDF_INFO = new TextEncoder().encode('omi-byok-v1');
const AES_GCM_IV_LENGTH_BYTES = 12;
const AES_KEY_LENGTH_BITS = 256;

// Test pepper — 32 bytes of fixed test-only randomness. Production must
// supply a fresh `openssl rand -base64 32` value via BYOK_MASTER_PEPPER.
const TEST_PEPPER_BASE64 = 'AbcdEfghIjklMnopQrstUvwxYz0123456789ABCDEFG=';

function getPepperBytes(b64) {
  const cleaned = b64.replace(/\s+/g, '').replace(/-/g, '+').replace(/_/g, '/');
  return new Uint8Array(Buffer.from(cleaned, 'base64'));
}

async function deriveUserKey(pepperB64, uid) {
  const pepperKey = await crypto.subtle.importKey(
    'raw',
    getPepperBytes(pepperB64),
    { name: 'HKDF' },
    false,
    ['deriveKey'],
  );
  return crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: new TextEncoder().encode(uid),
      info: HKDF_INFO,
    },
    pepperKey,
    { name: 'AES-GCM', length: AES_KEY_LENGTH_BITS },
    false,
    ['encrypt', 'decrypt'],
  );
}

function b64Encode(bytes) {
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  return Buffer.from(view).toString('base64');
}

function b64Decode(s) {
  return new Uint8Array(Buffer.from(s, 'base64'));
}

async function encrypt(pepperB64, uid, plaintext) {
  const key = await deriveUserKey(pepperB64, uid);
  const iv = crypto.getRandomValues(new Uint8Array(AES_GCM_IV_LENGTH_BYTES));
  const ct = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    new TextEncoder().encode(plaintext),
  );
  return { ciphertext: b64Encode(ct), iv: b64Encode(iv) };
}

async function decrypt(pepperB64, uid, encrypted) {
  const key = await deriveUserKey(pepperB64, uid);
  const pt = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: b64Decode(encrypted.iv) },
    key,
    b64Decode(encrypted.ciphertext),
  );
  return new TextDecoder().decode(pt);
}

async function hash(plaintext) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(plaintext));
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

describe('BYOK encryption (HKDF-SHA256 + AES-GCM)', () => {
  before(() => {
    assert.ok(globalThis.crypto?.subtle, 'webcrypto.subtle required (Node 20+)');
  });

  it('round-trips plaintext through encrypt → decrypt', async () => {
    const uid = 'user-12345';
    const key = 'sk-test-abcdef0123456789';
    const enc = await encrypt(TEST_PEPPER_BASE64, uid, key);
    const dec = await decrypt(TEST_PEPPER_BASE64, uid, enc);
    assert.equal(dec, key);
  });

  it('produces different ciphertexts for the same plaintext (random IV)', async () => {
    const uid = 'user-12345';
    const key = 'sk-test-abcdef0123456789';
    const e1 = await encrypt(TEST_PEPPER_BASE64, uid, key);
    const e2 = await encrypt(TEST_PEPPER_BASE64, uid, key);
    assert.notEqual(e1.ciphertext, e2.ciphertext, 'ciphertext should not repeat');
    assert.notEqual(e1.iv, e2.iv, 'IV should not repeat');
    // Both must still decrypt to the same plaintext.
    assert.equal(await decrypt(TEST_PEPPER_BASE64, uid, e1), key);
    assert.equal(await decrypt(TEST_PEPPER_BASE64, uid, e2), key);
  });

  it('does not allow decryption with the wrong UID', async () => {
    const key = 'sk-test-abcdef0123456789';
    const enc = await encrypt(TEST_PEPPER_BASE64, 'user-A', key);
    await assert.rejects(
      () => decrypt(TEST_PEPPER_BASE64, 'user-B', enc),
      /OperationError|invalid|tag/i,
    );
  });

  it('does not allow decryption with the wrong pepper', async () => {
    const otherPepper = 'XYZAbcdEfghIjklMnopQrstUvwxYz0123456789ABCDE='; // valid b64, different
    const key = 'sk-test-abcdef0123456789';
    const enc = await encrypt(TEST_PEPPER_BASE64, 'user-A', key);
    await assert.rejects(
      () => decrypt(otherPepper, 'user-A', enc),
      /OperationError|invalid|tag/i,
    );
  });

  it('rejects tampered ciphertext (auth tag mismatch)', async () => {
    const uid = 'user-12345';
    const enc = await encrypt(TEST_PEPPER_BASE64, uid, 'sk-test-key');
    // Flip the last byte of the ciphertext.
    const ctBytes = b64Decode(enc.ciphertext);
    ctBytes[ctBytes.length - 1] ^= 0x01;
    const tampered = { ciphertext: b64Encode(ctBytes), iv: enc.iv };
    await assert.rejects(
      () => decrypt(TEST_PEPPER_BASE64, uid, tampered),
      /OperationError|invalid|tag/i,
    );
  });

  it('hash is deterministic and matches expected SHA-256', async () => {
    const h1 = await hash('sk-test-key');
    const h2 = await hash('sk-test-key');
    assert.equal(h1, h2, 'hash must be deterministic');
    assert.equal(h1.length, 64, 'SHA-256 hex must be 64 chars');
    // Sanity vs Node crypto module.
    const { createHash } = await import('node:crypto');
    const expected = createHash('sha256').update('sk-test-key').digest('hex');
    assert.equal(h1, expected);
  });

  it('different plaintexts produce different hashes', async () => {
    const a = await hash('sk-test-A');
    const b = await hash('sk-test-B');
    assert.notEqual(a, b);
  });
});
