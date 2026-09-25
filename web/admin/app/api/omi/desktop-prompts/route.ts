import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { getDb } from "@/lib/firebase/admin";
export const dynamic = "force-dynamic";

// Admin CRUD for remote desktop prompts (`desktop_prompts` in Firestore).
// The prod backend serves active documents to every desktop client via
// GET /v2/desktop/prompts — creating or toggling one here reaches users
// within one client poll (~5 minutes), no app release.
const ALLOWED_TYPES = new Set(["stars", "nps", "choice", "banner"]);
const TRIGGER_KINDS = new Set(["app_launch", "question_count"]);

export function normalizePrompt(body: any): { error?: string; doc?: any } {
  const type = String(body?.type ?? "");
  const question = String(body?.question ?? "").trim();
  if (!ALLOWED_TYPES.has(type))
    return {
      error: `type must be one of ${Array.from(ALLOWED_TYPES).join(", ")}`,
    };
  if (!question) return { error: "question is required" };
  const triggerKind = String(body?.trigger_kind ?? "app_launch");
  if (!TRIGGER_KINDS.has(triggerKind)) {
    return {
      error: `trigger_kind must be one of ${Array.from(TRIGGER_KINDS).join(", ")}`,
    };
  }
  const rolloutPct = Math.min(
    Math.max(Number(body?.rollout_pct ?? 100), 0),
    100,
  );
  const doc: any = {
    type,
    question,
    active: Boolean(body?.active ?? false),
    options:
      type === "choice"
        ? (Array.isArray(body?.options) ? body.options : [])
            .map((o: any) => String(o).trim())
            .filter(Boolean)
            .slice(0, 6)
        : [],
    cta:
      type === "banner" && body?.cta_label && body?.cta_url
        ? { label: String(body.cta_label), url: String(body.cta_url) }
        : null,
    trigger: {
      kind: triggerKind,
      count: Math.max(Number(body?.trigger_count ?? 0), 0),
    },
    audience: {
      rollout_pct: rolloutPct,
      channels: (Array.isArray(body?.channels) ? body.channels : [])
        .map((c: any) => String(c))
        .filter((c: string) => ["stable", "beta"].includes(c)),
    },
    updated_at: Date.now() / 1000,
  };
  if (type === "choice" && doc.options.length < 2) {
    return { error: "choice prompts need at least 2 options" };
  }
  return { doc };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;
  const snapshot = await getDb()
    .collection("desktop_prompts")
    .orderBy("created_at", "desc")
    .limit(100)
    .get();
  return NextResponse.json({
    prompts: snapshot.docs.map((d) => ({ id: d.id, ...d.data() })),
  });
}

export async function POST(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;
  const { error, doc } = normalizePrompt(await request.json());
  if (error) return NextResponse.json({ error }, { status: 400 });
  doc.created_at = Date.now() / 1000;
  const ref = await getDb().collection("desktop_prompts").add(doc);
  return NextResponse.json({ id: ref.id, ...doc }, { status: 201 });
}
