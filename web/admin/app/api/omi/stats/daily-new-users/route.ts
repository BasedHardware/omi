import { NextRequest, NextResponse } from "next/server";
import admin, { getDb } from "@/lib/firebase/admin";
import { verifyAdmin } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const { searchParams } = new URL(request.url);
    const days = Math.min(parseInt(searchParams.get("days") || "30", 10), 730);

    const db = getDb();
    const now = new Date();
    const startDate = new Date(now);
    startDate.setDate(startDate.getDate() - days);
    startDate.setHours(0, 0, 0, 0);

    const startTimestamp = admin.firestore.Timestamp.fromDate(startDate);

    // Run three queries in parallel:
    //  1. Total document count across the entire users collection — the
    //     authoritative source for "all users ever" (includes docs with no
    //     created_at field, which would otherwise be silently dropped).
    //  2. Count of users created inside the window — subtracted from the
    //     total to derive the pre-window baseline.
    //  3. The full window snapshot, bucketed by day for the per-day series.
    const [totalAgg, windowCountAgg, windowSnapshot] = await Promise.all([
      db.collection("users").count().get(),
      db
        .collection("users")
        .where("created_at", ">=", startTimestamp)
        .count()
        .get(),
      db
        .collection("users")
        .where("created_at", ">=", startTimestamp)
        .orderBy("created_at", "asc")
        .get(),
    ]);

    const totalCount = totalAgg.data().count;
    const windowCount = windowCountAgg.data().count;
    // Everything that existed before the window — including users that
    // predate the created_at field and therefore can't be binned by date.
    const baseline = Math.max(0, totalCount - windowCount);

    // Group by date
    const countsByDate: Record<string, number> = {};

    // Pre-fill all dates with 0
    for (let i = 0; i < days; i++) {
      const d = new Date(startDate);
      d.setDate(d.getDate() + i);
      const key = d.toISOString().split("T")[0];
      countsByDate[key] = 0;
    }

    windowSnapshot.docs.forEach((doc) => {
      const data = doc.data();
      if (data.created_at) {
        const ts = data.created_at.toDate();
        const key = ts.toISOString().split("T")[0];
        if (countsByDate[key] !== undefined) {
          countsByDate[key]++;
        }
      }
    });

    let running = baseline;
    const data = Object.entries(countsByDate)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, users]) => {
        running += users;
        return { date, users, cumulative: running };
      });

    const totalUsers = data.reduce((sum, d) => sum + d.users, 0);

    return NextResponse.json({ data, totalUsers, days });
  } catch (error: any) {
    console.error("Daily new users error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to fetch daily new users" },
      { status: 500 }
    );
  }
}
