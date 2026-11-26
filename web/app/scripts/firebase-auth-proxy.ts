/** Firebase's redirect helper must share the app's origin on Safari. */
export function createFirebaseAuthProxy(
  projectId: string,
  upstreamFetch: typeof fetch = globalThis.fetch,
): (request: Request) => Promise<Response | null> {
  // The upstream is deployment configuration, never a request-supplied host.
  const origin = /^[a-z0-9][a-z0-9-]*$/.test(projectId)
    ? `https://${projectId}.firebaseapp.com`
    : null;
  return async (request) => {
    const url = new URL(request.url);
    if (
      !url.pathname.startsWith('/__/auth/') &&
      url.pathname !== '/__/firebase/init.json'
    ) {
      return null;
    }
    if (!origin) return new Response('Firebase auth is not configured', { status: 503 });
    if (request.method !== 'GET' && request.method !== 'POST') {
      return new Response('Method not allowed', {
        status: 405,
        headers: { Allow: 'GET, POST' },
      });
    }
    const headers = new Headers();
    for (const name of ['accept', 'content-type']) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    try {
      const response = await upstreamFetch(`${origin}${url.pathname}${url.search}`, {
        method: request.method,
        headers,
        body: request.method === 'POST' ? await request.arrayBuffer() : undefined,
        redirect: 'manual',
        signal: AbortSignal.timeout(15000),
      });
      const responseHeaders = new Headers(response.headers);
      // Fetch decodes compressed bodies; stale wire lengths/encodings corrupt them.
      responseHeaders.delete('content-encoding');
      responseHeaders.delete('content-length');
      responseHeaders.set('Cache-Control', 'no-store');
      // Only this SDK helper may be framed, and only by our own app.
      responseHeaders.set('X-Frame-Options', 'SAMEORIGIN');
      const csp = responseHeaders.get('Content-Security-Policy');
      const directives = (csp ?? '')
        .split(';')
        .map((part) => part.trim())
        .filter((part) => part && !/^frame-ancestors(?:\s|$)/i.test(part));
      directives.push("frame-ancestors 'self'");
      responseHeaders.set('Content-Security-Policy', directives.join('; '));
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });
    } catch {
      return new Response('Firebase auth helper unavailable', { status: 502 });
    }
  };
}
