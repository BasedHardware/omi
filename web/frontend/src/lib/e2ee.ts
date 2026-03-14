/**
 * E2EE decryption for the web frontend using Web Crypto API.
 * Mirrors the AES-256-GCM encryption in the Flutter app.
 * The key is stored in localStorage and persists across tabs/sessions.
 */

const E2EE_KEY_STORAGE = 'omi_e2ee_key';
const E2EE_KEY_HASH_STORAGE = 'omi_e2ee_key_hash';

export async function computeKeyHash(base64Key: string): Promise<string> {
  const keyBytes = Uint8Array.from(atob(base64Key), (c) => c.charCodeAt(0));
  const hashBuffer = await crypto.subtle.digest('SHA-256', keyBytes);
  const hashArray = new Uint8Array(hashBuffer);
  return Array.from(hashArray)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

export function storeKeyHash(hash: string): void {
  localStorage.setItem(E2EE_KEY_HASH_STORAGE, hash);
}

export function getStoredKeyHash(): string | null {
  return localStorage.getItem(E2EE_KEY_HASH_STORAGE);
}

export async function importKey(base64Key: string): Promise<CryptoKey> {
  const keyBytes = Uint8Array.from(atob(base64Key), (c) => c.charCodeAt(0));
  if (keyBytes.length !== 32) {
    throw new Error('Invalid key length. Expected 32 bytes.');
  }
  return crypto.subtle.importKey(
    'raw',
    keyBytes,
    { name: 'AES-GCM', length: 256 },
    false,
    ['decrypt'],
  );
}

export async function decrypt(encrypted: string, key: CryptoKey): Promise<string> {
  if (!encrypted) return encrypted;

  let payload: Uint8Array;
  try {
    payload = Uint8Array.from(atob(encrypted), (c) => c.charCodeAt(0));
  } catch {
    return encrypted;
  }

  if (payload.length < 28) {
    return encrypted;
  }

  const nonce = payload.slice(0, 12);
  const ciphertext = payload.slice(12);

  try {
    const decrypted = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: nonce, tagLength: 128 },
      key,
      ciphertext,
    );
    return new TextDecoder().decode(decrypted);
  } catch {
    return encrypted;
  }
}

export async function storeKey(base64Key: string): Promise<void> {
  localStorage.setItem(E2EE_KEY_STORAGE, base64Key);
  const hash = await computeKeyHash(base64Key);
  storeKeyHash(hash);
}

export function getStoredKey(): string | null {
  return localStorage.getItem(E2EE_KEY_STORAGE);
}

export function clearKey(): void {
  localStorage.removeItem(E2EE_KEY_STORAGE);
  localStorage.removeItem(E2EE_KEY_HASH_STORAGE);
}

export function hasKey(): boolean {
  return localStorage.getItem(E2EE_KEY_STORAGE) !== null;
}

export async function getDecryptionKey(): Promise<CryptoKey | null> {
  const stored = getStoredKey();
  if (!stored) return null;
  try {
    return await importKey(stored);
  } catch {
    return null;
  }
}
