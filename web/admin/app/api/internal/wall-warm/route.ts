import { after, NextRequest, NextResponse } from "next/server";
import { wallPayload, wallSnapshotStore } from "@/lib/wall-cache";
import { WARM_BUDGET_MS, warmSeries } from "@/lib/wall-series";

export const dynamic = "force-dynamic";
export const maxDuration = 3600;

// Cron-only Omi TV warmer (scheduler `omi-admin-wall-warm`, every 10 min).
// The wall's snapshot and series legs are keyed per UTC day; without this the
// first viewer after midnight UTC triggered the whole day's PostHog fill
// (~60 serialized HogQL reads, ~11 min on 2026-10-28) and the board sat blank.
// Here the fill runs off the viewing path, answering within WARM_BUDGET_MS
// (Scheduler's attempt deadline is 30 min); once every leg is complete for the
// day a tick is only shared-store reads.
//
// Auth: `x-cron-secret` must equal `process.env.CRON_SECRET`, as for
// /api/internal/precompute. Response and logs carry leg names, outcomes and
// controlled reasons only.
export async function POST(request: NextRequest) {
  const secret = process.env.CRON_SECRET;
  if (!secret || request.headers.get("x-cron-secret") !== secret)
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const started = Date.now();
  // Fills that outlast this request keep running inside after() (the admin
  // deploy pins --no-cpu-throttling); the next tick sees their leases.
  const retain = (work: Promise<unknown>) =>
    after(async () => {
      await work;
    });
  // Snapshot first: series reads yield to a running snapshot refresh anyway.
  const work: Promise<unknown>[] = [];
  const snapshot = await wallPayload(
    undefined,
    undefined,
    (refresh) => {
      work.push(refresh);
      retain(refresh);
    },
    wallSnapshotStore()
  );
  let timer: ReturnType<typeof setTimeout> | undefined;
  await Promise.race([
    Promise.allSettled(work),
    new Promise((resolve) => (timer = setTimeout(resolve, WARM_BUDGET_MS))),
  ]);
  if (timer) clearTimeout(timer);
  const legs = await warmSeries(
    undefined,
    undefined,
    Math.max(0, WARM_BUDGET_MS - (Date.now() - started)),
    retain
  );
  const incomplete = Object.entries(legs)
    .filter(([, leg]) => !leg.complete)
    .map(([name]) => name);
  const result = {
    ms: Date.now() - started,
    snapshotRefreshed: work.length > 0,
    snapshotNullMetrics: snapshot.metrics.filter((m) => m.value == null).length,
    incomplete,
    legs,
  };
  console.log(
    JSON.stringify({
      event: "wall_warm",
      ms: result.ms,
      incomplete,
      snapshot_refreshed: result.snapshotRefreshed,
    })
  );
  return NextResponse.json(result);
}
