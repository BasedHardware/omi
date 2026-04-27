/**
 * Server-side Firestore reader/writer for the per-user settings document.
 *
 * Schema (`users/{uid}/settings/profile`):
 * ```
 * {
 *   eu_privacy_mode: boolean,
 *   byok_keys: {
 *     openai?:    { ciphertext: string, iv: string, hash: string },
 *     anthropic?: ...,
 *     gemini?:    ...,
 *     deepgram?:  ...,
 *     regolo?:    ...,
 *   },
 *   updated_at: number,  // Unix ms
 * }
 * ```
 *
 * `hash` is the SHA-256 of the plaintext key, included so the backend's
 * fingerprint-comparison (`backend/utils/byok.py:141`) can validate without
 * needing to decrypt. Plaintext keys never leave this module — only the
 * encrypted shape goes to Firestore, and only the plaintext-on-demand path
 * (for backend forwarding) returns a decrypted value.
 *
 * Security notes:
 * - This file is server-only. Any caller (Server Action, route handler)
 *   must be reachable only from server contexts — Firestore admin SDK
 *   reads are not currently used; the Firebase web SDK Firestore is
 *   reached via `db` from `lib/firebase.ts`. If admin-side reads become
 *   necessary, add a separate `firestore-admin.ts` module.
 * - Firestore security rules MUST pin reads/writes to `request.auth.uid`.
 */

import { doc, getDoc, setDoc, serverTimestamp } from 'firebase/firestore';
import { db } from '@/src/lib/firebase';
import {
  encryptBYOK,
  hashBYOK,
  decryptBYOK,
  type EncryptedBYOK,
} from '@/src/lib/firestore/encryption';

export type BYOKProvider = 'openai' | 'anthropic' | 'gemini' | 'deepgram' | 'regolo';

export const BYOK_PROVIDERS: readonly BYOKProvider[] = [
  'openai',
  'anthropic',
  'gemini',
  'deepgram',
  'regolo',
] as const;

export interface StoredBYOKKey extends EncryptedBYOK {
  hash: string; // SHA-256 of plaintext, hex-encoded
}

export interface UserSettings {
  eu_privacy_mode: boolean;
  byok_keys: Partial<Record<BYOKProvider, StoredBYOKKey>>;
  updated_at?: number;
}

const DEFAULT_SETTINGS: UserSettings = {
  eu_privacy_mode: false,
  byok_keys: {},
};

function settingsRef(uid: string) {
  if (!uid) throw new Error('uid is required for Firestore settings access');
  return doc(db, 'users', uid, 'settings', 'profile');
}

export async function getUserSettings(uid: string): Promise<UserSettings> {
  const snap = await getDoc(settingsRef(uid));
  if (!snap.exists()) return { ...DEFAULT_SETTINGS };

  const data = snap.data();
  return {
    eu_privacy_mode: Boolean(data.eu_privacy_mode),
    byok_keys: (data.byok_keys ?? {}) as UserSettings['byok_keys'],
    updated_at: typeof data.updated_at === 'number' ? data.updated_at : undefined,
  };
}

/** Toggle EU Privacy Mode without touching BYOK keys. */
export async function setEuPrivacyMode(uid: string, enabled: boolean): Promise<void> {
  const current = await getUserSettings(uid);
  await setDoc(
    settingsRef(uid),
    {
      ...current,
      eu_privacy_mode: enabled,
      updated_at: Date.now(),
    },
    { merge: true },
  );
}

/**
 * Encrypt and persist a BYOK key. Caller passes plaintext exactly once;
 * this function discards it after encryption. Empty string clears the key.
 */
export async function setBYOKKey(
  uid: string,
  provider: BYOKProvider,
  plaintextKey: string,
): Promise<void> {
  const current = await getUserSettings(uid);
  const nextByok = { ...current.byok_keys };

  if (plaintextKey === '') {
    delete nextByok[provider];
  } else {
    const encrypted = await encryptBYOK(uid, plaintextKey);
    const hash = await hashBYOK(plaintextKey);
    nextByok[provider] = { ...encrypted, hash };
  }

  await setDoc(
    settingsRef(uid),
    {
      ...current,
      byok_keys: nextByok,
      updated_at: Date.now(),
    },
    { merge: true },
  );
}

/**
 * Decrypt a stored BYOK key for backend header forwarding. Returns null if
 * the user hasn't configured a key for this provider. Callers must use the
 * returned plaintext immediately and never persist or log it.
 */
export async function getBYOKKeyForBackendForwarding(
  uid: string,
  provider: BYOKProvider,
): Promise<string | null> {
  const settings = await getUserSettings(uid);
  const stored = settings.byok_keys[provider];
  if (!stored) return null;
  return decryptBYOK(uid, stored);
}
