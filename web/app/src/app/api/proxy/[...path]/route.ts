import { moonshineJson } from '@tschk/moonshine-next/server';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.omi.me';

/**
 * API Proxy to avoid CORS issues during development
 * Forwards requests from /api/proxy/* to https://api.omi.me/*
 */
export async function GET(request: Request) {
  return handleRequest(request);
}

export async function POST(request: Request) {
  return handleRequest(request);
}

export async function PATCH(request: Request) {
  return handleRequest(request);
}

export async function DELETE(request: Request) {
  return handleRequest(request);
}

async function handleRequest(request: Request) {
  try {
    const requestUrl = new URL(request.url);
    const path = requestUrl.pathname.slice('/api/proxy/'.length);
    const searchParams = requestUrl.searchParams.toString();
    const url = `${API_BASE_URL}/${path}${searchParams ? `?${searchParams}` : ''}`;

    // Get auth header from incoming request
    const authHeader = request.headers.get('Authorization');

    if (!authHeader) {
      return moonshineJson({ error: 'Authorization header required' }, { status: 401 });
    }

    // Check if this is a multipart form data request
    const contentType = request.headers.get('content-type') || '';
    const isMultipart = contentType.includes('multipart/form-data');

    // Build headers - don't set Content-Type for multipart (let fetch set it with boundary)
    const headers: HeadersInit = {
      Authorization: authHeader,
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

    if (!isMultipart && request.method !== 'GET') {
      headers['Content-Type'] = 'application/json';
    }

    const fetchOptions: RequestInit = {
      method: request.method,
      headers,
    };

    // Include body for POST/PATCH/DELETE requests
    if (
      request.method === 'POST' ||
      request.method === 'PATCH' ||
      request.method === 'DELETE'
    ) {
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
      return new Response(null, { status: 204 });
    }

    // Get response data
    const responseContentType = response.headers.get('content-type');

    // Handle streaming responses (for chat)
    if (
      responseContentType?.includes('text/event-stream') ||
      responseContentType?.includes('text/plain')
    ) {
      const text = await response.text();
      return new Response(text, {
        status: response.status,
        headers: {
          'Content-Type': responseContentType || 'text/plain',
        },
      });
    }

    // Handle download/streaming responses (e.g., data export) — pass body through without buffering
    const contentDisposition = response.headers.get('content-disposition');
    if (contentDisposition) {
      return new Response(response.body, {
        status: response.status,
        headers: {
          'Content-Type': responseContentType || 'application/octet-stream',
          'Content-Disposition': contentDisposition,
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
        cacheHeaders['Cache-Control'] =
          'public, max-age=3600, stale-while-revalidate=86400';
      }

      return moonshineJson(data, {
        status: response.status,
        headers: cacheHeaders,
      });
    }

    // Default: return as text
    const data = await response.text();
    return new Response(data, {
      status: response.status,
      headers: {
        'Content-Type': responseContentType || 'text/plain',
      },
    });
  } catch (error) {
    console.error('Proxy error:', error);
    return moonshineJson({ error: 'Proxy request failed' }, { status: 500 });
  }
}
