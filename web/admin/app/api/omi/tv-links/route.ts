import { NextRequest, NextResponse } from "next/server";
import { requireScope } from "@/lib/auth";
import { hasScope } from "@/lib/admin-access";
import { createTvLink, listTvLinks } from "@/lib/tv-links";

export const dynamic = "force-dynamic";

/** The only shareable board is the financial Business one, so its share
 * links need finance:read; without a non-financial board there is nothing
 * a non-finance issuer may share. */
function boardScopeDenied(auth: Awaited<ReturnType<typeof requireScope>>) {
  if (auth instanceof NextResponse) return auth;
  return auth.json(
    {
      error:
        "TV links open the Business board (revenue and cost panels), which requires finance:read.",
      scope: "finance:read",
    },
    { status: 403 }
  );
}

export async function GET(request: NextRequest) {
  const auth = await requireScope(request, "analytics:share");
  if (auth instanceof NextResponse) return auth;

  try {
    const links = await listTvLinks({
      // The share token is the capability to view the financial board; it
      // stays visible only to callers who could mint one themselves.
      revealTokens: hasScope(auth.access, "finance:read"),
    });
    return auth.json({ links });
  } catch (error) {
    console.error("list TV links:", error);
    return auth.json({ error: "Failed to list TV links" }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  const auth = await requireScope(request, "analytics:share");
  if (auth instanceof NextResponse) return auth;
  if (!hasScope(auth.access, "finance:read")) return boardScopeDenied(auth);

  const raw = await request.text();
  let parsed: unknown = {};
  if (raw.trim()) {
    try {
      parsed = JSON.parse(raw);
    } catch {
      return auth.json({ error: "Invalid JSON body" }, { status: 400 });
    }
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return auth.json(
      { error: "Request body must be a JSON object" },
      { status: 400 }
    );
  }
  const body = parsed as {
    label?: string;
    ttlDays?: number | null;
  };

  if (
    body.label !== undefined &&
    body.label !== null &&
    typeof body.label !== "string"
  ) {
    return auth.json({ error: "label must be a string" }, { status: 400 });
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
        return auth.json(
          {
            error:
              "ttlDays must be a positive integer, null for never, or omitted for default",
          },
          { status: 400 }
        );
      }
      if (ttlDays > 3650) {
        return auth.json(
          { error: "ttlDays cannot exceed 3650" },
          { status: 400 }
        );
      }
    }

    const created = await createTvLink({
      label: body.label || "Office TV",
      createdBy: auth.uid,
      ttlDays,
    });

    const proto =
      request.headers.get("x-forwarded-proto") ||
      request.nextUrl.protocol.replace(":", "") ||
      "https";
    const host =
      request.headers.get("x-forwarded-host") || request.headers.get("host");
    const origin = host ? `${proto}://${host}` : "";
    const url = origin ? `${origin}${created.path}` : created.path;

    return auth.json({
      link: created.link,
      token: created.token,
      path: created.path,
      url,
    });
  } catch (error) {
    console.error("create TV link:", error);
    return auth.json({ error: "Failed to create TV link" }, { status: 500 });
  }
}
