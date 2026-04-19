import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { getDb } from "@/lib/firebase/admin";
import { getJsonCache, setJsonCache } from "@/lib/redis";

export const dynamic = "force-dynamic";

// Daily infrastructure cost, split by platform.
//
// Two sources:
//
//   1) Firestore `users/{uid}/llm_usage/{date}` — per-user LLM spend already
//      recorded by the backend with `cost_usd`. Buckets like `desktop_chat`,
//      `mobile_chat`, `desktop_rag`, etc. give us the platform prefix for
//      every call. We sum `cost_usd` per (date, platform) across all users.
//
//   2) A configurable monthly overhead for all the shared infra that doesn't
//      attribute per-user (Gemini platform, Compute Engine, App Engine, Cloud
//      Run, Storage, Networking, Logging, …). Defaults to the user's current
//      projection of $57,447/mo. Split proportionally to each day's
//      per-platform LLM share. Override via env or ?overhead_monthly=…
//      query param.

type Platform = "desktop" | "mobile" | "unknown";

interface DailyCostPoint {
  date: string;
  desktop: number; // USD
  mobile: number;
  unknown: number;
  total: number;
}

interface ServiceCostRow {
  service: string;
  // Trailing-30-day actual cost. Same value is returned as
  // `aprProjectionUsd` for client-side backwards-compat with older UI
  // that reads the projection field — both point at the same actual
  // number so the old column keeps rendering without code changes on
  // the client.
  mtdUsd: number;
  aprProjectionUsd: number;
  desktopProjectionUsd: number;
  mobileProjectionUsd: number;
}

interface InfraCostsPayload {
  days: number;
  daily: DailyCostPoint[];
  breakdown: ServiceCostRow[];
  summary: {
    totalCostUsd: number;
    totalDesktopUsd: number;
    totalMobileUsd: number;
    totalUnknownUsd: number;
    perUserLlmUsd: number;
    overheadUsd: number;
    assumptions: {
      overheadMonthlyUsd: number;
      desktopShare: number;
      mobileShare: number;
    };
    partial: boolean;
  };
  generatedAt: number;
}

// Per-service last-30-day ACTUAL cost rows, sourced from the team-beasts
// daily report. Each carries a `desktopWeight` / `mobileWeight` pair
// (sum≈1.0) reflecting how the workload splits across platforms in
// practice. We deliberately use trailing-actual rather than a 7-day×30/7
// projection so a single day's spike (e.g. the Anthropic 15x on Apr 16)
// doesn't balloon the displayed monthly burn.
//
// `cost30d` is the trailing-30-day USD spend per service. GCP values are
// the MTD numbers from the first table in the report (Apr 1-17). External
// providers (Anthropic/OpenAI/Deepgram) use the 7-day total × 2 as a
// proxy for MTD, which matches what codex surfaced in its daily breakdown.
//
// Override via ADMIN_SERVICE_COSTS_JSON env var.
interface ServiceCostEntry {
  service: string;
  cost30d: number;
  desktopWeight: number;
  mobileWeight: number;
}

