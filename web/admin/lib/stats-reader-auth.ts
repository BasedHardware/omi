import { OAuth2Client } from "google-auth-library";
import { NextRequest, NextResponse } from "next/server";

// Reuse the client: google-auth-library caches Google's signing certificates
// according to Cache-Control and refreshes them after expiry.
const googleIdentity = new OAuth2Client();
const GOOGLE_ISSUERS = ["accounts.google.com", "https://accounts.google.com"];
type Reason =
  | "allowed"
  | "disabled"
  | "route_not_allowed"
  | "method_not_allowed"
  | "invalid_token"
  | "expired"
  | "email_unverified"
  | "reader_not_allowed";

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
  const audience = process.env.ADMIN_STATS_READER_AUDIENCE?.trim();
  const readers = (process.env.ADMIN_STATS_READER_SAS ?? "")
    .split(/[,\s]+/)
    .filter(Boolean);
  if (!audience || !readers.length) return decision("disabled");

  try {
    const ticket = await googleIdentity.verifyIdToken({
      idToken: token,
      audience,
    });
    const claims = ticket.getPayload();
    if (
      !claims ||
      !GOOGLE_ISSUERS.includes(claims.iss) ||
      claims.aud !== audience ||
      !claims.sub
    ) {
      return decision("invalid_token");
    }
    // The SDK permits clock skew; this capability stops at the actual expiry.
    if (!Number.isFinite(claims.exp) || claims.exp <= Date.now() / 1000)
      return decision("expired");
    if (claims.email_verified !== true) return decision("email_unverified");
    if (
      !claims.email?.endsWith(".gserviceaccount.com") ||
      !readers.includes(claims.email)
    ) {
      return decision("reader_not_allowed");
    }
    audit("allowed");
    return { uid: `stats-reader:${claims.sub}` };
  } catch {
    return decision("invalid_token");
  }
}
