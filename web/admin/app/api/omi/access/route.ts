import { NextRequest, NextResponse } from "next/server";
import { requireMember } from "@/lib/auth";

export const dynamic = "force-dynamic";

/** The caller's own effective access, so the dashboard can hide what they lack. */
export async function GET(request: NextRequest) {
  const authResult = await requireMember(request);
  if (authResult instanceof NextResponse) return authResult;

  const { access } = authResult;
  return authResult.json({
    uid: authResult.uid,
    kind: access.kind,
    role: access.role,
    roleLabel: access.roleLabel,
    scopes: access.scopes,
  });
}
