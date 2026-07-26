// Server-side (route handler) helpers for verifying a caller's Firebase ID token and
// rate-limiting by uid. This package has no firebase-admin dependency, so verification
// goes through the public Identity Toolkit REST API (same approach already used by
// src/app/api/social-profile/route.ts) rather than the Admin SDK.

const firebaseApiKey = process.env.NEXT_PUBLIC_FIREBASE_API_KEY;

const RATE_LIMIT_WINDOW_MS = 60_000;
const rateLimits = new Map<string, { count: number; resetAt: number }>();

/**
 * Verifies the request's `Authorization: Bearer <idToken>` header against Firebase and
 * returns the token's uid, or null if missing/invalid. Never trust a client-supplied
 * `uid` field in a request body in its place — only this return value is proof of
 * identity.
 */
export async function authenticatedUid(req: Request): Promise<string | null> {
  const authorization = req.headers.get('authorization');
  const token = authorization?.match(/^Bearer\s+(.+)$/i)?.[1];
  if (!token || !firebaseApiKey) return null;

  const response = await fetch(
    `https://identitytoolkit.googleapis.com/v1/accounts:lookup?key=${encodeURIComponent(
      firebaseApiKey,
    )}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ idToken: token }),
    },
  );

  if (!response.ok) return null;

  const data = (await response.json()) as { users?: Array<{ localId?: string }> };
  return data.users?.[0]?.localId || null;
}

/** In-memory sliding-window rate limiter, keyed by caller (uid or IP/hash). */
export function isRateLimited(key: string, maxRequests: number): boolean {
  const now = Date.now();
  if (rateLimits.size > 1000) {
    for (const [entryKey, entry] of rateLimits) {
      if (entry.resetAt <= now) rateLimits.delete(entryKey);
    }
  }

  const current = rateLimits.get(key);

  if (!current || current.resetAt <= now) {
    rateLimits.set(key, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS });
    return false;
  }

  current.count += 1;
  return current.count > maxRequests;
}
