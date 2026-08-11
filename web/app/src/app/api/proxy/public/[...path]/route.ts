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

/**
 * How long to wait on the backend before giving up.
 *
 * Without this a slow upstream holds a connection here open for as long as it
 * likes, so backend latency becomes exhausted web-server connections. This is
 * the one risk the hop actually adds: the endpoints below are already public on
 * the API origin, so proxying them grants no access and offers no amplification
 * over calling the backend directly, which is why there is no separate rate
 * limit here.
 */
const UPSTREAM_TIMEOUT_MS = 10_000;

/**
 * Public catalogue data changes rarely, and every uncached request is a backend
 * round trip on a page anyone can load. Only successful responses are cached —
 * a cached error would outlive the outage that produced it.
 */
const SUCCESS_CACHE_CONTROL = 'public, max-age=60, stale-while-revalidate=300';
const FAIR_USE_STATUS_PATH = /^v1\/fair-use\/case\/[^/]+\/status$/;

export function publicProxyCacheControl(
  path: string,
  succeeded: boolean,
): string | undefined {
  if (FAIR_USE_STATUS_PATH.test(path)) return 'no-store';
  return succeeded ? SUCCESS_CACHE_CONTROL : undefined;
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
    const response = await fetch(url, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
    const body = await response.text();
    const headers: Record<string, string> = {
      'Content-Type':
        response.headers.get('content-type') || 'application/json; charset=utf-8',
    };
    const cacheControl = publicProxyCacheControl(path, response.ok);
    if (cacheControl) headers['Cache-Control'] = cacheControl;
    return new Response(body, { status: response.status, headers });
  } catch (error) {
    console.error('Public proxy error:', error);
    return moonshineJson({ error: 'Proxy request failed' }, { status: 502 });
  }
}
