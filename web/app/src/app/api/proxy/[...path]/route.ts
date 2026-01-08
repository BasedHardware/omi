import { NextRequest, NextResponse } from 'next/server';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.omi.me';

/**
 * API Proxy to avoid CORS issues during development
 * Forwards requests from /api/proxy/* to https://api.omi.me/*
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return handleRequest(request, await params);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return handleRequest(request, await params);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return handleRequest(request, await params);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return handleRequest(request, await params);
}

async function handleRequest(
  request: NextRequest,
  params: { path: string[] }
) {
  try {
    const path = params.path.join('/');
    const searchParams = request.nextUrl.searchParams.toString();
    const url = `${API_BASE_URL}/${path}${searchParams ? `?${searchParams}` : ''}`;

    // Get auth header from incoming request
    const authHeader = request.headers.get('Authorization');

    if (!authHeader) {
      return NextResponse.json(
        { error: 'Authorization header required' },
        { status: 401 }
      );
    }

    // Check if this is a multipart form data request
    const contentType = request.headers.get('content-type') || '';
    const isMultipart = contentType.includes('multipart/form-data');

    // Build headers - don't set Content-Type for multipart (let fetch set it with boundary)
    const headers: HeadersInit = {
      'Authorization': authHeader,
    };

    // Forward custom headers for FCM token registration
    const appPlatform = request.headers.get('X-App-Platform');
    const deviceIdHash = request.headers.get('X-Device-Id-Hash');
    if (appPlatform) {
      headers['X-App-Platform'] = appPlatform;
    }
    if (deviceIdHash) {
      headers['X-Device-Id-Hash'] = deviceIdHash;
    }

    if (!isMultipart && request.method !== 'GET' && request.method !== 'DELETE') {
      headers['Content-Type'] = 'application/json';
    }

    const fetchOptions: RequestInit = {
      method: request.method,
      headers,
    };

    // Include body for POST/PATCH requests
    if (request.method === 'POST' || request.method === 'PATCH') {
      if (isMultipart) {
        // For multipart, forward the FormData directly
        const formData = await request.formData();
        fetchOptions.body = formData;
      } else {
        const body = await request.text();
        if (body) {
          fetchOptions.body = body;
        }
      }
    }

    const response = await fetch(url, fetchOptions);

    // Handle 204 No Content responses (common for DELETE)
    if (response.status === 204) {
      return new NextResponse(null, { status: 204 });
    }

    // Get response data
    const responseContentType = response.headers.get('content-type');

    // Handle streaming responses (for chat)
    if (responseContentType?.includes('text/event-stream') ||
        responseContentType?.includes('text/plain')) {
      const text = await response.text();
      return new NextResponse(text, {
        status: response.status,
        headers: {
          'Content-Type': responseContentType || 'text/plain',
        },
      });
    }

    // Handle JSON responses
    if (responseContentType?.includes('application/json')) {
      const data = await response.json();

      // Add Cache-Control headers for static/rarely-changing endpoints
      const cacheHeaders: HeadersInit = {};
      if (
        path.includes('app-categories') ||
        path.includes('app-capabilities') ||
        path.includes('app/plans')
      ) {
        // Static reference data - cache for 1 hour
        cacheHeaders['Cache-Control'] = 'public, max-age=3600, stale-while-revalidate=86400';
      } else if (path.includes('folders') && request.method === 'GET') {
        // User folders - cache briefly with revalidation
        cacheHeaders['Cache-Control'] = 'private, max-age=60, stale-while-revalidate=300';
      }

      return NextResponse.json(data, {
        status: response.status,
        headers: cacheHeaders,
      });
    }

    // Default: return as text
    const data = await response.text();
    return new NextResponse(data, {
      status: response.status,
      headers: {
        'Content-Type': responseContentType || 'text/plain',
      },
    });
  } catch (error) {
    console.error('Proxy error:', error);
    return NextResponse.json(
      { error: 'Proxy request failed' },
      { status: 500 }
    );
  }
}
