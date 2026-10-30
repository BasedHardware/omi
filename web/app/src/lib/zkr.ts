// Browser side of the ZK Relay (zkr) v1 hand-off: encrypt a freshly created
// Omi key locally and turn it into a one-time agent link, so the copy-paste
// prompt carries a capability URL instead of the raw secret.
//
// Protocol: https://zkr.scalingforever.com/protocol/v1
// Source:   https://github.com/Git-on-my-level/zk-relay (public/crypto.js)
//
// What leaves the browser: ciphertext, nonce, and SHA-256 of the access token.
// The AES key K and the access token T exist only in this module's memory and
// in the link fragment (`#v1.K.T`), which browsers and HTTP clients never send.

/** Public zkr instance. The link origin, never a fetch target from the browser. */
export const ZKR_ORIGIN = 'https://zkr.scalingforever.com';

/**
 * Same-origin relay for the create call. zkr serves no CORS headers, so the
 * browser cannot read its create response directly; the web server forwards
 * the ciphertext-only request (see `app/api/zkr/secrets/route.ts`).
 */
export const ZKR_CREATE_ENDPOINT = '/api/zkr/secrets';

export const ZKR_PROTOCOL_VERSION = 1;
export const ZKR_AAD = 'zk-relay/v1;envelope';

/** Shortest TTL zkr accepts. A key share is consumed once, within minutes. */
export const ZKR_SHARE_TTL_SECONDS = 3600;

/** Receive command the prompt tells the agent to run (link on stdin). */
export const ZKR_RECEIVE_COMMAND = 'zkr receive --link-stdin --output';

/** Agent-facing install/usage guide. */
export const ZKR_LLMS_TXT = `${ZKR_ORIGIN}/llms.txt`;

export interface ZkrEnvelope {
  v: 1;
  kind: 'text';
  name: string;
  mediaType: string;
  data: string;
}

/** The exact body `POST /api/v1/secrets` accepts — nothing secret in it. */
export interface ZkrCreateRequest {
  v: 1;
  ciphertext: string;
  nonce: string;
  accessTokenHash: string;
  expiresInSeconds: number;
  expireAfterReveal: true;
}

export interface ZkrShare {
  id: string;
  expiresAt: string;
  /** `/a/:id#v1.K.T` — what an agent receives with `zkr receive`. */
  agentLink: string;
  /** `/h/:id#v1.K.T` — browser link for a human recipient. */
  humanLink: string;
}

const encoder = new TextEncoder();

