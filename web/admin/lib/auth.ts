import { NextRequest, NextResponse } from "next/server";
import {
  DEV_BYPASS_ENABLED,
  DEV_BYPASS_TOKEN,
  DEV_BYPASS_UID,
} from "@/lib/dev-auth";
import { verifyFirebaseToken, getDb } from "@/lib/firebase/admin";
import { usesFirebaseIssuer, verifyStatsReader } from "@/lib/stats-reader-auth";

/**
 * Verify that the request comes from an authenticated admin user.
 * Human callers need a Firebase ID token and adminData membership. Machine
 * callers receive only the stats GET capability from verifyStatsReader.
 * Returns an authenticated identity or a NextResponse error.
 */
export async function verifyAdmin(
  request: NextRequest
): Promise<{ uid: string } | NextResponse> {
  const authorization = request.headers.get("Authorization");

  if (DEV_BYPASS_ENABLED && authorization === `Bearer ${DEV_BYPASS_TOKEN}`) {
    return { uid: DEV_BYPASS_UID };
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
  if (!usesFirebaseIssuer(token)) return verifyStatsReader(request, token);
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

    return { uid: decodedToken.uid };
  } catch {
    console.error("Error verifying admin");
    return NextResponse.json(
      { error: "Internal server error during auth" },
      { status: 500 }
    );
  }
}
