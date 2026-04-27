/**
 * BYOK encryption-at-rest for the web frontend.
 *
 * Per `desktop/docs/M4-decisions.md` § Decision 1 (KMS choice):
 * - App-side AES-GCM encryption.
 * - Per-user encryption key derived from `BYOK_MASTER_PEPPER` env-var via
 *   HKDF-SHA256 keyed by the user UID (so two users' ciphertexts cannot be
 *   swapped, and rotating the pepper invalidates every user's keys at once).
 * - Plaintext is never persisted; only `{ ciphertext, iv, hash }` reaches
 *   Firestore. `hash` is the SHA-256 fingerprint of the plaintext used by
 *   the backend's existing BYOK fingerprint comparison
 *   (`backend/utils/byok.py:141`) without needing to decrypt.
 *
 * Server-only — must NEVER ship in the browser bundle. Importers should be
 * Server Actions or route handlers that read the env-var.
 */

import envConfig from '@/src/constants/envConfig';

const HKDF_INFO = new TextEncoder().encode('omi-byok-v1');
const AES_KEY_LENGTH_BITS = 256;
const AES_GCM_IV_LENGTH_BYTES = 12; // standard for AES-GCM per NIST SP 800-38D

export class BYOKEncryptionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'BYOKEncryptionError';
  }
}

function getPepperBytes(): Uint8Array {
  const raw = envConfig.BYOK_MASTER_PEPPER;
  if (!raw) {
    throw new BYOKEncryptionError(
      'BYOK_MASTER_PEPPER env-var is not set. Generate one with `openssl rand -base64 32` and ' +
        'configure it in your server environment (NOT as NEXT_PUBLIC_*).',
    );
  }
  // Accept base64 or base64url. Strip whitespace defensively.
  const cleaned = raw.replace(/\s+/g, '').replace(/-/g, '+').replace(/_/g, '/');
  const buf = Buffer.from(cleaned, 'base64');
  if (buf.length < 32) {
    throw new BYOKEncryptionError(
      `BYOK_MASTER_PEPPER must decode to at least 32 bytes; got ${buf.length}.`,
    );
  }
  return new Uint8Array(buf);
}

async function deriveUserKey(uid: string): Promise<CryptoKey> {
  const pepperKey = await crypto.subtle.importKey(
    'raw',
    getPepperBytes(),
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

function bytesToBase64(bytes: ArrayBuffer | Uint8Array): string {
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  return Buffer.from(view).toString('base64');
}

function base64ToBytes(b64: string): Uint8Array {
  return new Uint8Array(Buffer.from(b64, 'base64'));
}

export interface EncryptedBYOK {
  ciphertext: string; // base64-encoded AES-GCM output (includes auth tag)
  iv: string; // base64-encoded 12-byte IV
}

export async function encryptBYOK(uid: string, plaintext: string): Promise<EncryptedBYOK> {
  if (!uid) throw new BYOKEncryptionError('uid is required');
  if (!plaintext) throw new BYOKEncryptionError('plaintext is required');

  const key = await deriveUserKey(uid);
  const iv = crypto.getRandomValues(new Uint8Array(AES_GCM_IV_LENGTH_BYTES));
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    new TextEncoder().encode(plaintext),
  );
  return { ciphertext: bytesToBase64(ciphertext), iv: bytesToBase64(iv) };
}

export async function decryptBYOK(uid: string, encrypted: EncryptedBYOK): Promise<string> {
  if (!uid) throw new BYOKEncryptionError('uid is required');
  if (!encrypted?.ciphertext || !encrypted?.iv) {
    throw new BYOKEncryptionError('encrypted must have ciphertext and iv');
  }

  const key = await deriveUserKey(uid);
  try {
    const plaintext = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: base64ToBytes(encrypted.iv) },
      key,
      base64ToBytes(encrypted.ciphertext),
    );
    return new TextDecoder().decode(plaintext);
  } catch {
    // AES-GCM auth tag mismatch — wrong UID, wrong pepper, or tampered data.
    // Do NOT include the underlying error; it can leak timing/oracle info.
    throw new BYOKEncryptionError(
      'BYOK decryption failed. The pepper may have rotated or the ciphertext is corrupt.',
    );
  }
}

/**
 * SHA-256 fingerprint of the plaintext key. Matches the backend's BYOK
 * fingerprint shape (`backend/utils/byok.py:141` — same hash hex over UTF-8
 * bytes) so the backend can compare against an enrollment record without
 * the web frontend needing to decrypt.
 */
export async function hashBYOK(plaintext: string): Promise<string> {
  if (!plaintext) throw new BYOKEncryptionError('plaintext is required');
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(plaintext));
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
