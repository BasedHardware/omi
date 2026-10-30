import { NextRequest, NextResponse } from "next/server";
import { requireTeamAgent } from "@/lib/team/agent-auth";
import { listRoster } from "@/lib/team/roster";
import { teamErrorResponse } from "@/lib/team/http";

export const dynamic = "force-dynamic";

/** Roster for team agents: who has which role. No user data. */
export async function GET(request: NextRequest) {
  const agent = await requireTeamAgent(request);
  if (agent instanceof NextResponse) return agent;

  try {
    return NextResponse.json({ teamMembers: await listRoster() });
  } catch (error) {
    return teamErrorResponse(error, "Failed to fetch team members");
  }
}
