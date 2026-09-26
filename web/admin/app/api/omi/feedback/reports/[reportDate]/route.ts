import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import {
  FeedbackApiError,
  generateReport,
  getReport,
} from "@/lib/services/omi-api/feedback";

export const dynamic = "force-dynamic";

// The report body carries pointers only — event envelopes plus the message
// ids, senders and timestamps around each thumbs-down. Conversation text is
// fetched separately, one event at a time, through the context route.
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ reportDate: string }> }
) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const { reportDate } = await params;
  try {
    return NextResponse.json(await getReport(authResult.uid, reportDate));
  } catch (error) {
    const status = error instanceof FeedbackApiError ? error.status : 502;
    // A 404 here is normal: a day whose cron has not run yet has no report.
    if (status !== 404) console.error("Feedback report fetch error:", error);
    return NextResponse.json(
      {
        error:
          error instanceof Error ? error.message : "Failed to fetch report",
      },
      { status }
    );
  }
}

// Manual (re)generation for a day whose nightly run failed, or a backfill.
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ reportDate: string }> }
) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const { reportDate } = await params;
  try {
    return NextResponse.json(await generateReport(authResult.uid, reportDate));
  } catch (error) {
    const status = error instanceof FeedbackApiError ? error.status : 502;
    console.error("Feedback report generate error:", error);
    return NextResponse.json(
      {
        error:
          error instanceof Error ? error.message : "Failed to generate report",
      },
      { status }
    );
  }
}