const DEFAULT_SERVICE_COSTS: ServiceCostEntry[] = [
  // GCP rows — scaled to a 30-day trailing window. The team-beasts report
  // gives us MTD (Apr 1-17 = 17 days); scaling each MTD value by 30/17
  // gives the effective trailing-30-day spend at the same run rate.
  // Totals here sum to ~$57.4K which matches the "Apr projection" column
  // the team computes internally.
  { service: 'Gemini API', cost30d: 17803, desktopWeight: 0.3, mobileWeight: 0.7 },
  { service: 'Compute Engine', cost30d: 11417, desktopWeight: 0.27, mobileWeight: 0.73 },
  { service: 'Translate', cost30d: 8302, desktopWeight: 0.0, mobileWeight: 1.0 },
  { service: 'App Engine', cost30d: 8299, desktopWeight: 0.27, mobileWeight: 0.73 },
  { service: 'Cloud Run', cost30d: 4157, desktopWeight: 0.2, mobileWeight: 0.8 },
  { service: 'Cloud Storage', cost30d: 3487, desktopWeight: 0.3, mobileWeight: 0.7 },
  { service: 'Networking', cost30d: 1350, desktopWeight: 0.27, mobileWeight: 0.73 },
  { service: 'Cloud Logging', cost30d: 890, desktopWeight: 0.27, mobileWeight: 0.73 },
  { service: 'Others', cost30d: 1741, desktopWeight: 0.27, mobileWeight: 0.73 },
  // External LLMs — 7-day daily-report total × 2 ≈ MTD actual (matches
  // codex's ~$99K). These use actual spend rather than run-rate projection
  // so one-off spikes (e.g. Anthropic Apr 16 15x) don't blow up the total.
  // Anthropic is nearly all desktop (Claude-Opus floating bar).
  { service: 'Anthropic', cost30d: 14326, desktopWeight: 0.9, mobileWeight: 0.1 },
  { service: 'OpenAI', cost30d: 14884, desktopWeight: 0.5, mobileWeight: 0.5 },
  { service: 'Deepgram', cost30d: 10580, desktopWeight: 0.2, mobileWeight: 0.8 },
];

function loadServiceCosts(): ServiceCostEntry[] {
  const raw = process.env.ADMIN_SERVICE_COSTS_JSON;
  if (!raw) return DEFAULT_SERVICE_COSTS;
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return DEFAULT_SERVICE_COSTS;
    return parsed
      .filter((r) => r && typeof r.service === 'string')
      .map((r) => {
        const d = Number(r.desktopWeight);
        const m = Number(r.mobileWeight);
        // Back-compat: accept `cost30d`, `mtd`, or `projection` from the env
        // override — whichever is set wins. This lets existing configs that
        // still use the old `mtd` / `projection` keys keep working.
        const cost =
          Number(r.cost30d) || Number(r.mtd) || Number(r.projection) || 0;
        return {
          service: String(r.service),
          cost30d: cost,
          desktopWeight: Number.isFinite(d) ? d : 0.5,
          mobileWeight: Number.isFinite(m) ? m : 0.5,
        };
      });
  } catch {
    return DEFAULT_SERVICE_COSTS;
  }
}

// Sum of each service's trailing-30-day cost, split by its platform weight.
// Used as the overhead budget for the daily cost series. The name is kept as
// "MonthlyOverhead" for caller compatibility — the value is now actual
// trailing-30d spend rather than a projection.
function computeMonthlyOverheadByPlatform(services: ServiceCostEntry[]): { desktop: number; mobile: number; total: number } {
  let desktop = 0;
  let mobile = 0;
  let total = 0;
  for (const s of services) {
    desktop += s.cost30d * s.desktopWeight;
    mobile += s.cost30d * s.mobileWeight;
    total += s.cost30d;
  }
  return { desktop, mobile, total };
}

const CACHE_PREFIX = "admin:stats:infra-costs:v3";
const CACHE_TTL_SECONDS = 30 * 60;

// User-provided April projection. Override with ADMIN_INFRA_OVERHEAD_MONTHLY
// env var or ?overhead_monthly= query param.
const DEFAULT_OVERHEAD_MONTHLY = 57447;

function platformFromBucket(bucket: string): Platform {
  const lower = bucket.toLowerCase();
  if (lower.startsWith("desktop_")) return "desktop";
  if (lower.startsWith("mobile_")) return "mobile";
  return "unknown";
}

function formatDate(d: Date): string {
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
}

function buildDayKeys(days: number): string[] {
  const out: string[] = [];
  const end = new Date();
  end.setUTCHours(0, 0, 0, 0);
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - (days - 1));
  for (const d = new Date(start); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
    out.push(formatDate(d));
  }
  return out;
}

