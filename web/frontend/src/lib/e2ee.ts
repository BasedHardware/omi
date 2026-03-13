/**
 * E2EE decryption for the web frontend using Web Crypto API.
 * Mirrors the AES-256-GCM encryption in the Flutter app.
 * The key never leaves the browser — it's stored in sessionStorage
 * and cleared when the tab is closed.
 */

const E2EE_KEY_STORAGE = 'omi_e2ee_key';

export async function importKey(base64Key: string): Promise<CryptoKey> {
  const keyBytes = Uint8Array.from(atob(base64Key), c => c.charCodeAt(0));
  if (keyBytes.length !== 32) {
    throw new Error('Invalid key length. Expected 32 bytes.');
  }
  return crypto.subtle.importKey(
    'raw',
    keyBytes,
    { name: 'AES-GCM', length: 256 },
    false,
    ['decrypt']
  );
}

export async function decrypt(encrypted: string, key: CryptoKey): Promise<string> {
  if (!encrypted) return encrypted;

  let payload: Uint8Array;
  try {
    payload = Uint8Array.from(atob(encrypted), c => c.charCodeAt(0));
  } catch {
    // Not valid base64 — likely plaintext
    return encrypted;
  }

  if (payload.length < 28) {
    // Too short for nonce(12) + tag(16) + data
    return encrypted;
  }

  const nonce = payload.slice(0, 12);
  const ciphertext = payload.slice(12);

  try {
    const decrypted = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: nonce, tagLength: 128 },
      key,
      ciphertext
    );
    return new TextDecoder().decode(decrypted);
  } catch {
    // Decryption failed — might be server-encrypted, not client-encrypted
    return encrypted;
  }
}

export function storeKey(base64Key: string): void {
  sessionStorage.setItem(E2EE_KEY_STORAGE, base64Key);
}

export function getStoredKey(): string | null {
  return sessionStorage.getItem(E2EE_KEY_STORAGE);
}

export function clearKey(): void {
  sessionStorage.removeItem(E2EE_KEY_STORAGE);
}

export function hasKey(): boolean {
  return sessionStorage.getItem(E2EE_KEY_STORAGE) !== null;
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
