import { NextRequest, NextResponse } from 'next/server';
import { DEV_BYPASS_ENABLED, DEV_BYPASS_TOKEN, DEV_BYPASS_UID } from '@/lib/dev-auth';
import { verifyFirebaseToken, getDb } from '@/lib/firebase/admin';
import { resolveActiveTvToken, type ResolvedTvLink } from '@/lib/tv-links';

/**
 * Verify that the request comes from an authenticated admin user.
 * Checks: (1) valid Firebase ID token in Authorization header,
 * (2) user's UID exists in the adminData collection.
 * Returns the decoded token on success, or a NextResponse error on failure.
 */
export async function verifyAdmin(request: NextRequest): Promise<
  { uid: string } | NextResponse
> {
  const authorization = request.headers.get('Authorization');

  if (DEV_BYPASS_ENABLED && authorization === `Bearer ${DEV_BYPASS_TOKEN}`) {
    return { uid: DEV_BYPASS_UID };
  }

  if (!authorization || !authorization.startsWith('Bearer ')) {
    return NextResponse.json({ error: 'Unauthorized: Missing or invalid token' }, { status: 401 });
  }

  const token = authorization.split('Bearer ')[1];
  try {
    const decodedToken = await verifyFirebaseToken(token);
    if (!decodedToken) {
      return NextResponse.json({ error: 'Unauthorized: Invalid token' }, { status: 401 });
    }

    const db = getDb();
    const adminDoc = await db.collection('adminData').doc(decodedToken.uid).get();
    if (!adminDoc.exists) {
      return NextResponse.json({ error: 'Forbidden: Not an admin' }, { status: 403 });
    }

    return { uid: decodedToken.uid };
  } catch (error) {
    console.error('Error verifying admin:', error);
    return NextResponse.json({ error: 'Internal server error during auth' }, { status: 500 });
  }
}

/** Extract a candidate TV share token from Authorization or `?token=`. */
export function extractTvToken(request: NextRequest): string | null {
  const authorization = request.headers.get('Authorization');
  if (authorization?.startsWith('Bearer ')) {
    const t = authorization.slice('Bearer '.length).trim();
    if (t && t !== DEV_BYPASS_TOKEN) return t;
  }
  const q = request.nextUrl.searchParams.get('token');
  return q?.trim() || null;
}

/** Firebase ID tokens are three '.'-separated segments; TV tokens are opaque base64url. */
function bearerLooksLikeJwt(bearer: string): boolean {
  return bearer.split('.').length === 3;
}

/**
 * TV share-link auth. Intentionally separate from verifyAdmin so a TV token
 * can never be mistaken for a full admin session.
 */
export async function verifyTvLink(
  request: NextRequest,
): Promise<ResolvedTvLink | NextResponse> {
  const raw = extractTvToken(request);
  if (!raw) {
    return NextResponse.json({ error: 'Unauthorized: Missing TV token' }, { status: 401 });
  }
  try {
    const link = await resolveActiveTvToken(raw);
    if (!link) {
      return NextResponse.json(
        { error: 'Unauthorized: Invalid or revoked TV link' },
        { status: 401 },
      );
    }
    return link;
  } catch (error) {
    console.error('Error verifying TV link:', error);
    return NextResponse.json(
      { error: 'Internal server error during TV auth' },
      { status: 500 },
    );
  }
}

export type SnapshotAuth =
  | { kind: 'admin'; uid: string; includeRevenue: true }
  | { kind: 'tv'; link: ResolvedTvLink; includeRevenue: boolean };

/**
 * Admin Firebase session OR active TV share link.
 * Used only by the read-only TV snapshot endpoint.
 *
 * Credential shapes are disjoint so kiosk polls never call Firebase verify
 * (and never log false auth errors), and JWT failures keep their status
 * instead of being flattened to a generic 401.
 */
export async function verifyAdminOrTvSnapshot(
  request: NextRequest,
): Promise<SnapshotAuth | NextResponse> {
  const authorization = request.headers.get('Authorization');
  const bearer = authorization?.startsWith('Bearer ')
    ? authorization.slice('Bearer '.length).trim()
    : '';
  const queryToken = request.nextUrl.searchParams.get('token')?.trim() || '';

  if (DEV_BYPASS_ENABLED && bearer === DEV_BYPASS_TOKEN) {
    return { kind: 'admin', uid: DEV_BYPASS_UID, includeRevenue: true };
  }

  if (bearer && bearerLooksLikeJwt(bearer)) {
    const admin = await verifyAdmin(request);
    if (admin instanceof NextResponse) return admin;
    return { kind: 'admin', uid: admin.uid, includeRevenue: true };
  }

  // Opaque bearer (TV capability) or ?token= kiosk query.
  if ((bearer && !bearerLooksLikeJwt(bearer)) || queryToken) {
    const tv = await verifyTvLink(request);
    if (tv instanceof NextResponse) return tv;
    return {
      kind: 'tv',
      link: tv,
      includeRevenue: tv.includeRevenue,
    };
  }

  return NextResponse.json(
    { error: 'Unauthorized: Missing or invalid token' },
    { status: 401 },
  );
}
