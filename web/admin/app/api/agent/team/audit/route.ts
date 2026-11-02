import { NextRequest, NextResponse } from "next/server";
import { requireTeamAgent } from "@/lib/team/agent-auth";
import { listAudit } from "@/lib/team/roster";
import { teamErrorResponse } from "@/lib/team/http";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const agent = await requireTeamAgent(request);
  if (agent instanceof NextResponse) return agent;

  const limit = Number(request.nextUrl.searchParams.get("limit") ?? 100) || 100;
  try {
    return NextResponse.json({ entries: await listAudit(limit) });
  } catch (error) {
    return teamErrorResponse(error, "Failed to fetch the audit log");
  }
}
