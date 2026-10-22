import { NextRequest, NextResponse } from "next/server";
import {
  verifyServiceAccountToken,
  type ServiceAccountReason,
} from "@/lib/service-account-token";

type Reason =
  | "allowed"
  | "route_not_allowed"
  | "method_not_allowed"
  | ServiceAccountReason;

/** Untrusted routing hint only; Firebase still verifies signature and claims. */
export function usesFirebaseIssuer(token: string): boolean {
  try {
    const { iss } = JSON.parse(
      Buffer.from(token.split(".")[1], "base64url").toString()
    );
    return (
      typeof iss === "string" &&
      iss.startsWith("https://securetoken.google.com/")
    );
  } catch {
    return false;
  }
}

/** This identity has no Firebase admin membership and is valid only for stats GET. */
export async function verifyStatsReader(request: NextRequest, token: string) {
  const route = request.nextUrl.pathname;
  function audit(reason: Reason) {
    const allowed = reason === "allowed";
    // Never include the token, claims, query string, or SDK errors (which can
    // embed the entire JWT). JSON is a single structured Cloud Logging record.
    console.info(
      JSON.stringify({
        event: "admin_stats_machine_auth",
        decision: allowed ? "allowed" : "denied",
        reason,
        route,
      })
    );
  }
  function decision(reason: Exclude<Reason, "allowed">) {
    audit(reason);
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  if (!route.startsWith("/api/omi/stats/"))
    return decision("route_not_allowed");
  if (request.method !== "GET") return decision("method_not_allowed");
  const result = await verifyServiceAccountToken(token, {
    audience: process.env.ADMIN_STATS_READER_AUDIENCE,
    allowlist: process.env.ADMIN_STATS_READER_SAS,
  });
  if (!result.ok) return decision(result.reason);
  audit("allowed");
  return { uid: `stats-reader:${result.sub}` };
}
