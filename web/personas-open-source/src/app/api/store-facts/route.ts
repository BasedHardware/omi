import { NextResponse } from 'next/server';
import Redis from 'ioredis';

// ... Redis client config ...

interface PostBody {
  uid: string;
  memories: string[];
}

export async function POST(req: Request) {
  let connectedRedis = false;
  try {
    console.log('[store-facts] Received request');
    const { uid, memories } = (await req.json()) as PostBody;
    console.log(`[store-facts] Processing request for UID: ${uid}, Memories count: ${memories?.length}`);

    if (!uid || !Array.isArray(memories) || memories.length === 0) {
      console.warn('[store-facts] Invalid request body:', { uid, memories });
      return NextResponse.json({ error: 'Invalid request body' }, { status: 400 });
    }

    const appId = process.env.OMI_APP_ID || process.env.NEXT_PUBLIC_OMI_APP_ID;
    const apiKey = process.env.OMI_API_KEY || process.env.NEXT_PUBLIC_OMI_API_KEY;

    if (!appId || !apiKey) {
      console.error('[store-facts] OMI_APP_ID or OMI_API_KEY missing!');
      return NextResponse.json({ error: 'Server misconfiguration' }, { status: 500 });
    }

    const url = `https://api.omi.me/v2/integrations/${appId}/user/facts?uid=${uid}`;
    const headers = {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    } as const;
    console.log(`[store-facts] OMI API Endpoint: ${url}`);

    const results: { text: string; success: boolean; status?: number; error?: string }[] = [];

    for (const memory of memories) {
      const payload = JSON.stringify({ text: memory, text_source: 'other' });
      console.log(`[store-facts] Sending memory to OMI: ${memory.substring(0, 50)}...`);
      try {
        const res = await fetch(url, {
          method: 'POST',
          headers,
          body: payload,
        });

        console.log(`[store-facts] OMI API Response Status for memory: ${res.status}`);
        if (!res.ok) {
          const errorText = await res.text();
          console.error(`[store-facts] OMI API Error (${res.status}): ${errorText}`);
          results.push({ text: memory.substring(0, 50), success: false, status: res.status, error: errorText });
        } else {
          results.push({ text: memory.substring(0, 50), success: true, status: res.status });
        }
      } catch (fetchErr: any) {
        console.error(`[store-facts] Fetch error sending memory to OMI: ${fetchErr.message}`, fetchErr);
        results.push({ text: memory.substring(0, 50), success: false, error: fetchErr.message });
      }
    }

    console.log('[store-facts] Finished processing memories. Results:', results);
    return NextResponse.json({ results });

  } catch (err: any) {
    console.error('[store-facts] Unexpected error in route handler:', err);
    return NextResponse.json(
      { error: 'Unknown server error', details: err.message, stack: err.stack },
      { status: 500 }
    );
  }
} 