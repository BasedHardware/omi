import { openDB, type DBSchema, type IDBPDatabase } from 'idb';

/**
 * Chat drafts are needed synchronously while a send is in flight, so the
 * current tab keeps an in-memory copy. The durable copy is AES-GCM encrypted;
 * its non-extractable key is structured-cloned into IndexedDB.
 */
const baseKeys = {
  panel: 'omi.chat.draft.panel',
  home: 'omi.chat.draft.home',
} as const;

interface DraftKeyDB extends DBSchema {
  keys: {
    key: string;
    value: CryptoKey;
  };
}

const DB_NAME = 'omi-chat-draft-keys';
const DB_VERSION = 1;
const KEY_ID = 'aes-gcm-v1';
const ENVELOPE_VERSION = 'v1';
const encoder = new TextEncoder();
const decoder = new TextDecoder();

let owner = '';
let ownerEpoch = 0;
let dbPromise: Promise<IDBPDatabase<DraftKeyDB>> | null = null;
const drafts = new Map<string, string>();
const revisions = new Map<string, number>();

function scopedKey(base: string): string {
  return owner ? `${base}:${owner}` : base;
}

function revisionFor(key: string): number {
  return revisions.get(key) ?? 0;
}

function advanceRevision(key: string): number {
  const next = revisionFor(key) + 1;
  revisions.set(key, next);
  return next;
}

function getDB(): Promise<IDBPDatabase<DraftKeyDB>> {
  if (!dbPromise) {
    dbPromise = openDB<DraftKeyDB>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        db.createObjectStore('keys');
      },
    });
  }
  return dbPromise;
}

async function getEncryptionKey(): Promise<CryptoKey> {
  const db = await getDB();
  const existing = await db.get('keys', KEY_ID);
  if (existing) return existing;

  const generated = await crypto.subtle.generateKey(
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  );

  // Read and write in one serialized transaction so two tabs do not replace
  // each other's key during first use.
  const tx = db.transaction('keys', 'readwrite');
  const current = await tx.store.get(KEY_ID);
  if (current) {
    await tx.done;
    return current;
  }
  await tx.store.put(generated, KEY_ID);
  await tx.done;
  return generated;
}

function bytesToBase64Url(bytes: Uint8Array): string {
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function base64UrlToBytes(value: string): Uint8Array {
  if (!/^[A-Za-z0-9_-]*$/.test(value)) throw new Error('Invalid chat draft envelope');
  const padded =
    value.replace(/-/g, '+').replace(/_/g, '/') +
    '='.repeat((4 - (value.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/** Encrypt a draft with the storage key as authenticated context. */
export async function encryptChatDraft(
  value: string,
  key: CryptoKey,
  storageKey: string,
): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    {
      name: 'AES-GCM',
      iv: iv as BufferSource,
      additionalData: encoder.encode(storageKey) as BufferSource,
      tagLength: 128,
    },
    key,
    encoder.encode(value) as BufferSource,
  );
  return `${ENVELOPE_VERSION}.${bytesToBase64Url(iv)}.${bytesToBase64Url(
    new Uint8Array(ciphertext),
  )}`;
}

/** Decrypt only a versioned AES-GCM draft envelope. */
export async function decryptChatDraft(
  envelope: string,
  key: CryptoKey,
  storageKey: string,
): Promise<string> {
  const [version, ivText, ciphertextText, extra] = envelope.split('.');
  if (version !== ENVELOPE_VERSION || !ivText || !ciphertextText || extra !== undefined) {
    throw new Error('Invalid chat draft envelope');
  }
  const plaintext = await crypto.subtle.decrypt(
    {
      name: 'AES-GCM',
      iv: base64UrlToBytes(ivText) as BufferSource,
      additionalData: encoder.encode(storageKey) as BufferSource,
      tagLength: 128,
    },
    key,
    base64UrlToBytes(ciphertextText) as BufferSource,
  );
  return decoder.decode(plaintext);
}

/** Called by the auth provider whenever the signed-in account changes. */
export function setChatDraftOwner(uid: string | null): void {
  const next = uid ?? '';
  if (next === owner) return;
  if (owner) {
    clearChatDraft(baseKeys.panel);
    clearChatDraft(baseKeys.home);
  }
  owner = next;
  ownerEpoch += 1;
}

/** The owner the current draft keys are scoped to ('' while signed out). */
export function chatDraftOwner(): string {
  return owner;
}

export const chatDraftKeys = baseKeys;

/** Return this tab's synchronous draft copy, or an empty string. */
export function readChatDraft(key: string): string {
  return drafts.get(scopedKey(key)) ?? '';
}

/** A revision token lets async restore avoid replacing newer user input. */
export function chatDraftRevision(key: string): number {
  return revisionFor(scopedKey(key));
}

/** Restore the encrypted durable copy if no newer in-memory value exists. */
export async function restoreChatDraft(key: string): Promise<string> {
  const storageKey = scopedKey(key);
  if (drafts.has(storageKey)) return drafts.get(storageKey) ?? '';
  const revision = revisionFor(storageKey);
  const epoch = ownerEpoch;
  try {
    const envelope = window.localStorage.getItem(storageKey);
    if (!envelope) return '';
    // Remove plaintext values written by older builds; never restore or keep
    // an unencrypted draft on disk.
    if (!envelope.startsWith(`${ENVELOPE_VERSION}.`)) {
      window.localStorage.removeItem(storageKey);
      return '';
    }
    const value = await decryptChatDraft(envelope, await getEncryptionKey(), storageKey);
    if (revisionFor(storageKey) === revision && ownerEpoch === epoch) {
      drafts.set(storageKey, value);
      return value;
    }
    return readChatDraft(key);
  } catch {
    return '';
  }
}

/** Update the synchronous copy and persist ciphertext on a best-effort basis. */
export async function writeChatDraft(key: string, value: string): Promise<void> {
  if (!value) {
    clearChatDraft(key);
    return;
  }
  const storageKey = scopedKey(key);
  const revision = advanceRevision(storageKey);
  const epoch = ownerEpoch;
  drafts.set(storageKey, value);
  try {
    const envelope = await encryptChatDraft(value, await getEncryptionKey(), storageKey);
    if (
      revisionFor(storageKey) === revision &&
      ownerEpoch === epoch &&
      drafts.get(storageKey) === value
    ) {
      window.localStorage.setItem(storageKey, envelope);
    }
  } catch {
    // Typing must keep working when browser storage or WebCrypto is blocked.
  }
}

export function clearChatDraft(key: string): void {
  const storageKey = scopedKey(key);
  advanceRevision(storageKey);
  drafts.delete(storageKey);
  try {
    window.localStorage.removeItem(storageKey);
  } catch {
    // Best-effort like the encrypted write path.
  }
}
