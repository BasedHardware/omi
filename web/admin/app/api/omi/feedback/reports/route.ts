import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import {
  FeedbackApiError,
  listReportDates,
} from "@/lib/services/omi-api/feedback";

export const dynamic = "force-dynamic";

// Dates that have a materialized daily thumbs-down report, newest first.
export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const parsed = parseInt(
    request.nextUrl.searchParams.get("limit") || "30",
    10
  );
  const limit = Math.min(Math.max(Number.isNaN(parsed) ? 30 : parsed, 1), 90);

  try {
    return NextResponse.json(await listReportDates(authResult.uid, limit));
  } catch (error) {
    const status = error instanceof FeedbackApiError ? error.status : 502;
    console.error("Feedback report list error:", error);
    return NextResponse.json(
      {
        error:
          error instanceof Error ? error.message : "Failed to list reports",
      },
      { status }
    );
  }
}
