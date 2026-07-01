import { NextResponse } from 'next/server';

const rapidApiKey = process.env.RAPIDAPI_KEY;
const rapidApiHost = process.env.RAPIDAPI_HOST;
const linkedinApiKey = process.env.LINKEDIN_API_KEY;
const linkedinApiHost = process.env.LINKEDIN_API_HOST;

const MAX_USERNAME_LENGTH = 64;
const RATE_LIMIT_WINDOW_MS = 60_000;
const RATE_LIMIT_MAX_REQUESTS = 30;
const rateLimits = new Map<string, { count: number; resetAt: number }>();

const rapidApiHeaders = (key?: string, host?: string) => {
  if (!key || !host) return null;
  return {
    'x-rapidapi-key': key,
    'x-rapidapi-host': host,
  };
};

const clientIp = (req: Request) => {
  const forwardedFor = req.headers.get('x-forwarded-for');
  if (forwardedFor) return forwardedFor.split(',')[0]?.trim() || 'unknown';
  return req.headers.get('x-real-ip') || 'unknown';
};

const isRateLimited = (key: string) => {
  const now = Date.now();
  if (rateLimits.size > 1000) {
    for (const [entryKey, entry] of rateLimits) {
      if (entry.resetAt <= now) rateLimits.delete(entryKey);
    }
  }

  const current = rateLimits.get(key);

  if (!current || current.resetAt <= now) {
    rateLimits.set(key, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS });
    return false;
  }

  current.count += 1;
  return current.count > RATE_LIMIT_MAX_REQUESTS;
};

export async function GET(req: Request) {
  const url = new URL(req.url);
  const provider = url.searchParams.get('provider');
  const username = url.searchParams.get('username')?.trim();

  if (!username) {
    return NextResponse.json({ error: 'Missing username' }, { status: 400 });
  }

  if (username.length > MAX_USERNAME_LENGTH) {
    return NextResponse.json({ error: 'Invalid username' }, { status: 400 });
  }

  if (isRateLimited(clientIp(req))) {
    return NextResponse.json({ error: 'Rate limit exceeded' }, { status: 429 });
  }

  let upstreamUrl: string;
  let headers: Record<string, string> | null;

  if (provider === 'twitter-profile') {
    headers = rapidApiHeaders(rapidApiKey, rapidApiHost);
    upstreamUrl = `https://${rapidApiHost}/screenname.php?screenname=${encodeURIComponent(
      username,
    )}`;
  } else if (provider === 'twitter-timeline') {
    headers = rapidApiHeaders(rapidApiKey, rapidApiHost);
    upstreamUrl = `https://${rapidApiHost}/timeline.php?screenname=${encodeURIComponent(
      username,
    )}`;
  } else if (provider === 'linkedin-profile') {
    headers = rapidApiHeaders(linkedinApiKey, linkedinApiHost);
    upstreamUrl = `https://${linkedinApiHost}/profile-data-connection-count-posts?username=${encodeURIComponent(
      username,
    )}`;
  } else {
    return NextResponse.json({ error: 'Unsupported provider' }, { status: 400 });
  }

  if (!headers) {
    return NextResponse.json({ error: 'Server misconfiguration' }, { status: 500 });
  }

  const response = await fetch(upstreamUrl, { headers });
  const data = await response.text();

  return new NextResponse(data, {
    status: response.status,
    headers: {
      'Content-Type': response.headers.get('Content-Type') || 'application/json',
    },
  });
}
