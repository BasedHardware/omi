import { NextRequest, NextResponse } from "next/server";
import { verifyAdminOrTvSnapshot } from "@/lib/auth";
import { buildTvSnapshot } from "@/lib/tv-snapshot";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

/**
 * Read-only aggregate TV metrics.
 * Auth: Firebase admin session OR active TV share token.
 * TV tokens never unlock other admin APIs.
 */
export async function GET(request: NextRequest) {
  const auth = await verifyAdminOrTvSnapshot(request);
  if (auth instanceof NextResponse) return auth;

  try {
    const includeRevenue =
      auth.kind === "admin" ? true : auth.includeRevenue;
    const snapshot = await buildTvSnapshot({ includeRevenue });
    return NextResponse.json(
      {
        ...snapshot,
        auth: {
          kind: auth.kind,
          includeRevenue,
          label: auth.kind === "tv" ? auth.link.label : "Admin",
        },
      },
      {
        headers: {
          "Cache-Control": "private, max-age=60",
        },
      },
    );
  } catch (error) {
    console.error("TV snapshot error:", error);
    const message = error instanceof Error ? error.message : "Failed to build TV snapshot";
    const allSourcesFailed =
      /no tv metric sources/i.test(message) ||
      /POSTHOG_PERSONAL_API_KEY/i.test(message);
    return NextResponse.json(
      { error: message },
      { status: allSourcesFailed ? 502 : 500 },
    );
  }
}
