import { after, NextRequest, NextResponse } from "next/server";
import { requireScope } from "@/lib/auth";
import { wallPayload, wallSnapshotStore } from "@/lib/wall-cache";
import { localWallFixture } from "@/lib/wall-local-fixture";
import { SERIES_NAMES, SeriesName, seriesPayload } from "@/lib/wall-series";

export const dynamic = "force-dynamic";
export const maxDuration = 3600;

/** Omi TV v3 chart series; same definitions and cold-load rules as /wall. */
export async function GET(
  request: NextRequest,
  props: { params: Promise<{ name: string }> }
) {
  // revenue, health and headline frames carry MRR, hardware revenue and
  // cost data; the usage-only series ride the same board, so the whole
  // route is a finance read, like /wall and the Grafana embed.
  const auth = await requireScope(request, "finance:read");
  if (auth instanceof NextResponse) return auth;
  const { name } = await props.params;
  if (!SERIES_NAMES.includes(name as SeriesName))
    return auth.json({ error: "Unknown wall series" }, { status: 404 });
  const retain = (work: Promise<unknown>) =>
    after(async () => {
      await work;
    });
  try {
    const snapshot = localWallFixture().then(
      (fixture) =>
        fixture ||
        wallPayload(undefined, undefined, retain, wallSnapshotStore())
    );
    const payload = await seriesPayload(
      name as SeriesName,
      snapshot,
      undefined,
      undefined,
      retain
    );
    return auth.json(payload, {
      headers: { "Cache-Control": "private, no-store" },
    });
  } catch {
    return auth.json(
      { error: "Wall series sources unavailable" },
      { status: 502 }
    );
  }
}
