import { NextRequest, NextResponse } from 'next/server';

/**
 * API proxy — browser → this route → the Omi backend.
 *
 * Mirrors `web/app/src/app/api/proxy/[...path]/route.ts`: it exists so the browser
 * never talks to `api.omi.me` cross-origin, and it forwards the caller's Firebase ID
 * token untouched. It adds no credentials of its own — a request without an
 * Authorization header is refused here rather than sent on unauthenticated.
 *
 * GET only. PAPER reads; it does not write.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.omi.me';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;

  const authHeader = request.headers.get('Authorization');
  if (!authHeader) {
    return NextResponse.json({ error: 'Authorization header required' }, { status: 401 });
  }

  const searchParams = request.nextUrl.searchParams.toString();
  const url = `${API_BASE_URL}/${path.join('/')}${searchParams ? `?${searchParams}` : ''}`;

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { Authorization: authHeader },
    });

    const contentType = response.headers.get('content-type');

    if (contentType?.includes('application/json')) {
      const data = await response.json();
      return NextResponse.json(data, { status: response.status });
    }

    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: { 'Content-Type': contentType || 'text/plain' },
    });
  } catch (error) {
    // The URL can carry a token in a query string on some endpoints; log the failure
    // reason only, never the request.
    console.error('Proxy error:', error instanceof Error ? error.message : 'unknown');
    return NextResponse.json(
      { error: 'Could not reach the Omi backend.' },
      { status: 502 },
    );
  }
}
