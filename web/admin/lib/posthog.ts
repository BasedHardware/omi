// Shared PostHog HogQL fetch with 429 backoff.
//
// PostHog's query endpoint is aggressively burst-rate-limited (HTTP 429,
// "Request was throttled. Expected available in 1 second."). The dashboard
// fires ~8 stat routes at once on load, so without retry these queries 429
// and the panels render errors / empty. Retrying with short backoff lets the
// burst drain and the per-route caches populate.

export async function posthogFetch(
  host: string,
  projectId: string,
  apiKey: string,
  query: string,
  { maxRetries = 5 }: { maxRetries?: number } = {},
): Promise<Response> {
  const url = `${host}/api/projects/${projectId}/query/`;
  let res!: Response;
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    res = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ query: { kind: "HogQLQuery", query } }),
    });
    if (res.status !== 429 || attempt === maxRetries) return res;
    // Burst throttle clears in ~1s; back off linearly with jitter.
    const waitMs = 1000 * (attempt + 1) + Math.floor(Math.random() * 400);
    await new Promise((r) => setTimeout(r, waitMs));
  }
  return res;
}
