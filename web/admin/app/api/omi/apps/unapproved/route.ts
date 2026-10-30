import { NextRequest, NextResponse } from "next/server";
import { requireScope } from "@/lib/auth";
// Assume a function exists to get unapproved apps from the Omi API
// You might need to create this in lib/services/omi-api/apps.ts
import { getUnapprovedApps } from "@/lib/services/omi-api/apps";
import { OmiApiError } from "@/lib/services/omi-api/client";

// Force dynamic rendering for this route as it needs auth
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const authResult = await requireScope(request, "apps:read");
  if (authResult instanceof NextResponse) return authResult;

  try {
    const apps = await getUnapprovedApps(authResult.uid);
    return authResult.json(apps);
  } catch (error) {
    console.error("[API Route] Error fetching Omi unapproved apps:", error);
    if (error instanceof OmiApiError) {
      return authResult.json(
        { error: error.message, details: error.details },
        { status: error.status }
      );
    }
    return authResult.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