export function bytesToBase64Url(bytes: Uint8Array): string {
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

export function base64UrlToBytes(value: string): Uint8Array {
  if (!/^[A-Za-z0-9_-]*$/.test(value)) throw new Error('Invalid base64url value');
  const padded =
    value.replace(/-/g, '+').replace(/_/g, '/') +
    '='.repeat((4 - (value.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function randomBytes(length: number): Uint8Array {
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  return bytes;
}

/** A `text` envelope; the field order matches the reference client byte for byte. */
export function textEnvelope(secret: string, name = 'secret.txt'): ZkrEnvelope {
  return {
    v: ZKR_PROTOCOL_VERSION,
    kind: 'text',
    name,
    mediaType: 'text/plain; charset=utf-8',
    data: bytesToBase64Url(encoder.encode(secret)),
  };
}

/** AES-256-GCM over the UTF-8 JSON envelope with the fixed v1 AAD. */
export async function encryptEnvelope(
  envelope: ZkrEnvelope,
  key: Uint8Array,
  nonce: Uint8Array,
): Promise<Uint8Array> {
  if (key.length !== 32 || nonce.length !== 12) {
    throw new Error('Invalid encryption material');
  }
  const plaintext = encoder.encode(JSON.stringify(envelope));
  try {
    const cryptoKey = await crypto.subtle.importKey(
      'raw',
      key as BufferSource,
      'AES-GCM',
      false,
      ['encrypt'],
    );
    const encrypted = await crypto.subtle.encrypt(
      {
        name: 'AES-GCM',
        iv: nonce as BufferSource,
        additionalData: encoder.encode(ZKR_AAD),
        tagLength: 128,
      },
      cryptoKey,
      plaintext,
    );
    return new Uint8Array(encrypted);
  } finally {
    plaintext.fill(0);
  }
}

export async function hashAccessToken(token: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', token as BufferSource);
  return bytesToBase64Url(new Uint8Array(digest));
}

/**
 * Encrypt `secret` and build the create request plus the fragment capability.
 * `material` exists for the protocol test vector; production omits it.
 */
export async function prepareZkrShare(
  secret: string,
  options: {
    name?: string;
    ttlSeconds?: number;
    material?: { key: Uint8Array; token: Uint8Array; nonce: Uint8Array };
  } = {},
): Promise<{ request: ZkrCreateRequest; fragment: string }> {
  const key = options.material?.key ?? randomBytes(32);
  const token = options.material?.token ?? randomBytes(32);
  const nonce = options.material?.nonce ?? randomBytes(12);
  if (token.length !== 32) throw new Error('Invalid encryption material');
  const ciphertext = await encryptEnvelope(
    textEnvelope(secret, options.name),
    key,
    nonce,
  );
  return {
    request: {
      v: ZKR_PROTOCOL_VERSION,
      ciphertext: bytesToBase64Url(ciphertext),
      nonce: bytesToBase64Url(nonce),
      accessTokenHash: await hashAccessToken(token),
      expiresInSeconds: options.ttlSeconds ?? ZKR_SHARE_TTL_SECONDS,
      expireAfterReveal: true,
    },
    fragment: `v1.${bytesToBase64Url(key)}.${bytesToBase64Url(token)}`,
  };
}

export function zkrLinks(
  id: string,
  fragment: string,
  origin = ZKR_ORIGIN,
): { agentLink: string; humanLink: string } {
  return {
    agentLink: `${origin}/a/${id}#${fragment}`,
    humanLink: `${origin}/h/${id}#${fragment}`,
  };
}

/**
 * Create a one-time, one-hour share of `secret` and return its links. Only the
 * ciphertext request crosses the network; the fragment is assembled locally.
 */
export async function createZkrShare(
  secret: string,
  options: {
    name?: string;
    fetchImpl?: (url: string, init: RequestInit) => Promise<Response>;
    endpoint?: string;
  } = {},
): Promise<ZkrShare> {
  const { request, fragment } = await prepareZkrShare(secret, { name: options.name });
  const fetchImpl = options.fetchImpl ?? ((url, init) => fetch(url, init));
  const response = await fetchImpl(options.endpoint ?? ZKR_CREATE_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error(`Secure link failed (${response.status})`);
  const body = (await response.json()) as { id?: unknown; expiresAt?: unknown };
  if (typeof body.id !== 'string' || !/^[A-Za-z0-9_-]{22,}$/.test(body.id)) {
    throw new Error('Secure link failed (invalid response)');
  }
  return {
    id: body.id,
    expiresAt: typeof body.expiresAt === 'string' ? body.expiresAt : '',
    ...zkrLinks(body.id, fragment),
  };
}

/** An Omi key envelope encrypts to a few hundred characters; files are refused. */
export const ZKR_RELAY_MAX_CIPHERTEXT_CHARS = 4096;

/**
 * Validate a create request before it is forwarded: exactly the protocol's
 * fields, a one-hour expire-after-reveal share, and a ciphertext sized for a
 * key rather than a file. Shared by the relay route and its tests.
 */
export function isRelayableZkrRequest(value: unknown): value is ZkrCreateRequest {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const body = value as Record<string, unknown>;
  const keys = Object.keys(body).sort().join(',');
  if (keys !== 'accessTokenHash,ciphertext,expireAfterReveal,expiresInSeconds,nonce,v') {
    return false;
  }
  const b64 = /^[A-Za-z0-9_-]+$/;
  return (
    body.v === ZKR_PROTOCOL_VERSION &&
    body.expiresInSeconds === ZKR_SHARE_TTL_SECONDS &&
    body.expireAfterReveal === true &&
    typeof body.ciphertext === 'string' &&
    b64.test(body.ciphertext) &&
    body.ciphertext.length <= ZKR_RELAY_MAX_CIPHERTEXT_CHARS &&
    typeof body.nonce === 'string' &&
    b64.test(body.nonce) &&
    base64UrlToBytes(body.nonce).length === 12 &&
    typeof body.accessTokenHash === 'string' &&
    b64.test(body.accessTokenHash) &&
    base64UrlToBytes(body.accessTokenHash).length === 32
  );
}
