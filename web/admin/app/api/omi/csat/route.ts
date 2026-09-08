import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { getDb } from "@/lib/firebase/admin";
export const dynamic = "force-dynamic";

// Admin editor for the built-in Desktop CSAT ask (`csat_config/product` in
// Firestore — a single product-wide doc). The backend serves it to every
// client via GET /v1/csat/config; a save here reaches clients within one
// client poll (~5 minutes) plus the backend's 60s cache. The backend GET is
// the only client read path — this BFF never serves app clients.
const CONFIG_COLLECTION = "csat_config";
const CONFIG_DOC = "product";

type CsatConfigDoc = {
  enabled: boolean;
  title: string;
  body: string;
  thank_you_text: string;
  refer_cta_text: string;
  question_threshold: number;
  comment_max_score: number;
};

// Mirrors `DEFAULT_CONFIG` in backend/database/csat.py: what a missing doc
// means, and the fail-open copy clients render before any fetch succeeds.
export const CSAT_DEFAULT_CONFIG: CsatConfigDoc & { revision: number } = {
  enabled: true,
  title: "How would you rate Omi Desktop?",
  body: "",
  thank_you_text: "Thank you!",
  refer_cta_text: "Enjoying Omi? Give a friend a free month.",
  question_threshold: 3,
  comment_max_score: 3,
  revision: 0,
};

function field(source: unknown, key: string): unknown {
  return source && typeof source === "object" && key in source
    ? (source as Record<string, unknown>)[key]
    : undefined;
}

function clamp(value: unknown, low: number, high: number, fallback: number) {
  const n = Math.round(Number(value));
  if (!Number.isFinite(n)) return fallback;
  return Math.min(Math.max(n, low), high);
}

export function normalizeCsatConfig(body: unknown): {
  error?: string;
  doc?: CsatConfigDoc;
} {
  const title = String(field(body, "title") ?? "").trim();
  if (!title) return { error: "title is required" };
  const doc: CsatConfigDoc = {
    enabled: Boolean(field(body, "enabled") ?? true),
    title,
    body: String(field(body, "body") ?? "").trim(),
    thank_you_text: String(field(body, "thank_you_text") ?? "").trim(),
    refer_cta_text: String(field(body, "refer_cta_text") ?? "").trim(),
    question_threshold: clamp(field(body, "question_threshold"), 1, 50, 3),
    comment_max_score: clamp(field(body, "comment_max_score"), 1, 5, 3),
  };
  return { doc };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;
  const snapshot = await getDb()
    .collection(CONFIG_COLLECTION)
    .doc(CONFIG_DOC)
    .get();
  const config = snapshot.exists
    ? { ...CSAT_DEFAULT_CONFIG, ...snapshot.data() }
    : { ...CSAT_DEFAULT_CONFIG };
  return NextResponse.json({ config });
}

export async function PUT(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;
  const { error, doc } = normalizeCsatConfig(await request.json());
  if (error) return NextResponse.json({ error }, { status: 400 });
  const ref = getDb().collection(CONFIG_COLLECTION).doc(CONFIG_DOC);
  const current = await ref.get();
  const revision = (Number(current.data()?.revision) || 0) + 1;
  const config = {
    ...doc,
    revision,
    updated_at: Date.now() / 1000,
    updated_by: authResult.uid,
  };
  await ref.set(config);
  return NextResponse.json({ config });
}
