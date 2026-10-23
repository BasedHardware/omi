import { NextRequest, NextResponse } from "next/server";
import { requireScope } from "@/lib/auth";
import { getApps } from "@/lib/services/omi-api/apps"; // Import your Omi service
import { OmiApiError } from "@/lib/services/omi-api/client"; // Import custom error

// Force dynamic rendering for this route as it uses request headers
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const authResult = await requireScope(request, "apps:read");
  if (authResult instanceof NextResponse) return authResult;

  try {
    const apps = await getApps(authResult.uid);
    return authResult.json(apps);
  } catch (error) {
    console.error("[API Route] Error fetching Omi apps:", error);
    if (error instanceof OmiApiError) {
      // Forward the status and details from the Omi API error
      return authResult.json(
        { error: error.message, details: error.details },
        { status: error.status }
      );
    }
    // Generic server error
    return authResult.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

// You would add similar POST, PATCH, DELETE handlers here as needed,
// each verifying the token and calling the corresponding service function.
