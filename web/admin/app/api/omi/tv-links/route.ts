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

  // Parse JSON explicitly — a malformed body must return 400, not silently
  // create a default 90-day, revenue-enabled link.
  const raw = await request.text();
  let parsed: unknown = {};
  if (raw.trim()) {
    try {
      parsed = JSON.parse(raw);
    } catch {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return NextResponse.json(
      { error: "Request body must be a JSON object" },
      { status: 400 },
    );
  }
  const body = parsed as {
    label?: string;
    ttlDays?: number | null;
    includeRevenue?: boolean;
  };

  if (
    body.label !== undefined &&
    body.label !== null &&
    typeof body.label !== "string"
  ) {
    return NextResponse.json(
      { error: "label must be a string" },
      { status: 400 },
    );
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

    // Validate includeRevenue type so a string like "false" cannot silently
    // create a revenue-enabled link (createTvLink treats !== false as true).
    if (
      body.includeRevenue !== undefined &&
      typeof body.includeRevenue !== "boolean"
    ) {
      return NextResponse.json(
        { error: "includeRevenue must be a boolean" },
        { status: 400 },
      );
    }

    const created = await createTvLink({
      label: body.label || "Office TV",
      createdBy: auth.uid,
      ttlDays,
      includeRevenue: body.includeRevenue,
    });

    // Absolute URL when host is known (for copy-paste on TV).
    // Derive protocol from the request so local HTTP dev doesn't get an
    // unopenable https://localhost URL.
    const proto =
      request.headers.get("x-forwarded-proto") ||
      request.nextUrl.protocol.replace(":", "") ||
      "https";
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
