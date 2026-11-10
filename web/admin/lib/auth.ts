import { NextRequest, NextResponse } from "next/server";
import {
  DEV_BYPASS_ENABLED,
  DEV_BYPASS_TOKEN,
  DEV_BYPASS_UID,
} from "@/lib/dev-auth";
import {
  verifyFirebaseToken,
  getDb,
  isFirebaseTokenError,
} from "@/lib/firebase/admin";
import { usesFirebaseIssuer, verifyStatsReader } from "@/lib/stats-reader-auth";
import {
  STATS_READER_SCOPES,
  accessFor,
  hasScope,
  type MemberAccess,
  type Scope,
} from "@/lib/admin-access";
import { redactSensitiveFields } from "@/lib/sensitive-fields";

export interface AdminIdentity {
  uid: string;
  kind: "human" | "stats-reader";
  /** Email on the caller's `adminData` doc, when it has one. */
  email: string | null;
  access: MemberAccess;
  /**
   * The one JSON response path for scoped data. Strips every classified
   * sensitive field (lib/sensitive-fields.ts) unless this identity holds
   * the scope that unlocks the field's class — including inside nested
   * documents, and with credentials never returned at all — so a route
   * cannot leak sensitive data field by field. A route that must show a
   * locked field passes `keep` with a comment and a test.
   */
  json: (
    body: unknown,
    init?: ResponseInit,
    keep?: readonly string[]
  ) => NextResponse;
}

const STATS_READER_ACCESS: MemberAccess = {
  kind: "role",
  role: null,
  roleLabel: "Stats reader",
  scopes: [...STATS_READER_SCOPES],
  overrides: {},
};

/** The single response choke point every scoped route responds through. */
function respondAs(access: MemberAccess) {
  return (body: unknown, init?: ResponseInit, keep?: readonly string[]) =>
    NextResponse.json(
      redactSensitiveFields(body, { scopes: access.scopes, keep }),
      init
    );
}

/**
 * Who is calling. Human callers need a Firebase ID token and adminData
 * membership. Machine callers receive only the stats GET capability from
 * verifyStatsReader. Every route goes through requireScope instead.
 */
async function authenticate(
  request: NextRequest
): Promise<AdminIdentity | NextResponse> {
  const authorization = request.headers.get("Authorization");

  if (DEV_BYPASS_ENABLED && authorization === `Bearer ${DEV_BYPASS_TOKEN}`) {
    const access = accessFor({ owner: true });
    return {
      uid: DEV_BYPASS_UID,
      kind: "human",
      email: null,
      access,
      json: respondAs(access),
    };
  }

  if (!authorization || !authorization.startsWith("Bearer ")) {
    return NextResponse.json(
      { error: "Unauthorized: Missing or invalid token" },
      { status: 401 }
    );
  }

  const token = authorization.split("Bearer ")[1];
  // Dispatch is not authorization: each verifier validates its own signed
  // claims. Machine failures never fall through to Firebase admin membership.
  if (!usesFirebaseIssuer(token)) {
    const reader = await verifyStatsReader(request, token);
    if (reader instanceof NextResponse) return reader;
    return {
      uid: reader.uid,
      kind: "stats-reader",
      email: null,
      access: STATS_READER_ACCESS,
      json: respondAs(STATS_READER_ACCESS),
    };
  }
  try {
    const decodedToken = await verifyFirebaseToken(token);
    if (!decodedToken) {
      return NextResponse.json(
        { error: "Unauthorized: Invalid token" },
        { status: 401 }
      );
    }

    const db = getDb();
    const adminDoc = await db
      .collection("adminData")
      .doc(decodedToken.uid)
      .get();
    if (!adminDoc.exists) {
      return NextResponse.json(
        { error: "Forbidden: Not an admin" },
        { status: 403 }
      );
    }

    const data = adminDoc.data?.() ?? {};
    const access = accessFor(data);
    return {
      uid: decodedToken.uid,
      kind: "human",
      email: typeof data.email === "string" ? data.email : null,
      access,
      json: respondAs(access),
    };
  } catch (error) {
    if (isFirebaseTokenError(error)) {
      // The token itself is bad (bad signature, malformed, expired): an
      // unauthenticated caller, not a server fault. Never logged, so token
      // probing cannot spam the error log.
      return NextResponse.json(
        { error: "Unauthorized: Invalid token" },
        { status: 401 }
      );
    }
    console.error("Error verifying admin");
    return NextResponse.json(
      { error: "Internal server error during auth" },
      { status: 500 }
    );
  }
}

/**
 * The one admin API guard. Authenticates the caller, then denies unless their
 * effective access (lib/admin-access.ts) includes `scope`. Each route's scope
 * is listed in lib/route-scopes.ts, and a test holds every route to it.
 */
export async function requireScope(
  request: NextRequest,
  scope: Scope
): Promise<AdminIdentity | NextResponse> {
  const identity = await authenticate(request);
  if (identity instanceof NextResponse) return identity;
  if (!hasScope(identity.access, scope)) {
    console.info(
      JSON.stringify({
        event: "admin_scope_denied",
        scope,
        route: request.nextUrl?.pathname,
        access: identity.access.kind,
      })
    );
    return NextResponse.json(
      { error: "Forbidden: your role does not include this", scope },
      { status: 403 }
    );
  }
  return identity;
}

/** Any admin, whatever their scopes. Only for reporting a caller's own access. */
export async function requireMember(
  request: NextRequest
): Promise<AdminIdentity | NextResponse> {
  return authenticate(request);
}
