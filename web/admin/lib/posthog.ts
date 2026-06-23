// Shared PostHog HogQL access with 429 backoff + Redis result caching.
//
// PostHog's query endpoint is aggressively rate-limited. The dashboard fires
// ~8 HogQL queries on every load; without caching, reloads + SWR retries blow
// the personal-API-key quota and every panel 429s.
//
// `posthogResults` caches each query's result in Redis (shared across Cloud
// Run instances), so a given query hits PostHog at most once per soft-TTL
// window instead of on every load. On throttle/error it serves the last good
// cached value (bounded by a hard TTL) rather than failing the panel.

import { createHash } from "crypto";
import { getJsonCache, setJsonCache } from "@/lib/redis";

export async function posthogFetch(
  host: string,
  projectId: string,
  apiKey: string,
  query: string,
  { maxRetries = 2 }: { maxRetries?: number } = {},
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
    const waitMs = 800 * (attempt + 1) + Math.floor(Math.random() * 300);
    await new Promise((r) => setTimeout(r, waitMs));
  }
  return res;
}

type CachedResults = { results: unknown[]; freshAt: number };

const SOFT_TTL_MS = 30 * 60 * 1000; // serve cached without re-querying for 30 min
const HARD_TTL_S = 6 * 60 * 60; // keep last-good up to 6h to survive throttling

/**
 * Run a HogQL query and return its `results` array, cached in Redis.
 * - Fresh cache (< soft TTL): returned without touching PostHog.
 * - Stale/miss: query PostHog (with 429 backoff); on success refresh the cache.
 * - On PostHog error/throttle: fall back to the last good cached value if any
 *   (within hard TTL), otherwise throw so the route surfaces the failure.
 */
export async function posthogResults(
  host: string,
  projectId: string,
  apiKey: string,
  query: string,
  opts: { softTtlMs?: number; hardTtlS?: number } = {},
): Promise<unknown[]> {
  const softTtlMs = opts.softTtlMs ?? SOFT_TTL_MS;
  const hardTtlS = opts.hardTtlS ?? HARD_TTL_S;
  const key = `admin:ph:${createHash("sha1").update(`${projectId}|${query}`).digest("hex")}`;

  const cached = await getJsonCache<CachedResults>(key);
  if (cached && Date.now() - cached.freshAt < softTtlMs) return cached.results;

  try {
    const res = await posthogFetch(host, projectId, apiKey, query);
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`PostHog API error: ${res.status} ${text.slice(0, 160)}`);
    }
    const raw = await res.json();
    const results = Array.isArray(raw.results) ? raw.results : [];
    await setJsonCache(key, { results, freshAt: Date.now() }, hardTtlS);
    return results;
  } catch (err) {
    if (cached) return cached.results; // serve last good value through the throttle
    throw err;
  }
}
