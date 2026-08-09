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
    return NextResponse.json({ error: "Failed to list TV links" }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  const auth = await verifyAdmin(request);
  if (auth instanceof NextResponse) return auth;

  try {
    const body = (await request.json().catch(() => ({}))) as {
      label?: string;
      ttlDays?: number | null;
      includeRevenue?: boolean;
    };

    const created = await createTvLink({
      label: body.label || "Office TV",
      createdBy: auth.uid,
      ttlDays: body.ttlDays === undefined ? undefined : body.ttlDays,
      includeRevenue: body.includeRevenue,
    });

    // Absolute URL when host is known (for copy-paste on TV).
    const proto = request.headers.get("x-forwarded-proto") || "https";
    const host = request.headers.get("x-forwarded-host") || request.headers.get("host");
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
    return NextResponse.json({ error: "Failed to create TV link" }, { status: 500 });
  }
}
