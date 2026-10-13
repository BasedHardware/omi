import { describe, expect, it, vi } from 'vitest';
import {
  ZKR_AAD,
  ZKR_CREATE_ENDPOINT,
  base64UrlToBytes,
  bytesToBase64Url,
  createZkrShare,
  encryptEnvelope,
  isRelayableZkrRequest,
  prepareZkrShare,
  textEnvelope,
} from '@/lib/zkr';

// protocol/test-vectors.json from github.com/Git-on-my-level/zk-relay — the
// reference client's deterministic AES-GCM vector (public test payload).
const VECTOR = {
  key: 'AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8',
  nonce: 'EBESExQVFhcYGRob',
  envelope: {
    v: 1,
    kind: 'text',
    name: 'secret.txt',
    mediaType: 'text/plain; charset=utf-8',
    data: 'emstcmVsYXktaW50ZXJvcGVyYWJpbGl0eQ',
  },
  ciphertext:
    'BtzuNHP4FpGhHGZ5LUNLJ7IoOiw34DnQipzAXXwnMbgijCMtgd4azVIU_zTu8XJPaswiUdmpLZfEahVBn_bNBT7YXEsozHhRGb1Air7s0JwRm_bMEvxwAKKVTWya545DD14W3cbLLKReU4k5Gh6VxCyTv2yY3b6ThpuKwQJWGJSJEOrvnz_wskNDeGG6',
} as const;

const SECRET = 'omi_mcp_7f3c0a9e1b2d4c5e6f708192a3b4c5d6';

/** Independent receiver: decrypt exactly as the protocol describes. */
async function receive(fragment: string, request: { ciphertext: string; nonce: string }) {
  const [version, keyText, tokenText] = fragment.split('.');
  expect(version).toBe('v1');
  const key = await crypto.subtle.importKey(
    'raw',
    base64UrlToBytes(keyText) as BufferSource,
    'AES-GCM',
    false,
    ['decrypt'],
  );
  const plaintext = await crypto.subtle.decrypt(
    {
      name: 'AES-GCM',
      iv: base64UrlToBytes(request.nonce) as BufferSource,
      additionalData: new TextEncoder().encode('zk-relay/v1;envelope'),
      tagLength: 128,
    },
    key,
    base64UrlToBytes(request.ciphertext) as BufferSource,
  );
  const envelope = JSON.parse(new TextDecoder().decode(plaintext));
  return {
    envelope,
    secret: new TextDecoder().decode(base64UrlToBytes(envelope.data)),
    tokenText,
    keyText,
  };
}

describe('zkr v1 encryption', () => {
  it('matches the reference test vector byte for byte', async () => {
    expect(textEnvelope('zk-relay-interoperability')).toEqual(VECTOR.envelope);
    const ciphertext = await encryptEnvelope(
      textEnvelope('zk-relay-interoperability'),
      base64UrlToBytes(VECTOR.key),
      base64UrlToBytes(VECTOR.nonce),
    );
    expect(bytesToBase64Url(ciphertext)).toBe(VECTOR.ciphertext);
    expect(ZKR_AAD).toBe('zk-relay/v1;envelope');
  });

  it('round-trips a key through the create request and link fragment', async () => {
    const { request, fragment } = await prepareZkrShare(SECRET);
    const received = await receive(fragment, request);

    expect(received.secret).toBe(SECRET);
    expect(received.envelope).toMatchObject({ v: 1, kind: 'text' });
    // The server stores SHA-256(T), never T.
    const digest = await crypto.subtle.digest(
      'SHA-256',
      base64UrlToBytes(received.tokenText) as BufferSource,
    );
    expect(request.accessTokenHash).toBe(bytesToBase64Url(new Uint8Array(digest)));
    expect(base64UrlToBytes(received.keyText)).toHaveLength(32);
    expect(base64UrlToBytes(request.nonce)).toHaveLength(12);
    expect(request).toMatchObject({ expiresInSeconds: 3600, expireAfterReveal: true });
  });

  it('uses fresh key material for every share', async () => {
    const a = await prepareZkrShare(SECRET);
    const b = await prepareZkrShare(SECRET);
    expect(a.fragment).not.toBe(b.fragment);
    expect(a.request.nonce).not.toBe(b.request.nonce);
    expect(a.request.ciphertext).not.toBe(b.request.ciphertext);
  });
});

describe('createZkrShare', () => {
  it('sends only ciphertext to the relay and keeps K and T in the fragment', async () => {
    const fetchImpl = vi.fn(async (_url: string, _init?: RequestInit) =>
      Response.json({ id: 'AbCdEfGhIjKlMnOpQrStUv', expiresAt: '2026-10-14T02:00:00Z' }),
    );
    const share = await createZkrShare(SECRET, { fetchImpl: fetchImpl });

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe(ZKR_CREATE_ENDPOINT);
    const body = String(init?.body);
    const fragment = share.agentLink.split('#')[1];
    const [, keyText, tokenText] = fragment.split('.');
    expect(body).not.toContain(SECRET);
    expect(body).not.toContain(bytesToBase64Url(new TextEncoder().encode(SECRET)));
    expect(body).not.toContain(keyText);
    expect(body).not.toContain(tokenText);
    expect(Object.keys(JSON.parse(body)).sort()).toEqual([
      'accessTokenHash',
      'ciphertext',
      'expireAfterReveal',
      'expiresInSeconds',
      'nonce',
      'v',
    ]);

    expect(share.agentLink).toMatch(
      /^https:\/\/zkr\.scalingforever\.com\/a\/AbCdEfGhIjKlMnOpQrStUv#v1\.[A-Za-z0-9_-]{43}\.[A-Za-z0-9_-]{43}$/,
    );
    expect(share.humanLink).toContain('/h/AbCdEfGhIjKlMnOpQrStUv#v1.');
    expect((await receive(fragment, JSON.parse(body))).secret).toBe(SECRET);
  });

  it('fails closed on a relay error or a malformed id', async () => {
    await expect(
      createZkrShare(SECRET, {
        fetchImpl: async () => new Response('', { status: 502 }),
      }),
    ).rejects.toThrow('Secure link failed (502)');
    await expect(
      createZkrShare(SECRET, {
        fetchImpl: async () => Response.json({ id: '../x' }),
      }),
    ).rejects.toThrow('invalid response');
  });
});

describe('isRelayableZkrRequest', () => {
  it('accepts exactly a one-hour expire-after-reveal key share', async () => {
    const { request } = await prepareZkrShare(SECRET);
    expect(isRelayableZkrRequest(request)).toBe(true);
    expect(isRelayableZkrRequest({ ...request, expiresInSeconds: 604800 })).toBe(false);
    expect(isRelayableZkrRequest({ ...request, expireAfterReveal: false })).toBe(false);
    expect(isRelayableZkrRequest({ ...request, plaintext: SECRET })).toBe(false);
    expect(isRelayableZkrRequest({ ...request, ciphertext: 'A'.repeat(5000) })).toBe(
      false,
    );
    expect(isRelayableZkrRequest({ ...request, nonce: 'AAAA' })).toBe(false);
    expect(isRelayableZkrRequest(null)).toBe(false);
  });
});
