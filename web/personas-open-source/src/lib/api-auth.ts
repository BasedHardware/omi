import { auth } from '@/lib/firebase';

/**
 * Headers for calls to this app's privileged API routes. The routes derive the
 * caller's UID from this token, so it must be attached to every request.
 */
export async function authedJsonHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = await auth.currentUser?.getIdToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}
