// Desktop sign-in handoff, ported from the v4 worker's `desktop-auth.ts`
// (undivisible/omi-v4 worker-rs/src/desktop_auth.rs): PKCE-style challenges,
// a derived session id, and RS256 service-account signing of Firebase custom
// tokens. The 3-step SQL handoff (start/complete/exchange) lives in
// desktop-auth-routes.ts; this module stays pure so every rule is testable
// without D1 or the network.

export const DESKTOP_AUTH_LIFETIME_MS = 5 * 60 * 1000;
export const DESKTOP_AUTH_START_RATE_LIMIT = 10;
export const DESKTOP_AUTH_START_RATE_WINDOW_MS = 10 * 60 * 1000;
export const DESKTOP_AUTH_CONFIRMATION_ATTEMPT_LIMIT = 5;

// `^[A-Za-z0-9_-]{32,128}$`. Used for sessionId, challenge,
// confirmationChallenge, and verifier.
export function isValidSessionValue(input: string): boolean {
  return /^[A-Za-z0-9_-]{32,128}$/.test(input);
}

// `^[0-9]{6}$`.
export function isValidConfirmationCode(input: string): boolean {
  return /^[0-9]{6}$/.test(input);
}

export function base64UrlEncode(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  const padded = btoa(binary);
  return padded.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export async function sha256Base64Url(value: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value)
  );
  return base64UrlEncode(new Uint8Array(digest));
}

// SHA-256 -> base64url of a verifier or confirmation code. Stored server-side
// so a D1 compromise cannot replay the handoff.
export const verifierChallenge = sha256Base64Url;

// Derives the desktop-auth session id from the client-supplied PKCE
// challenges so the id cannot be chosen independently of the verifier
// material: sha256url(challenge + "\0" + confirmationChallenge).
export async function deriveSessionId(
  challenge: string,
  confirmationChallenge: string
): Promise<string | null> {
  if (
    !isValidSessionValue(challenge) ||
    !isValidSessionValue(confirmationChallenge)
  ) {
    return null;
  }
  const derived = await sha256Base64Url(
    `${challenge}\0${confirmationChallenge}`
  );
  return isValidSessionValue(derived) ? derived : null;
}

// The browser leg of the handoff is this worker's own confirmation page:
// <origin>/auth/desktop?desktop_auth=<sessionId>. The origin is the one the
// desktop client actually reached, so it is reachable by construction.
export function browserUrlFor(
  origin: string,
  sessionId: string
): string | null {
  if (!isValidSessionValue(sessionId)) return null;
  try {
    const url = new URL("/auth/desktop", origin);
    url.searchParams.set("desktop_auth", sessionId);
    return url.toString();
  } catch {
    return null;
  }
}

// Decode a PKCS#8 PEM private key body into DER bytes. Handles the `\n`
// escaping wrangler secret put applies to multiline values.
export function privateKeyDer(pem: string): Uint8Array | null {
  const normalized = pem.replaceAll("\\n", "\n");
  const body = normalized
    .replace("-----BEGIN PRIVATE KEY-----", "")
    .replace("-----END PRIVATE KEY-----", "")
    .replace(/\s+/g, "");
  if (body.length === 0) return null;
  try {
    const padded = atob(body.replace(/-/g, "+").replace(/_/g, "/"));
    const bytes = new Uint8Array(padded.length);
    for (let index = 0; index < padded.length; index += 1) {
      bytes[index] = padded.charCodeAt(index);
    }
    return bytes;
  } catch {
    return null;
  }
}

// Sign a Firebase custom token (RS256) for `uid` with the service account.
// `nowSeconds` is unix seconds; the token lives one hour. Returns null when
// the key is unusable — the route maps that to 503.
export async function createFirebaseCustomToken(
  uid: string,
  serviceAccountEmail: string,
  privateKeyPem: string,
  nowSeconds: number
): Promise<string | null> {
  const der = privateKeyDer(privateKeyPem);
  if (der === null || serviceAccountEmail.length === 0) return null;
  let key: CryptoKey;
  try {
    key = await crypto.subtle.importKey(
      "pkcs8",
      der as unknown as BufferSource,
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
      false,
      ["sign"]
    );
  } catch {
    return null;
  }
  const header = base64UrlEncode(
    new TextEncoder().encode('{"alg":"RS256","typ":"JWT"}')
  );
  const payloadJson = JSON.stringify({
    iss: serviceAccountEmail,
    sub: serviceAccountEmail,
    aud: "https://identitytoolkit.googleapis.com/google.identity.identitytoolkit.v1.IdentityToolkit",
    iat: nowSeconds,
    exp: nowSeconds + 3600,
    uid,
  });
  const payload = base64UrlEncode(new TextEncoder().encode(payloadJson));
  const unsigned = `${header}.${payload}`;
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    key,
    new TextEncoder().encode(unsigned) as unknown as BufferSource
  );
  return `${unsigned}.${base64UrlEncode(new Uint8Array(signature))}`;
}
