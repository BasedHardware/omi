import { NextResponse } from 'next/server';

const rapidApiKey = process.env.RAPIDAPI_KEY;
const rapidApiHost = process.env.RAPIDAPI_HOST;
const linkedinApiKey = process.env.LINKEDIN_API_KEY;
const linkedinApiHost = process.env.LINKEDIN_API_HOST;

const rapidApiHeaders = (key?: string, host?: string) => {
  if (!key || !host) return null;
  return {
    'x-rapidapi-key': key,
    'x-rapidapi-host': host,
  };
};

export async function GET(req: Request) {
  const url = new URL(req.url);
  const provider = url.searchParams.get('provider');
  const username = url.searchParams.get('username')?.trim();

  if (!username) {
    return NextResponse.json({ error: 'Missing username' }, { status: 400 });
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
