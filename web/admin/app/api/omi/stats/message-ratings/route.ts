import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { getDb } from "@/lib/firebase/admin";

export const dynamic = "force-dynamic";

// macOS thumbs positive share, computed from the chat DB itself: every rated
// message doc (users/*/messages, rating in {1,-1}) joined to its own journal
// metadata. This replaces the earlier PostHog-event version because events
// carry no message id — the DB join classifies ALL history, not just events
// from tagged builds (Nik, 2026-09-02).
//
// Desktop messages are the ones with a `message_source` of desktop_chat
// (text) or realtime_voice (voice); mobile ratings (message_source null) are
// excluded — this board is macOS. Thumbs on proactive-notification cards
// (journal continuityKey prefixed "notification:" — memory/insight/
// suggestion/task/goal/etc.) rate the notification, not a general Omi
// answer, and are excluded from every series.
type RatioPoint = {
  date: string;
  all: number | null;
  text: number | null;
  voice: number | null;
  upAll: number;
  downAll: number;
};

export type RatedMessageRow = {
  createdAt: string; // ISO
  rating: 1 | -1;
  messageSource: string | null;
  continuityKey: string | null;
};

function ratio(up: number, down: number): number | null {
  const total = up + down;
  return total > 0 ? Math.round((1000 * up) / total) / 10 : null;
}

function mondayKey(ymd: string): string {
  const d = new Date(ymd + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return d.toISOString().slice(0, 10);
}

function nycDay(iso: string): string {
  return new Date(iso).toLocaleDateString("en-CA", {
    timeZone: "America/New_York",
  });
}

const DESKTOP_SOURCES: Record<string, "text" | "voice"> = {
  desktop_chat: "text",
  realtime_voice: "voice",
};

export function classifyRatedMessage(
  row: RatedMessageRow
): "text" | "voice" | "notification" | "mobile" {
  if (row.continuityKey?.startsWith("notification:")) return "notification";
  const lane = row.messageSource ? DESKTOP_SOURCES[row.messageSource] : null;
  return lane ?? "mobile";
}

export function aggregateRatedMessages(rows: RatedMessageRow[]) {
  type Bucket = { up: Record<string, number>; down: Record<string, number> };
  const byDay = new Map<string, Bucket>();
  for (const row of rows) {
    const lane = classifyRatedMessage(row);
    if (lane === "notification" || lane === "mobile") continue;
    const key = nycDay(row.createdAt);
    const bucket = byDay.get(key) ?? { up: {}, down: {} };
    const side = row.rating === 1 ? bucket.up : bucket.down;
    side[lane] = (side[lane] ?? 0) + 1;
    byDay.set(key, bucket);
  }

  const sum = (rec: Record<string, number>, keys?: string[]) =>
    Object.entries(rec)
      .filter(([k]) => !keys || keys.includes(k))
      .reduce((a, [, v]) => a + v, 0);

  const toPoint = (date: string, b: Bucket): RatioPoint => ({
    date,
    all: ratio(sum(b.up), sum(b.down)),
    text: ratio(sum(b.up, ["text"]), sum(b.down, ["text"])),
    voice: ratio(sum(b.up, ["voice"]), sum(b.down, ["voice"])),
    upAll: sum(b.up),
    downAll: sum(b.down),
  });

  const daily = Array.from(byDay.entries())
    .map(([date, bucket]) => toPoint(date, bucket))
    .sort((a, b) => (a.date < b.date ? -1 : 1));

  const byWeek = new Map<string, Bucket>();
  byDay.forEach((bucket, day) => {
    const week = mondayKey(day);
    const acc = byWeek.get(week) ?? { up: {}, down: {} };
    for (const [k, v] of Object.entries(bucket.up))
      acc.up[k] = (acc.up[k] ?? 0) + v;
    for (const [k, v] of Object.entries(bucket.down))
      acc.down[k] = (acc.down[k] ?? 0) + v;
    byWeek.set(week, acc);
  });
  const weekly = Array.from(byWeek.entries())
    .map(([week, bucket]) => ({ ...toPoint(week, bucket), week }))
    .sort((a, b) => (a.week < b.week ? -1 : 1));

  // Legacy shape kept for the existing "Message ratings" volumes panel and
  // /dashboard/classic.
  const data = daily.map((p) => ({
    date: p.date,
    thumbs_up: p.upAll,
    thumbs_down: p.downAll,
    ratio: p.all,
  }));

  return { data, daily, weekly };
}

async function fetchRatedMessages(days: number): Promise<RatedMessageRow[]> {
  const db = getDb();
  const since = new Date(Date.now() - days * 86_400_000);
  // Needs the collection-group composite index on (rating, created_at) —
  // created 2026-09-02 on prod.
  const snap = await db
    .collectionGroup("messages")
    .where("rating", "in", [1, -1])
    .where("created_at", ">=", since)
    .get();
  return snap.docs.map((doc) => {
    const d = doc.data();
    let continuityKey: string | null = null;
    if (typeof d.metadata === "string" && d.metadata) {
      try {
        continuityKey = JSON.parse(d.metadata)?.continuityKey ?? null;
      } catch {
        // unreadable journal metadata → treated as a plain message
      }
    }
    const createdAt =
      typeof d.created_at?.toDate === "function"
        ? d.created_at.toDate().toISOString()
        : new Date(d.created_at).toISOString();
    return {
      createdAt,
      rating: d.rating,
      messageSource: d.message_source ?? null,
      continuityKey,
    };
  });
}

export async function computeMessageRatings(days: number) {
  const rows = await fetchRatedMessages(days);
  return { days, ...aggregateRatedMessages(rows) };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const days = Math.min(
      parseInt(request.nextUrl.searchParams.get("days") || "30", 10) || 30,
      180
    );
    return NextResponse.json(await computeMessageRatings(days));
  } catch (error: any) {
    console.error("Message ratings error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to fetch message ratings" },
      { status: 502 }
    );
  }
}
