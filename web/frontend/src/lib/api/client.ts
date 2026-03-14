import { auth } from '@/src/lib/firebase';
import { getStoredKeyHash } from '@/src/lib/e2ee';

/**
 * Fetch wrapper that adds auth and E2EE headers automatically.
 */
export async function apiFetch(url: string, options?: RequestInit): Promise<Response> {
  const headers = new Headers(options?.headers);

  const user = auth.currentUser;
  if (user) {
    const token = await user.getIdToken();
    headers.set('Authorization', `Bearer ${token}`);
  }

  const keyHash = getStoredKeyHash();
  if (keyHash) {
    headers.set('X-E2EE-Key-Hash', keyHash);
  }

  return fetch(url, { ...options, headers });
}
