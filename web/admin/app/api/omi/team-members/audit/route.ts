import { NextRequest, NextResponse } from "next/server";
import { requireScope } from "@/lib/auth";
import { listAudit } from "@/lib/team/roster";
import { teamErrorResponse } from "@/lib/team/http";

export const dynamic = "force-dynamic";

/** Every roster, role and proposal event, newest first. */
export async function GET(request: NextRequest) {
  const authResult = await requireScope(request, "team:read");
  if (authResult instanceof NextResponse) return authResult;

  const limit = Number(request.nextUrl.searchParams.get("limit") ?? 100) || 100;
  try {
    return authResult.json({ entries: await listAudit(limit) });
  } catch (error) {
    return teamErrorResponse(error, "Failed to fetch the audit log");
  }
}
