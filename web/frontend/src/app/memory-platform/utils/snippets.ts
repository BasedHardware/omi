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

export const mcpClientSnippet = `{
  "mcpServers": {
    "omi": {
      "url": "https://api.omi.me/mcp",
      "headers": { "Authorization": "Bearer \${OMI_MCP_KEY}" }
    }
  }
}`;

/**
 * The published iframe never pairs allow-scripts with allow-same-origin: a
 * framed document granted both can remove its own sandbox attribute.
 */
export const iframeSnippet = `<iframe
  src="https://your-app.example/omi-memory"
  title="Omi memory"
  loading="lazy"
  referrerpolicy="strict-origin-when-cross-origin"
  sandbox="allow-scripts"
  style="width:100%;height:560px;border:0"
></iframe>`;

export const proxySnippet = `// app/api/memory/route.ts — runs on your server, never in the browser
export async function GET(request: Request) {
  const session = await requireSession(request); // your auth, your tenant check
  const q = new URL(request.url).searchParams.get('q') ?? '';

  const upstream = await fetch(
    '${API_HOST}/v1/memory/platform/search?' +
      new URLSearchParams({ query: q.slice(0, ${MEMORY_PLATFORM_LIMITS.maxQueryLength}), limit: '20' }),
    { headers: { Authorization: \`Bearer \${process.env.OMI_SERVER_KEY}\` } },
  );

  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { 'content-type': 'application/json' },
  });
}`;

export const postMessageSnippet = `const OMI_ORIGIN = 'https://h.omi.me';

window.addEventListener('message', (event) => {
  if (event.origin !== OMI_ORIGIN) return;          // validate the origin
  const data = event.data;
  if (data?.type !== 'omi.memory.embed.resize') return;
  frame.style.height = \`\${Number(data.height) || 560}px\`;
});`;

export const cspSnippet = `Content-Security-Policy: frame-ancestors https://your-app.example https://app.your-app.example`;

export const securityChecklist = [
  'Use a server-side proxy or a short-lived, narrowly scoped session.',
  'Never place Omi API keys in source, browser storage, or public environment variables.',
  'Validate origin on every postMessage event and send only typed UI events.',
  'Set frame-ancestors to the exact parent origins you control.',
  'Keep writes explicit and user-initiated; default to memories.read.',
  'Treat local zkr or SQLite as a cache or pending buffer, never as authority.',
];
