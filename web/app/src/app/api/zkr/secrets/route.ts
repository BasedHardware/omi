import { moonshineJson } from '@tschk/moonshine-next/server';
import { ZKR_ORIGIN, isRelayableZkrRequest } from '@/lib/zkr';

// Ciphertext-only relay for the zkr create call. The browser encrypts the key
// and keeps the AES key and access token in the link fragment; this route sees
// only what zkr itself would see. It exists because zkr sends no CORS headers,
// so a browser cannot read the share id from a cross-origin create.

export async function POST(request: Request) {
  // Browsers always label fetch metadata; a cross-site page must not be able
  // to use this route as a free relay.
  const site = request.headers.get('Sec-Fetch-Site');
  if (site && site !== 'same-origin') {
    return moonshineJson({ error: 'Forbidden' }, { status: 403 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return moonshineJson({ error: 'Invalid request body' }, { status: 400 });
  }
  if (!isRelayableZkrRequest(body)) {
    return moonshineJson({ error: 'Invalid secure-link request' }, { status: 400 });
  }

  try {
    const response = await fetch(`${ZKR_ORIGIN}/api/v1/secrets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(10_000),
    });
    const created = (await response.json().catch(() => null)) as {
      id?: unknown;
      expiresAt?: unknown;
    } | null;
    if (!response.ok || typeof created?.id !== 'string') {
      return moonshineJson(
        { error: 'Secure link service rejected the request' },
        { status: response.status === 429 ? 429 : 502 },
      );
    }
    return moonshineJson(
      { id: created.id, expiresAt: created.expiresAt },
      { status: 201, headers: { 'Cache-Control': 'no-store' } },
    );
  } catch {
    return moonshineJson({ error: 'Secure link service unavailable' }, { status: 502 });
  }
}
