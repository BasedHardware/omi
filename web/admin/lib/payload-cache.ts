// Firestore payload cache for precomputed admin stats payloads.
//
// Separate from posthog.ts's per-query cache (`admin_stats_cache`). This stores
// whole computed route payloads (profitability, infra-costs) keyed by their
// request params, written off the request path by the cron precompute endpoint.
//
// The admin service's configured Redis (light-eel-27878.upstash.io) is dead, so
// the old `@/lib/redis` caching was a silent no-op. Firestore is always
// reachable here via firebase-admin (same path posthog.ts + macos-versions use).
// Payloads are JSON-stringified to sidestep Firestore's no-nested-arrays rule.

import { createHash } from "crypto";
import { getDb } from "@/lib/firebase/admin";

const CACHE_COLLECTION = "admin_stats_payload_cache";
const MAX_PAYLOAD_CHARS = 900_000; // Firestore field cap ~1 MB; skip oversized

type CacheDoc = { payload: string; freshAt: number };

// Doc ids can't contain `/`. Callers use keys like
// `profitability:v1:90:1.2:0.3` which are safe, but if a key ever contains a
// slash we sha1-hash it to keep the write valid.
function docId(key: string): string {
  return key.includes("/") ? createHash("sha1").update(key).digest("hex") : key;
}

export async function getPayload<T>(
  key: string,
  opts?: { maxAgeMs?: number }
): Promise<{ data: T; freshAt: number } | null> {
  try {
    const snap = await getDb()
      .collection(CACHE_COLLECTION)
      .doc(docId(key))
      .get();
    if (!snap.exists) return null;
    const d = snap.data() as CacheDoc;
    if (!d?.payload) return null;
    const freshAt = d.freshAt ?? 0;
    // A doc older than the consumer's bound is a miss, not a hit: fall through
    // to the caller's inline compute instead of serving a frozen payload.
    if (opts?.maxAgeMs != null && Date.now() - freshAt > opts.maxAgeMs) {
      return null;
    }
    return { data: JSON.parse(d.payload) as T, freshAt };
  } catch {
    return null; // best-effort cache read; never throws
  }
}

// Serve a precomputed payload only while it can still be considered live.
// The precompute cron (app/api/internal/precompute) runs hourly, so 3× its
// cadence tolerates one failed run; past that, a doc is a key no active
// writer maintains (legacy request params, retired surface) and must not be
// served as fresh data — the route recomputes inline instead. This is what
// made the Aug-25 frozen profitability panel possible: a legacy
// `profitability:v1:30:1.2:0.3` doc was served at any age for ~4 weeks while
// the cron wrote a sibling key.
export const MAX_PRECOMPUTED_AGE_MS = 3 * 60 * 60 * 1000;

// Stamp a payload with the age of the data it carries. Consumers that pass
// MAX_PRECOMPUTED_AGE_MS serve cached payloads only within that bound, but the
// bound is a latency/freshness trade, not a TTL eviction — without `freshAt`
// a broken precompute cron still looks identical to live data within it.
// `freshAt` is epoch ms: the moment the payload was computed on a cache hit,
// or `Date.now()` on a fresh inline compute.
export function withFreshness<T extends object>(
  data: T,
  freshAt: number
): T & { freshAt: number } {
  return { ...data, freshAt };
}

export async function setPayload(key: string, data: unknown): Promise<void> {
  try {
    const payload = JSON.stringify(data);
    if (payload.length > MAX_PAYLOAD_CHARS) return;
    await getDb()
      .collection(CACHE_COLLECTION)
      .doc(docId(key))
      .set({ payload, freshAt: Date.now() });
  } catch {
    // best-effort cache write; never block the response
  }
}
