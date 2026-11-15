// Synthetic upstream only. This file is mounted into the exact Linux image;
// Docker networking is disabled and generated product code is never edited.
import { appendFileSync } from 'node:fs';
globalThis.fetch = (async (input, options) => {
  const url = String(input instanceof Request ? input.url : input);
  if (!url.startsWith(`https://${process.env.PROBE_HOST}/__/`)) {
    throw new Error('Non-helper outbound fetch blocked');
  }
  appendFileSync(process.env.PROBE_CAPTURE!, JSON.stringify({
    url, method: options?.method, redirect: options?.redirect,
    headers: Object.fromEntries(new Headers(options?.headers).entries()),
    body: options?.body ? Buffer.from(options.body as ArrayBuffer).toString('base64') : null,
  }) + '\n');
  return new Response(options?.method === 'POST' ? null : 'synthetic-helper-response', {
    status: options?.method === 'POST' ? 302 : 200,
    headers: {
      'content-type': 'text/html',
      'content-security-policy': "script-src 'self'; frame-ancestors 'none'",
      ...(options?.method === 'POST' ? { location: 'https://accounts.google.com/synthetic-probe' } : {}),
    },
  });
}) as typeof fetch;
