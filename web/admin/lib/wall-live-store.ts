/** Web read of the live metered document the `omi-tv-live` job writes to
 * `admin_stats_payload_cache/${LIVE_DOC_ID}` (same `{payload, freshAt}` shape as
 * the series store). Read-only here; any failure is "no live days", never a
 * guess: the margin then shows the settled days alone and says so. */
import { LiveDoc, LIVE_DOC_ID, parseLiveDoc } from "./wall-live";

const COLLECTION = "admin_stats_payload_cache";

export async function readLiveDoc(): Promise<LiveDoc | null> {
  try {
    const { getDb } = await import("@/lib/firebase/admin");
    const snap = await getDb().collection(COLLECTION).doc(LIVE_DOC_ID).get();
    const data = snap.exists ? (snap.data() as { payload?: string }) : null;
    return parseLiveDoc(data?.payload ? JSON.parse(data.payload) : null);
  } catch {
    return null;
  }
}
