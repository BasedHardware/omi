import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { createTvLink, listTvLinks } from "@/lib/tv-links";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const auth = await verifyAdmin(request);
  if (auth instanceof NextResponse) return auth;

  try {
    const links = await listTvLinks();
    return NextResponse.json({ links });
  } catch (error) {
    console.error("list TV links:", error);
    return NextResponse.json(
      { error: "Failed to list TV links" },
      { status: 500 },
    );
  }
}

export async function POST(request: NextRequest) {
  const auth = await verifyAdmin(request);
  if (auth instanceof NextResponse) return auth;

  let body: {
    label?: string;
    ttlDays?: number | null;
    includeRevenue?: boolean;
  };

  // Parse JSON explicitly — a malformed body must return 400, not silently
  // create a default 90-day, revenue-enabled link.
  const raw = await request.text();
  if (raw.trim()) {
    try {
      body = JSON.parse(raw);
    } catch {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
  } else {
    body = {};
  }

  let ttlDays: number | null | undefined = body.ttlDays;
  try {
    if (ttlDays !== undefined && ttlDays !== null) {
      if (
        typeof ttlDays !== "number" ||
        !Number.isFinite(ttlDays) ||
        !Number.isInteger(ttlDays) ||
        ttlDays < 1
      ) {
        return NextResponse.json(
          {
            error:
              "ttlDays must be a positive integer, null for never, or omitted for default",
          },
          { status: 400 },
        );
      }
      if (ttlDays > 3650) {
        return NextResponse.json(
          { error: "ttlDays cannot exceed 3650" },
          { status: 400 },
        );
      }
    }

    const created = await createTvLink({
      label: body.label || "Office TV",
      createdBy: auth.uid,
      ttlDays,
      includeRevenue: body.includeRevenue,
    });

    // Absolute URL when host is known (for copy-paste on TV).
    const proto = request.headers.get("x-forwarded-proto") || "https";
    const host =
      request.headers.get("x-forwarded-host") || request.headers.get("host");
    const origin = host ? `${proto}://${host}` : "";
    const url = origin ? `${origin}${created.path}` : created.path;

    return NextResponse.json({
      link: created.link,
      token: created.token,
      path: created.path,
      url,
      // Token is only returned on create.
      notice: "Copy the URL now. The full token is not shown again.",
    });
  } catch (error) {
    console.error("create TV link:", error);
    return NextResponse.json(
      { error: "Failed to create TV link" },
      { status: 500 },
    );
  }
}
