import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import {
  FeedbackApiError,
  getEventContext,
} from "@/lib/services/omi-api/feedback";

export const dynamic = "force-dynamic";

// The only route that returns user conversation text. It is fetched on demand
// per event rather than baked into the report, so no plaintext copy of a
// user's chat is ever written outside the encrypted message store. The backend
// logs each of these reads against the admin key that made it.
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ eventId: string }> }
) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const { eventId } = await params;
  const reportDate =
    request.nextUrl.searchParams.get("report_date") || undefined;

  try {
    return NextResponse.json(
      await getEventContext(authResult.uid, eventId, reportDate)
    );
  } catch (error) {
    const status = error instanceof FeedbackApiError ? error.status : 502;
    console.error("Feedback context fetch error:", error);
    return NextResponse.json(
      {
        error:
          error instanceof Error ? error.message : "Failed to fetch context",
      },
      { status }
    );
  }
}
