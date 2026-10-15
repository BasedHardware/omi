import { NextRequest, NextResponse } from 'next/server';
import { shareLinkHeader, shareRepresentation } from './lib/shared-export.mjs';
import { ITEM_LIST_QUERY_HEADER } from './lib/item-link.mjs';

export function proxy(request: NextRequest) {
  if (request.method !== 'GET' && request.method !== 'HEAD') return NextResponse.next();
  if (request.nextUrl.pathname === '/items') return itemListRequest(request);
  const match = /^\/conversations\/([^/]+)$/.exec(request.nextUrl.pathname);
  if (!match) return NextResponse.next();
  const suffix = /\.(md|json)$/.exec(match[1]);
  const id = suffix ? match[1].slice(0, -suffix[0].length) : match[1];
  let decodedId: string;
  try {
    decodedId = decodeURIComponent(id);
  } catch {
    return new NextResponse('Bad Request', {
      status: 400,
      headers: { Vary: 'Accept', 'Cache-Control': 'private, no-store' },
    });
  }
  const type = suffix
    ? suffix[1] === 'md'
      ? 'text/markdown'
      : 'application/json'
    : shareRepresentation(request.headers.get('accept') || '');
  if (!type) {
    return new NextResponse('Not Acceptable', {
      status: 406,
      headers: { Vary: 'Accept', 'Cache-Control': 'private, no-store' },
    });
  }
  let response;
  if (type === 'text/html') {
    response = NextResponse.next();
  } else {
    const destination = request.nextUrl.clone();
    destination.pathname = `/share-export/${id}`;
    destination.search = '';
    destination.searchParams.set('format', type === 'text/markdown' ? 'md' : 'json');
    response = NextResponse.rewrite(destination);
  }
  response.headers.set('Vary', 'Accept');
  response.headers.set('Link', shareLinkHeader(decodedId));
  // Sharing can be revoked. Do not let intermediary caches retain a public body.
  response.headers.set('Cache-Control', 'private, no-store');
  return response;
}

/**
 * /items keeps its display order in the raw query (repeated, interleaved keys),
 * which a parsed searchParams object loses. Hand the page the raw string,
 * always overwriting any client-sent copy of the header.
 */
function itemListRequest(request: NextRequest) {
  const forwarded = new Headers(request.headers);
  forwarded.set(ITEM_LIST_QUERY_HEADER, request.nextUrl.search.replace(/^\?/, ''));
  return NextResponse.next({ request: { headers: forwarded } });
}

export const config = { matcher: ['/conversations/:path*', '/items'] };
