import { NextRequest, NextResponse } from "next/server";
import { usesFirebaseIssuer } from "@/lib/stats-reader-auth";
import {
  verifyServiceAccountToken,
  type ServiceAccountReason,
} from "@/lib/service-account-token";

export interface TeamAgent {
  email: string;
  sub: string;
}

/**
 * Team agents (Claude Code and similar, running as an allowlisted Google
 * service account) may read the roster and audit log and file proposals.
 * They never hold an admin scope: `requireScope` does not accept them, and
 * these routes do not accept Firebase (human) tokens.
 */
export async function requireTeamAgent(
  request: NextRequest
): Promise<TeamAgent | NextResponse> {
  const route = request.nextUrl.pathname;
  function denied(
    reason: ServiceAccountReason | "missing_token" | "human_token"
  ) {
    console.info(
      JSON.stringify({
        event: "admin_team_agent_auth",
        decision: "denied",
        reason,
        route,
      })
    );
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const authorization = request.headers.get("Authorization");
  if (!authorization?.startsWith("Bearer ")) return denied("missing_token");
  const token = authorization.slice("Bearer ".length);
  if (usesFirebaseIssuer(token)) return denied("human_token");

  const result = await verifyServiceAccountToken(token, {
    audience: process.env.ADMIN_TEAM_AGENT_AUDIENCE,
    allowlist: process.env.ADMIN_TEAM_AGENT_SAS,
  });
  if (!result.ok) return denied(result.reason);
  console.info(
    JSON.stringify({
      event: "admin_team_agent_auth",
      decision: "allowed",
      agent: result.email,
      route,
      method: request.method,
    })
  );
  return { email: result.email, sub: result.sub };
}
