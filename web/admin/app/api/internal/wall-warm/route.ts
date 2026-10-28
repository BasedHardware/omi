import { NextRequest, NextResponse } from "next/server";
import { wallPayload, wallSnapshotStore } from "@/lib/wall-cache";
import { warmSeries } from "@/lib/wall-series";

export const dynamic = "force-dynamic";
export const maxDuration = 3600;

// Cron-only Omi TV warmer (scheduler `omi-admin-wall-warm`, every 10 min).
// The wall's snapshot and series legs are keyed per UTC day; without this the
// first viewer after midnight UTC triggered the whole day's PostHog fill
// (~60 serialized HogQL reads, ~11 min on 2026-10-28) and the board sat blank.
// Here the fill runs to completion off the viewing path; once every leg is
// complete for the day a tick is only shared-store reads.
//
// Auth: `x-cron-secret` must equal `process.env.CRON_SECRET`, as for
// /api/internal/precompute. Response and logs carry leg names, outcomes and
// controlled reasons only.
export async function POST(request: NextRequest) {
  const secret = process.env.CRON_SECRET;
  if (!secret || request.headers.get("x-cron-secret") !== secret)
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const started = Date.now();
  // Snapshot first: series reads yield to a running snapshot refresh anyway.
  const work: Promise<unknown>[] = [];
  const snapshot = await wallPayload(
    undefined,
    undefined,
    (refresh) => void work.push(refresh),
    wallSnapshotStore()
  );
  await Promise.allSettled(work);
  const legs = await warmSeries();
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
