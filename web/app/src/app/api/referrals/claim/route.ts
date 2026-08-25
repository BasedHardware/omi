import { moonshineJson } from '@tschk/moonshine-next/server';

const REFERRAL_BACKENDS = {
  dev: 'https://api.omiapi.com',
  prod: 'https://api.omi.me',
} as const;

type ReferralEnvironment = keyof typeof REFERRAL_BACKENDS;

export function referralBackendOrigin(environment: string): string | null {
  return environment in REFERRAL_BACKENDS
    ? REFERRAL_BACKENDS[environment as ReferralEnvironment]
    : null;
}

export async function POST(request: Request) {
  const authorization = request.headers.get('Authorization');
  if (!authorization) {
    return moonshineJson({ error: 'Authorization header required' }, { status: 401 });
  }

  let body: { code?: unknown; environment?: unknown };
  try {
    body = await request.json();
  } catch {
    return moonshineJson({ error: 'Invalid request body' }, { status: 400 });
  }

  if (typeof body.code !== 'string' || typeof body.environment !== 'string') {
    return moonshineJson({ error: 'Invalid referral claim' }, { status: 400 });
  }
  const backendOrigin = referralBackendOrigin(body.environment);
  if (!backendOrigin) {
    return moonshineJson({ error: 'Invalid referral environment' }, { status: 400 });
  }

  try {
    const response = await fetch(`${backendOrigin}/v1/users/me/referral/claim`, {
      method: 'POST',
      headers: {
        Authorization: authorization,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ code: body.code }),
      signal: AbortSignal.timeout(10_000),
    });
    const responseBody = await response.text();
    return new Response(responseBody, {
      status: response.status,
      headers: {
        'Content-Type':
          response.headers.get('content-type') || 'application/json; charset=utf-8',
        'Cache-Control': 'no-store',
      },
    });
  } catch {
    return moonshineJson({ error: 'Referral service unavailable' }, { status: 502 });
  }
}
