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

// Per-service monthly cost rows — sourced from the team's Apr projection.
// Each service also carries a `desktopWeight` / `mobileWeight` pair (sum=1.0)
// that reflects how the workload is split across platforms in practice.
// These defaults came from the team-beasts daily report: Anthropic is
// overwhelmingly desktop (floating-bar Claude Opus), Deepgram and Gemini
// lean mobile (device-connected audio + mobile-only features), GCP compute
// splits by DAU share. Override via ADMIN_SERVICE_COSTS_JSON env var.
interface ServiceCostEntry {
  service: string;
  mtd: number;
  projection: number;
  desktopWeight: number;
  mobileWeight: number;
}

const DEFAULT_SERVICE_COSTS: ServiceCostEntry[] = [
  // Gemini: mobile-weighted (app features, translation fallback).
  { service: 'Gemini API', mtd: 7829, projection: 17803, desktopWeight: 0.3, mobileWeight: 0.7 },
  // Compute Engine: shared infra, split by DAU share (27% desktop / 73% mobile on Apr 16).
  { service: 'Compute Engine', mtd: 4228, projection: 11417, desktopWeight: 0.27, mobileWeight: 0.73 },
  // Translate: 100% mobile feature.
  { service: 'Translate', mtd: 2814, projection: 8302, desktopWeight: 0.0, mobileWeight: 1.0 },
  // App Engine: backend for both — DAU split.
  { service: 'App Engine', mtd: 3022, projection: 8299, desktopWeight: 0.27, mobileWeight: 0.73 },
  // Cloud Run: listen/pusher subservices — mostly mobile audio pipeline.
  { service: 'Cloud Run', mtd: 1457, projection: 4157, desktopWeight: 0.2, mobileWeight: 0.8 },
  // Cloud Storage: audio uploads + chat file uploads — mostly mobile.
  { service: 'Cloud Storage', mtd: 1432, projection: 3487, desktopWeight: 0.3, mobileWeight: 0.7 },
  // Networking / Logging / Others: split by DAU.
  { service: 'Networking', mtd: 495, projection: 1350, desktopWeight: 0.27, mobileWeight: 0.73 },
  { service: 'Cloud Logging', mtd: 326, projection: 890, desktopWeight: 0.27, mobileWeight: 0.73 },
  { service: 'Others', mtd: 638, projection: 1741, desktopWeight: 0.27, mobileWeight: 0.73 },
  // External LLM bills, not in the GCP table. Projections are the team-
  // beasts daily-report 7-day totals extrapolated to 30 days
  // (weekly × 30/7) so the dashboard matches the reported ~$4.6K/day run
  // rate instead of undershooting at the older MTD-based estimates.
  // Anthropic is almost entirely desktop (Claude-Opus floating bar);
  // OpenAI splits 50/50.
  { service: 'Anthropic', mtd: 7163, projection: 30699, desktopWeight: 0.9, mobileWeight: 0.1 },
  { service: 'OpenAI', mtd: 7442, projection: 31895, desktopWeight: 0.5, mobileWeight: 0.5 },
  { service: 'Deepgram', mtd: 5290, projection: 22672, desktopWeight: 0.2, mobileWeight: 0.8 },
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
        return {
          service: String(r.service),
          mtd: Number(r.mtd) || 0,
          projection: Number(r.projection) || 0,
          desktopWeight: Number.isFinite(d) ? d : 0.5,
          mobileWeight: Number.isFinite(m) ? m : 0.5,
        };
      });
  } catch {
    return DEFAULT_SERVICE_COSTS;
  }
}

// Sum of each service's monthly projection, split by its platform weight.
// Used as the overhead budget for the daily cost series when per-service
// attribution is available.
function computeMonthlyOverheadByPlatform(services: ServiceCostEntry[]): { desktop: number; mobile: number; total: number } {
  let desktop = 0;
  let mobile = 0;
  let total = 0;
  for (const s of services) {
    desktop += s.projection * s.desktopWeight;
    mobile += s.projection * s.mobileWeight;
    total += s.projection;
  }
  return { desktop, mobile, total };
}

const CACHE_PREFIX = "admin:stats:infra-costs:v2";
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
    // Anthropic 90% desktop) instead of a single global ratio.
    const breakdown: ServiceCostRow[] = services.map((row) => ({
      service: row.service,
      mtdUsd: Math.round(row.mtd * 100) / 100,
      aprProjectionUsd: Math.round(row.projection * 100) / 100,
      desktopProjectionUsd: Math.round(row.projection * row.desktopWeight * 100) / 100,
      mobileProjectionUsd: Math.round(row.projection * row.mobileWeight * 100) / 100,
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
