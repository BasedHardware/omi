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

export function storeKey(base64Key: string): void {
  localStorage.setItem(E2EE_KEY_STORAGE, base64Key);
}

export function storeKeyHash(hash: string): void {
  localStorage.setItem(E2EE_KEY_HASH_STORAGE, hash);
}

export function getStoredKey(): string | null {
  return localStorage.getItem(E2EE_KEY_STORAGE);
}

export function getStoredKeyHash(): string | null {
  return localStorage.getItem(E2EE_KEY_HASH_STORAGE);
}

export function hasKey(): boolean {
  return localStorage.getItem(E2EE_KEY_STORAGE) !== null;
}

export function clearKey(): void {
  localStorage.removeItem(E2EE_KEY_STORAGE);
  localStorage.removeItem(E2EE_KEY_HASH_STORAGE);
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
