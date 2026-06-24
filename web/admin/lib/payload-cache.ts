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

export async function getPayload<T>(key: string): Promise<{ data: T; freshAt: number } | null> {
  try {
    const snap = await getDb().collection(CACHE_COLLECTION).doc(docId(key)).get();
    if (!snap.exists) return null;
    const d = snap.data() as CacheDoc;
    if (!d?.payload) return null;
    return { data: JSON.parse(d.payload) as T, freshAt: d.freshAt ?? 0 };
  } catch {
    return null; // best-effort cache read; never throws
  }
}

export async function setPayload(key: string, data: unknown): Promise<void> {
  try {
    const payload = JSON.stringify(data);
    if (payload.length > MAX_PAYLOAD_CHARS) return;
    await getDb().collection(CACHE_COLLECTION).doc(docId(key)).set({ payload, freshAt: Date.now() });
  } catch {
    // best-effort cache write; never block the response
  }
}
