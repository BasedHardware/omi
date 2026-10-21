import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { getDb } from "@/lib/firebase/admin";
export const dynamic = "force-dynamic";

// Firestore-backed CSAT stats (`csat_ratings`): overall count, 1–5 histogram,
// average, and the most recent comments. The PostHog `Desktop Rating
// Submitted` chart stays as the daily trend feed — PostHog has no comments,
// so this is the read path for them. One rating doc per `{platform}_{uid}`,
// newest-first, computed in memory (no composite index needed at this scale).

type CsatRatingRow = {
  uid: string;
  platform: string;
  app_version: string;
  score: number;
  comment: string;
  created_at: number;
  revision: number;
};

type CsatStats = {
  available: boolean;
  total: number;
  histogram: Record<string, number>;
  avg: number | null;
  comments: CsatRatingRow[];
};

function row(data: Record<string, unknown>): CsatRatingRow {
  return {
    uid: String(data.uid ?? ""),
    platform: String(data.platform ?? ""),
    app_version: String(data.app_version ?? ""),
    score: Number(data.score) || 0,
    comment: String(data.comment ?? ""),
    created_at: Number(data.created_at) || 0,
    revision: Number(data.revision) || 0,
  };
}

export function summarizeCsatRatings(
  rawRows: CsatRatingRow[]
): Omit<CsatStats, "available"> {
  const histogram: Record<string, number> = {};
  let sum = 0;
  let counted = 0;
  for (const entry of rawRows) {
    if (entry.score < 1 || entry.score > 5) continue;
    const key = String(entry.score);
    histogram[key] = (histogram[key] ?? 0) + 1;
    sum += entry.score;
    counted += 1;
  }
  return {
    total: counted,
    histogram,
    avg: counted > 0 ? Math.round((sum / counted) * 100) / 100 : null,
    // Newest first already (query order); only rows that carry a comment.
    comments: rawRows.filter((entry) => entry.comment.trim()).slice(0, 50),
  };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;
  const requested = parseInt(
    request.nextUrl.searchParams.get("limit") || "500",
    10
  );
  const limit = Number.isFinite(requested)
    ? Math.min(Math.max(requested, 1), 500)
    : 500;
  try {
    const snapshot = await getDb()
      .collection("csat_ratings")
      .orderBy("created_at", "desc")
      .limit(limit)
      .get();
    const rows = snapshot.docs.map((d) => row(d.data()));
    return NextResponse.json({
      available: true,
      ...summarizeCsatRatings(rows),
    });
  } catch (error) {
    console.error("CSAT stats error:", error);
    // Never invent zeros while claiming success.
    return NextResponse.json({
      available: false,
      total: 0,
      histogram: {},
      avg: null,
      comments: [],
    });
  }
}
