import { moonshineJson } from '@tschk/moonshine-next/server';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.omi.me';

/**
 * Same-origin passthrough for the *unauthenticated* backend endpoints the
 * public pages read (marketplace, fair-use case status).
 *
 * The sibling `/api/proxy/[...path]` route rejects every request without an
 * Authorization header, and the backend sends no CORS headers by default
 * (`CORS_ALLOWED_ORIGINS` is empty in `backend/main.py`), so a browser on the
 * web origin can reach these endpoints only through a same-origin server hop.
 * Static `public` outranks the sibling catch-all in the router's segment
 * precedence, so this handler wins for `/api/proxy/public/*`.
 *
 * The allowlist keeps this from becoming an open, credential-free relay for
 * the whole API: only exact public read paths are forwarded.
 */
const PUBLIC_PATH_PATTERNS: RegExp[] = [
  /^v1\/approved-apps$/,
  /^v2\/apps$/,
  /^v1\/fair-use\/case\/[^/]+\/status$/,
];

export function isPublicProxyPath(path: string): boolean {
  return PUBLIC_PATH_PATTERNS.some((pattern) => pattern.test(path));
}

export async function GET(request: Request) {
  const requestUrl = new URL(request.url);
  const path = requestUrl.pathname.slice('/api/proxy/public/'.length);

  if (!isPublicProxyPath(path)) {
    return moonshineJson({ error: 'Not a public endpoint' }, { status: 404 });
  }

  const searchParams = requestUrl.searchParams.toString();
  const url = `${API_BASE_URL}/${path}${searchParams ? `?${searchParams}` : ''}`;

  try {
    const response = await fetch(url, { headers: { Accept: 'application/json' } });
    const body = await response.text();
    return new Response(body, {
      status: response.status,
      headers: {
        'Content-Type':
          response.headers.get('content-type') || 'application/json; charset=utf-8',
      },
    });
  } catch (error) {
    console.error('Public proxy error:', error);
    return moonshineJson({ error: 'Proxy request failed' }, { status: 502 });
  }
}
