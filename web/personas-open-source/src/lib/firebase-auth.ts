const JWKS_URL =
  'https://www.googleapis.com/robot/v1/metadata/jwk/securetoken@system.gserviceaccount.com';

const DEFAULT_JWKS_TTL_MS = 60 * 60 * 1000;

interface RsaJwk {
  kty: string;
  alg?: string;
  use?: string;
  kid: string;
  n: string;
  e: string;
}

interface JwtHeader {
  alg?: unknown;
  kid?: unknown;
  typ?: unknown;
}

interface JwtPayload {
  iss?: unknown;
  aud?: unknown;
  sub?: unknown;
  exp?: unknown;
  iat?: unknown;
}

let cache: { keys: Map<string, RsaJwk>; expiresAt: number } | null = null;
let inFlight: Promise<Map<string, RsaJwk>> | null = null;

function projectId(): string {
  const id =
    process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID || process.env.FIREBASE_PROJECT_ID;
  if (!id) {
    throw new Error('Missing NEXT_PUBLIC_FIREBASE_PROJECT_ID');
  }
  return id;
}

function maxAgeMs(header: string | null): number {
  if (!header) return DEFAULT_JWKS_TTL_MS;
  const match = /max-age\s*=\s*(\d+)/i.exec(header);
  if (!match) return DEFAULT_JWKS_TTL_MS;
  const seconds = Number(match[1]);
  if (!Number.isFinite(seconds) || seconds <= 0) return DEFAULT_JWKS_TTL_MS;
  return seconds * 1000;
}

function isRsaJwk(value: unknown): value is RsaJwk {
  const jwk = value as RsaJwk | null;
  return (
    !!jwk &&
    typeof jwk === 'object' &&
    jwk.kty === 'RSA' &&
    typeof jwk.kid === 'string' &&
    jwk.kid.length > 0 &&
    typeof jwk.n === 'string' &&
    typeof jwk.e === 'string' &&
    (jwk.alg === undefined || jwk.alg === 'RS256')
  );
}

async function loadJwks(): Promise<Map<string, RsaJwk>> {
  const now = Date.now();
  if (cache && cache.expiresAt > now) return cache.keys;
  if (inFlight) return inFlight;

  inFlight = (async () => {
    const res = await fetch(JWKS_URL, { cache: 'no-store' });
    if (!res.ok) {
      throw new Error(`Failed to fetch Google JWKS: ${res.status}`);
    }
    const body = (await res.json()) as { keys?: unknown };
    if (!Array.isArray(body.keys)) {
      throw new Error('Malformed Google JWKS response');
    }
    const keys = new Map<string, RsaJwk>();
    for (const entry of body.keys) {
      if (isRsaJwk(entry)) keys.set(entry.kid, entry);
    }
    if (keys.size === 0) {
      throw new Error('Google JWKS contained no usable RSA keys');
    }
    cache = { keys, expiresAt: Date.now() + maxAgeMs(res.headers.get('cache-control')) };
    return keys;
  })();

  try {
    return await inFlight;
  } finally {
    inFlight = null;
  }
}

function base64UrlToBytes(input: string): Uint8Array {
  if (!/^[A-Za-z0-9_-]*$/.test(input)) {
    throw new Error('Invalid base64url segment');
  }
  const padded = input.replace(/-/g, '+').replace(/_/g, '/');
  return new Uint8Array(Buffer.from(padded, 'base64'));
}

function decodeJsonSegment(segment: string): unknown {
  return JSON.parse(new TextDecoder().decode(base64UrlToBytes(segment)));
}

async function importKey(jwk: RsaJwk): Promise<CryptoKey> {
  return globalThis.crypto.subtle.importKey(
    'jwk',
    { kty: 'RSA', n: jwk.n, e: jwk.e, alg: 'RS256', ext: true },
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['verify'],
  );
}

/**
 * Verify a Firebase ID token against Google's published signing keys.
 * Returns the token's `sub` (the caller's UID) or null if anything about the
 * token fails to check out.
 */
export async function verifyFirebaseIdToken(token: string): Promise<string | null> {
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  const [headerSegment, payloadSegment, signatureSegment] = parts;
  if (!headerSegment || !payloadSegment || !signatureSegment) return null;

  let header: JwtHeader;
  let payload: JwtPayload;
  let signature: Uint8Array;
  try {
    header = decodeJsonSegment(headerSegment) as JwtHeader;
    payload = decodeJsonSegment(payloadSegment) as JwtPayload;
    signature = base64UrlToBytes(signatureSegment);
  } catch {
    return null;
  }

  if (!header || typeof header !== 'object' || !payload || typeof payload !== 'object') {
    return null;
  }
  if (header.alg !== 'RS256') return null;
  if (typeof header.kid !== 'string' || header.kid.length === 0) return null;
  if (signature.length === 0) return null;

  let keys: Map<string, RsaJwk>;
  try {
    keys = await loadJwks();
  } catch (error) {
    console.error('Unable to load Google signing keys:', error);
    throw error;
  }

  const jwk = keys.get(header.kid);
  if (!jwk) return null;

  let verified = false;
  try {
    const key = await importKey(jwk);
    verified = await globalThis.crypto.subtle.verify(
      'RSASSA-PKCS1-v1_5',
      key,
      signature,
      new TextEncoder().encode(`${headerSegment}.${payloadSegment}`),
    );
  } catch {
    return null;
  }
  if (!verified) return null;

  const id = projectId();
  if (payload.iss !== `https://securetoken.google.com/${id}`) return null;
  if (payload.aud !== id) return null;

  const nowSeconds = Date.now() / 1000;
  if (typeof payload.exp !== 'number' || !(payload.exp > nowSeconds)) return null;
  if (typeof payload.iat !== 'number' || !(payload.iat <= nowSeconds)) return null;
  if (typeof payload.sub !== 'string' || payload.sub.length === 0) return null;

  return payload.sub;
}

/** Firebase UIDs are 28 alphanumeric chars today; allow a generous band. */
const UID_PATTERN = /^[A-Za-z0-9]{20,128}$/;

export type AuthResult = { uid: string } | { error: string; status: number };

/**
 * Derive the caller's UID from a verified Firebase ID token. The request body
 * is never trusted for identity — these routes act with privileged server
 * credentials on behalf of whoever the token says they are.
 */
export async function authenticateRequest(req: Request): Promise<AuthResult> {
  const authorization = req.headers.get('Authorization');
  if (!authorization || !authorization.startsWith('Bearer ')) {
    return { error: 'Unauthorized: Missing or invalid token', status: 401 };
  }

  const token = authorization.slice('Bearer '.length).trim();
  if (!token) {
    return { error: 'Unauthorized: Missing or invalid token', status: 401 };
  }

  let uid: string | null;
  try {
    uid = await verifyFirebaseIdToken(token);
  } catch (error) {
    console.error('Auth verification failed:', error);
    return { error: 'Internal server error during auth', status: 500 };
  }

  if (!uid || !UID_PATTERN.test(uid)) {
    return { error: 'Unauthorized: Invalid token', status: 401 };
  }

  return { uid };
}
