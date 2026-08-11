import { MEMORY_PLATFORM_LIMITS } from '@/src/lib/api/memory-platform';

export const API_HOST = 'https://api.omi.me';

export const capabilitySnippet = `curl ${API_HOST}/v1/memory/platform \\
  -H "Authorization: Bearer $OMI_SESSION"`;

export const searchSnippet = `curl -G ${API_HOST}/v1/memory/platform/search \\
  -H "Authorization: Bearer $OMI_SESSION" \\
  --data-urlencode "query=the next launch" \\
  --data-urlencode "limit=20"`;

export const ingestSnippet = `curl -X POST ${API_HOST}/v1/memory/platform/ingest \\
  -H "Authorization: Bearer $OMI_SESSION" \\
  -H "Content-Type: application/json" \\
  -d '{"content":"The next launch is Thursday","category":"manual"}'`;

export const boundsSummary = `query ≤ ${
  MEMORY_PLATFORM_LIMITS.maxQueryLength
} characters · limit ${MEMORY_PLATFORM_LIMITS.minLimit}–${
  MEMORY_PLATFORM_LIMITS.maxLimit
} (default ${MEMORY_PLATFORM_LIMITS.defaultLimit}) · offset ${
  MEMORY_PLATFORM_LIMITS.minOffset
}–${MEMORY_PLATFORM_LIMITS.maxOffset.toLocaleString('en-US')}`;

export const MCP_ENDPOINT = `${API_HOST}/v1/mcp/sse`;

export const mcpClientSnippet = `{
  "mcpServers": {
    "omi": {
      "url": "${MCP_ENDPOINT}",
      "headers": { "Authorization": "Bearer \${OMI_MCP_KEY}" }
    }
  }
}`;

/**
 * The published iframe never pairs allow-scripts with allow-same-origin: a
 * framed document granted both can remove its own sandbox attribute.
 */
export const iframeSnippet = `<iframe
  id="omi-memory"
  src="https://your-app.example/omi-memory"
  title="Omi memory"
  loading="lazy"
  referrerpolicy="strict-origin-when-cross-origin"
  sandbox="allow-scripts"
  style="width:100%;height:560px;border:0"
></iframe>`;

// /v1/memory/platform/* authenticates with get_current_user_uid, which accepts
// only Firebase ID tokens — it rejects MCP and Developer key families. There is
// no durable server key for this route, so the proxy forwards the *visitor's*
// own refreshable session rather than a static credential.
export const proxySnippet = `// app/api/memory/route.ts — runs on your server, never in the browser
export async function GET(request: Request) {
  // Your auth and your tenant check. omiIdToken is the visitor's current Omi
  // Firebase ID token, refreshed by your session layer — never a durable key.
  const { omiIdToken } = await requireSession(request);
  const q = new URL(request.url).searchParams.get('q') ?? '';

  const upstream = await fetch(
    '${API_HOST}/v1/memory/platform/search?' +
      new URLSearchParams({ query: q.slice(0, ${MEMORY_PLATFORM_LIMITS.maxQueryLength}), limit: '20' }),
    { headers: { Authorization: \`Bearer \${omiIdToken}\` } },
  );

  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { 'content-type': 'application/json' },
  });
}`;

// The sandboxed frame has an opaque origin, so every message it sends carries
// event.origin === 'null'. An origin allowlist cannot identify the sender;
// event.source can, because only that frame's window is its contentWindow.
export const postMessageSnippet = `const frame = document.querySelector('#omi-memory');

window.addEventListener('message', (event) => {
  // The sandboxed frame's origin is the opaque 'null', so validate the SENDER.
  if (event.source !== frame.contentWindow) return;
  const data = event.data;

  // Hand the frame a session it cannot obtain itself: no storage, no cookies.
  if (data?.type === 'omi.memory.embed.session-request') {
    // Minted server-side for the visitor you already authenticated.
    fetch('/api/omi-session')
      .then((response) => response.json())
      .then(({ token }) => {
        frame.contentWindow.postMessage(
          { type: 'omi.memory.embed.session', token },
          '*', // an opaque-origin frame cannot be addressed by origin
        );
      });
    return;
  }

  if (data?.type !== 'omi.memory.embed.resize') return;
  frame.style.height = \`\${Number(data.height) || 560}px\`;
});`;

export const cspSnippet = `Content-Security-Policy: frame-ancestors https://your-app.example https://app.your-app.example`;

export const securityChecklist = [
  'Use a server-side proxy or a short-lived, narrowly scoped session.',
  'Never place Omi API keys in source, browser storage, or public environment variables.',
  'Validate event.source on every postMessage event; a sandboxed frame reports origin "null".',
  'Set frame-ancestors to the exact parent origins you control.',
  'Keep writes explicit and user-initiated; default to memories.read.',
  'Treat local zkr or SQLite as a cache or pending buffer, never as authority.',
];
