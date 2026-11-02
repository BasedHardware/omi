import { NextRequest, NextResponse } from "next/server";
import { requireTeamAgent } from "@/lib/team/agent-auth";
import {
  createProposal,
  listProposals,
  proposalInput,
} from "@/lib/team/proposals";
import { readJson, teamErrorResponse } from "@/lib/team/http";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const agent = await requireTeamAgent(request);
  if (agent instanceof NextResponse) return agent;

  try {
    return NextResponse.json({ proposals: await listProposals() });
  } catch (error) {
    return teamErrorResponse(error, "Failed to fetch proposals");
  }
}

/**
 * File a proposed roster change. Nothing changes until an owner or a deputy
 * approves it on the Team page; there is no agent route that approves.
 */
export async function POST(request: NextRequest) {
  const agent = await requireTeamAgent(request);
  if (agent instanceof NextResponse) return agent;

  const parsed = proposalInput.safeParse(await readJson(request));
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid proposal", issues: parsed.error.issues },
      { status: 400 }
    );
  }
  try {
    const proposal = await createProposal(agent.email, parsed.data);
    return NextResponse.json({ proposal }, { status: 201 });
  } catch (error) {
    return teamErrorResponse(error, "Failed to file proposal");
  }
}
