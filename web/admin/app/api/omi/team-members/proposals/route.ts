import { NextRequest, NextResponse } from "next/server";
import { requireScope } from "@/lib/auth";
import { listProposals } from "@/lib/team/proposals";
import { teamErrorResponse } from "@/lib/team/http";

export const dynamic = "force-dynamic";

/** Agent proposals, newest first. A read: expiry is derived per response
 * and persisted only when a write path (decide, file) touches the proposal. */
export async function GET(request: NextRequest) {
  const authResult = await requireScope(request, "team:read");
  if (authResult instanceof NextResponse) return authResult;

  try {
    return authResult.json({ proposals: await listProposals() });
  } catch (error) {
    return teamErrorResponse(error, "Failed to fetch proposals");
  }
}
