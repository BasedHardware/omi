import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { getDb } from "@/lib/firebase/admin";
export const dynamic = "force-dynamic";

// PATCH toggles/edits one remote desktop prompt; DELETE removes it. A
// deactivated or deleted prompt disappears from every client within one
// poll (~5 minutes) — this is the no-release kill path.
export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;
  const { id } = await params;
  const body = await request.json();
  const updates: Record<string, unknown> = { updated_at: Date.now() / 1000 };
  if (typeof body?.active === "boolean") updates.active = body.active;
  if (typeof body?.question === "string" && body.question.trim()) {
    updates.question = body.question.trim();
  }
  if (body?.rollout_pct !== undefined) {
    updates["audience.rollout_pct"] = Math.min(
      Math.max(Number(body.rollout_pct), 0),
      100,
    );
  }
  await getDb().collection("desktop_prompts").doc(id).update(updates);
  return NextResponse.json({ id, updated: true });
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;
  const { id } = await params;
  await getDb().collection("desktop_prompts").doc(id).delete();
  return NextResponse.json({ id, deleted: true });
}
