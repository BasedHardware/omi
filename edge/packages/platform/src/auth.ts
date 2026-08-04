/**
 * Firebase ID token verify for Workers (JWKS).
 * ADMIN_KEY impersonation mirrors backend/utils/other/endpoints.py verify_token.
 */

export type AuthEnv = {
  FIREBASE_PROJECT_ID: string;
  ADMIN_KEY?: string;
  ADMIN_KEY_AUTH_ENABLED?: string;
};

type JwtHeader = { alg: string; kid?: string };
type JwtPayload = { user_id?: string; sub?: string; aud?: string | string[]; iss?: string; exp?: number };

const JWKS_URL = (projectId: string) =>
  `https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com`;

let jwksCache: { keys: JsonWebKey[]; fetchedAt: number } | null = null;
const JWKS_TTL_MS = 60 * 60 * 1000;

async function getJwks(projectId: string): Promise<JsonWebKey[]> {
  const now = Date.now();
  if (jwksCache && now - jwksCache.fetchedAt < JWKS_TTL_MS) return jwksCache.keys;
  const res = await fetch(JWKS_URL(projectId));
  if (!res.ok) throw new Error(`JWKS fetch failed: ${res.status}`);
  const body = (await res.json()) as { keys: JsonWebKey[] };
  jwksCache = { keys: body.keys, fetchedAt: now };
  return body.keys;
}

function b64urlToBytes(s: string): Uint8Array {
  const pad = "=".repeat((4 - (s.length % 4)) % 4);
  const b64 = (s + pad).replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function decodeJson<T>(part: string): T {
  return JSON.parse(new TextDecoder().decode(b64urlToBytes(part))) as T;
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let out = 0;
  for (let i = 0; i < a.length; i++) out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return out === 0;
}

export async function verifyBearerToken(token: string, env: AuthEnv): Promise<string> {
  const adminKey = env.ADMIN_KEY;
  const adminEnabled = (env.ADMIN_KEY_AUTH_ENABLED ?? "true").toLowerCase() === "true";
  if (adminKey && adminEnabled && adminKey.length >= 16) {
    const prefix = token.slice(0, adminKey.length);
    if (timingSafeEqual(prefix, adminKey) && token.length > adminKey.length) {
      return token.slice(adminKey.length);
    }
  }

  const parts = token.split(".");
  if (parts.length !== 3) throw new Error("invalid_token");
  const [h, p, s] = parts as [string, string, string];
  const header = decodeJson<JwtHeader>(h);
  const payload = decodeJson<JwtPayload>(p);
  if (header.alg !== "RS256") throw new Error("invalid_alg");

  const projectId = env.FIREBASE_PROJECT_ID;
  const iss = `https://securetoken.google.com/${projectId}`;
  if (payload.iss !== iss) throw new Error("invalid_iss");
  const aud = payload.aud;
  const audOk = Array.isArray(aud) ? aud.includes(projectId) : aud === projectId;
  if (!audOk) throw new Error("invalid_aud");
  if (!payload.exp || payload.exp * 1000 < Date.now()) throw new Error("token_expired");

  const keys = await getJwks(projectId);
  const jwk = keys.find((k) => (k as JsonWebKey & { kid?: string }).kid === header.kid);
  if (!jwk) throw new Error("unknown_kid");

  const key = await crypto.subtle.importKey(
    "jwk",
    jwk,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"],
  );
  const data = new TextEncoder().encode(`${h}.${p}`);
  const sig = b64urlToBytes(s);
  const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, sig, data);
  if (!ok) throw new Error("bad_signature");

  const uid = payload.user_id || payload.sub;
  if (!uid) throw new Error("missing_uid");
  return uid;
}

export function bearerFromAuthorization(header: string | null): string | null {
  if (!header) return null;
  const m = /^Bearer\s+(.+)$/i.exec(header.trim());
  return m?.[1]?.trim() || null;
}
