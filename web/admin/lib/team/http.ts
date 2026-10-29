import { NextResponse } from "next/server";
import type { AdminIdentity } from "@/lib/auth";
import { TeamError, type HumanActor } from "@/lib/team/roster";

export function actorFrom(identity: AdminIdentity): HumanActor {
  return { uid: identity.uid, email: identity.email, access: identity.access };
}

/** TeamError carries its own status and safe message; anything else is a 500. */
export function teamErrorResponse(error: unknown, fallback: string) {
  if (error instanceof TeamError) {
    return NextResponse.json(
      { error: error.message },
      { status: error.status }
    );
  }
  console.error(`${fallback}:`, error);
  return NextResponse.json({ error: fallback }, { status: 500 });
}

export async function readJson(request: Request): Promise<unknown> {
  try {
    return await request.json();
  } catch {
    return undefined;
  }
}