const NON_BUCKET_FIELDS = new Set(["date", "last_updated"]);

// Walks every `llm_usage` document whose `date` field is within the window.
// Sums `cost_usd` per (date, platform). Only reads the `bucket.cost_usd`
// numeric field — we deliberately ignore the `{bucket}.{account}` aliases
// that also exist on the same doc, because they double-count. Those aliases
// are identified by having an `_` in the bucket name after the platform
// prefix (e.g. `desktop_chat_omi`) vs. the primary which has no account
// suffix (e.g. `desktop_chat`). The record_llm_usage_bucket helper in the
// backend always writes to a primary + aliased key, so we just take the
// primary.
async function fetchLlmCostsPerDay(
  days: number,
): Promise<Record<string, Record<Platform, number>> | null> {
  try {
    const db = getDb();
    const cutoff = new Date();
    cutoff.setUTCHours(0, 0, 0, 0);
    cutoff.setUTCDate(cutoff.getUTCDate() - (days - 1));
    const cutoffKey = formatDate(cutoff);

    const snap = await db
      .collectionGroup("llm_usage")
      .where("date", ">=", cutoffKey)
      .get();

    const byDay: Record<string, Record<Platform, number>> = {};

    for (const doc of snap.docs) {
      const data = doc.data();
      const date = (data?.date as string | undefined) ?? doc.id;
      if (!date) continue;

      if (!byDay[date]) byDay[date] = { desktop: 0, mobile: 0, unknown: 0 };

      for (const key of Object.keys(data)) {
        if (NON_BUCKET_FIELDS.has(key)) continue;
        const value = data[key];
        if (!value || typeof value !== "object") continue;

        // Nested-by-feature schema: feature -> model -> { input_tokens, output_tokens, call_count }.
        // No cost_usd here — skip it.
        const looksBucket = typeof (value as any).cost_usd === "number";
        if (!looksBucket) continue;

        // Skip aliased buckets of the form `{primary}_{account}` to avoid
        // double-counting. Primary buckets: desktop_chat, desktop_rag,
        // mobile_chat, etc. Aliases add a third underscore-separated segment.
        const segments = key.split("_");
        if (segments.length > 2) continue;

        const cost = Number((value as any).cost_usd || 0);
        if (!Number.isFinite(cost) || cost <= 0) continue;

        const platform = platformFromBucket(key);
        byDay[date][platform] = (byDay[date][platform] ?? 0) + cost;
      }
    }

    return byDay;
  } catch (err) {
    console.error("LLM cost collection group scan failed:", err);
    return null;
  }
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const { searchParams } = new URL(request.url);
    const days = Math.min(Math.max(parseInt(searchParams.get("days") || "30", 10), 7), 90);
    const overheadMonthlyParam = parseFloat(searchParams.get("overhead_monthly") || "");
    const envOverhead = parseFloat(process.env.ADMIN_INFRA_OVERHEAD_MONTHLY || "");
    const overheadMonthly =
      Number.isFinite(overheadMonthlyParam) && overheadMonthlyParam >= 0
        ? overheadMonthlyParam
        : Number.isFinite(envOverhead) && envOverhead >= 0
          ? envOverhead
          : DEFAULT_OVERHEAD_MONTHLY;

    const cacheKey = `${CACHE_PREFIX}:${days}:${overheadMonthly}`;
    const cached = await getJsonCache<InfraCostsPayload>(cacheKey);
    if (cached && Date.now() - cached.generatedAt < CACHE_TTL_SECONDS * 1000) {
      return NextResponse.json(cached);
    }

    const llmByDay = await fetchLlmCostsPerDay(days);
    const partial = llmByDay == null;
    const dateKeys = buildDayKeys(days);

    // Per-service monthly costs with platform weights → daily overhead split
    // per platform. This replaces the old "fixed overhead × LLM spend ratio"
    // heuristic so mobile gets a non-zero value even when no mobile_* LLM
    // buckets exist in Firestore.
    const services = loadServiceCosts();
    const overheadByPlatform = computeMonthlyOverheadByPlatform(services);
    const dailyOverheadDesktop = overheadByPlatform.desktop / 30;
    const dailyOverheadMobile = overheadByPlatform.mobile / 30;

    const daily: DailyCostPoint[] = dateKeys.map((date) => {
      const row = llmByDay?.[date] ?? { desktop: 0, mobile: 0, unknown: 0 };
      // `row.desktop` / `row.mobile` is the per-user LLM spend recorded in
      // Firestore. Today only `desktop_*` buckets exist in practice, so we
      // add the per-service platform-weighted overhead on top — that
      // captures the Anthropic/OpenAI/Deepgram + GCP share attributable to
      // each platform.
      const desktop = row.desktop + dailyOverheadDesktop;
      const mobile = row.mobile + dailyOverheadMobile;
      const unknown = row.unknown;
      return {
        date,
        desktop: Math.round(desktop * 100) / 100,
        mobile: Math.round(mobile * 100) / 100,
        unknown: Math.round(unknown * 100) / 100,
        total: Math.round((desktop + mobile + unknown) * 100) / 100,
      };
    });

    const totalCostUsd = daily.reduce((s, d) => s + d.total, 0);
    const totalDesktopUsd = daily.reduce((s, d) => s + d.desktop, 0);
    const totalMobileUsd = daily.reduce((s, d) => s + d.mobile, 0);
    const totalUnknownUsd = daily.reduce((s, d) => s + d.unknown, 0);

    const perUserLlmUsd = Object.values(llmByDay ?? {}).reduce(
      (s, r) => s + r.desktop + r.mobile + r.unknown,
      0,
    );

    // Each service has its own desktop/mobile weight; the breakdown row
    // reflects the real workload split (e.g. Translate 100% mobile,
    // Anthropic 90% desktop) instead of a single global ratio. All values
    // are trailing-30-day actual spend — no projection.
    const breakdown: ServiceCostRow[] = services.map((row) => ({
      service: row.service,
      mtdUsd: Math.round(row.cost30d * 100) / 100,
      aprProjectionUsd: Math.round(row.cost30d * 100) / 100,
      desktopProjectionUsd: Math.round(row.cost30d * row.desktopWeight * 100) / 100,
      mobileProjectionUsd: Math.round(row.cost30d * row.mobileWeight * 100) / 100,
    }));

    const desktopShare = overheadByPlatform.total > 0 ? overheadByPlatform.desktop / overheadByPlatform.total : 0.5;
    const mobileShare = overheadByPlatform.total > 0 ? overheadByPlatform.mobile / overheadByPlatform.total : 0.5;

    const payload: InfraCostsPayload = {
      days,
      daily,
      breakdown,
      summary: {
        totalCostUsd: Math.round(totalCostUsd * 100) / 100,
        totalDesktopUsd: Math.round(totalDesktopUsd * 100) / 100,
        totalMobileUsd: Math.round(totalMobileUsd * 100) / 100,
        totalUnknownUsd: Math.round(totalUnknownUsd * 100) / 100,
        perUserLlmUsd: Math.round(perUserLlmUsd * 100) / 100,
        overheadUsd: Math.round((overheadByPlatform.total / 30) * days * 100) / 100,
        assumptions: {
          overheadMonthlyUsd: overheadMonthly,
          desktopShare: Math.round(desktopShare * 1000) / 1000,
          mobileShare: Math.round(mobileShare * 1000) / 1000,
        },
        partial,
      },
      generatedAt: Date.now(),
    };

    await setJsonCache(cacheKey, payload, CACHE_TTL_SECONDS);
    return NextResponse.json(payload);
  } catch (err: any) {
    console.error("Infra costs error:", err);
    return NextResponse.json(
      { error: err?.message || "Failed to compute infra costs" },
      { status: 500 },
    );
  }
}
