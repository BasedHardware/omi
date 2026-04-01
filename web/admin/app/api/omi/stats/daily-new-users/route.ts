import { NextResponse } from "next/server";
import admin, { getDb } from "@/lib/firebase/admin";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const days = Math.min(parseInt(searchParams.get("days") || "30", 10), 90);

    const db = getDb();
    const now = new Date();
    const startDate = new Date(now);
    startDate.setDate(startDate.getDate() - days);
    startDate.setHours(0, 0, 0, 0);

    const snapshot = await db
      .collection("users")
      .where("created_at", ">=", admin.firestore.Timestamp.fromDate(startDate))
      .orderBy("created_at", "asc")
      .get();

    // Group by date
    const countsByDate: Record<string, number> = {};

    // Pre-fill all dates with 0
    for (let i = 0; i < days; i++) {
      const d = new Date(startDate);
      d.setDate(d.getDate() + i);
      const key = d.toISOString().split("T")[0];
      countsByDate[key] = 0;
    }

    snapshot.docs.forEach((doc) => {
      const data = doc.data();
      if (data.created_at) {
        const ts = data.created_at.toDate();
        const key = ts.toISOString().split("T")[0];
        if (countsByDate[key] !== undefined) {
          countsByDate[key]++;
        }
      }
    });

    const data = Object.entries(countsByDate)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, users]) => ({ date, users }));

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
