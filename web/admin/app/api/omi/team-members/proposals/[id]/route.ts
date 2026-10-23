import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { requireScope } from "@/lib/auth";
import { decideProposal } from "@/lib/team/proposals";
import { actorFrom, readJson, teamErrorResponse } from "@/lib/team/http";

export const dynamic = "force-dynamic";

const decisionSchema = z.object({ decision: z.enum(["approve", "reject"]) });

/**
 * The human approval step. requireScope admits only Firebase-authenticated
 * admins with team:manage, so an agent identity can never reach it.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const authResult = await requireScope(request, "team:manage");
  if (authResult instanceof NextResponse) return authResult;

  const parsed = decisionSchema.safeParse(await readJson(request));
  if (!parsed.success) {
    return authResult.json(
      { error: 'decision must be "approve" or "reject"' },
      { status: 400 }
    );
  }
  const { id } = await params;
  try {
    const proposal = await decideProposal(
      actorFrom(authResult),
      id,
      parsed.data.decision
    );
    return authResult.json({ proposal });
  } catch (error) {
    return teamErrorResponse(error, "Failed to decide proposal");
  }
}
