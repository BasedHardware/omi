/** All-in daily cost for the TV wall ("count every cost line", David 2026-10-16).
 *
 * total = GCP net of credits (spend-based CUD arrives as FEE_UTILIZATION_OFFSET
 *         credits) − one-time incident excess
 *       + OpenAI + Anthropic invoices (billing-mode legs)
 *       + STT: a measured FinOps vendor line when one exists for the day,
 *         otherwise a constant read from the Soniox console ("estimate")
 *       + SaaS: a complete, fresh Mercury daily aggregate when available,
 *         otherwise a fixed monthly estimate.
 * Each estimate carries the date it was read; past ESTIMATE_STALE_DAYS the
 * series flags it stale so the board can say so unless the latest day is
 * measured.
 * A line that cannot be sourced is reported in `missing`, never dropped silently.
 */
import { isLlmService } from "./services/gcp-billing";

export const SAAS_MONTHLY_USD = 4800; // "Omi Cost vs Revenue" artifact, Oct 2026 row
export const SAAS_AS_OF = "2026-10-16";
/** Soniox console, October 2026 (read 2026-10-16): ≈ $174/day; the KB
 * transcription-cost note's ≈ $204/day agrees in order. The FinOps
 * `stt_vendor_low` model (~$10K/mo) overstated it and is no longer used.
 * A measured FinOps line replaces this dated fallback on its own day. */
export const STT_MONTHLY_USD = 5300;
export const STT_AS_OF = "2026-10-16";
export const STT_SOURCE = `Soniox console, Oct 2026, read ${STT_AS_OF}`;
/** A manual estimate older than this is flagged stale on the cost frames. */
export const ESTIMATE_STALE_DAYS = 35;
const DAYS_PER_MONTH = 365.25 / 12;
/** A GCP service-day is a one-time incident when it exceeds its trailing
 * 14-day median by both $500 and 2× (e.g. the 2026-09-07 Coldline migration:
 * Cloud Storage $13,967 against ~$200/day). Only the excess is excluded. */
export const ONE_TIME = { lookbackDays: 14, minExcessUsd: 500, multiple: 2 };

export interface BillingDay {
  date: string;
  total: number;
  components?: Record<string, unknown>;
}
export interface CostDay {
  date: string;
  gcp: number;
  vertexLlm: number;
  openai: number | null;
  anthropic: number | null;
  stt: number;
  /** STT came from a measured FinOps vendor line, not the console constant. */
  sttMeasured: boolean;
  saas: number;
  /** SaaS came from a complete, fresh Mercury FinOps aggregate. */
  saasMeasured: boolean;
  oneTime: number;
  total: number;
}

const median = (xs: number[]) => {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

export function oneTimeExcess(days: BillingDay[]) {
  const sorted = [...days].sort((a, b) => a.date.localeCompare(b.date));
  const out = new Map<
    string,
    { usd: number; llmUsd: number; services: string[] }
  >();
  sorted.forEach((day, i) => {
    const services = (day.components?.gcpServices || {}) as Record<
      string,
      number
    >;
    const prior = sorted.slice(Math.max(0, i - ONE_TIME.lookbackDays), i);
    if (prior.length < 7) return; // not enough history to call a spike
    for (const [service, usd] of Object.entries(services)) {
      const base = median(
        prior.map(
          (d) =>
            ((d.components?.gcpServices || {}) as Record<string, number>)[
              service
            ] ?? 0
        )
      );
      const excess = usd - base;
      if (excess >= ONE_TIME.minExcessUsd && usd >= ONE_TIME.multiple * base) {
        const entry = out.get(day.date) || { usd: 0, llmUsd: 0, services: [] };
        entry.usd += excess;
        if (isLlmService(service)) entry.llmUsd += excess;
        entry.services.push(service);
        out.set(day.date, entry);
      }
    }
  });
  return out;
}

export interface EstimateStatus {
  line: "STT" | "SaaS";
  monthlyUsd: number;
  asOf: string;
  ageDays: number;
  stale: boolean;
}

/** Age of each manual cost constant on `now` (UTC days). */
export function estimateStatus(
  now: Date,
  measured: Partial<Record<EstimateStatus["line"], boolean>> = {}
): EstimateStatus[] {
  const age = (asOf: string) =>
    Math.floor((now.getTime() - Date.parse(`${asOf}T00:00:00Z`)) / 86_400_000);
  return (
    [
      ["STT", STT_MONTHLY_USD, STT_AS_OF],
      ["SaaS", SAAS_MONTHLY_USD, SAAS_AS_OF],
    ] as const
  ).map(([line, monthlyUsd, asOf]) => {
    const ageDays = age(asOf);
    return {
      line,
      monthlyUsd,
      asOf,
      ageDays,
      stale: !measured[line] && ageDays > ESTIMATE_STALE_DAYS,
    };
  });
}

/** Measured date maps replace their dated estimates for those days. */
export function allInCost(
  days: BillingDay[],
  coverage: { openai?: boolean; anthropic?: boolean } = {},
  sttMeasured: Record<string, number> = {},
  saasMeasured: Record<string, number> = {}
) {
  const oneTime = oneTimeExcess(days);
  const missing: string[] = [];
  if (coverage.openai === false) missing.push("OpenAI invoice");
  if (coverage.anthropic === false) missing.push("Anthropic invoice");
  const saasEstimate = SAAS_MONTHLY_USD / DAYS_PER_MONTH;
  const sttUsd = STT_MONTHLY_USD / DAYS_PER_MONTH;
  const daily: CostDay[] = [...days]
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((d) => {
      const c = (d.components || {}) as Record<string, number>;
      const excess = oneTime.get(d.date)?.usd ?? 0;
      const llmExcess = oneTime.get(d.date)?.llmUsd ?? 0;
      const hasComponents = d.components != null;
      const openai = coverage.openai === false ? null : c.openai ?? 0;
      const anthropic = coverage.anthropic === false ? null : c.anthropic ?? 0;
      // Without components the billing total is GCP + invoices already.
      const gcpNet = hasComponents
        ? (c.gcpInfra ?? 0) + (c.vertexLlm ?? 0)
        : d.total;
      const vertexLlm = (c.vertexLlm ?? 0) - llmExcess;
      const gcp = gcpNet - excess - vertexLlm;
      const measured = sttMeasured[d.date];
      const stt = measured ?? sttUsd;
      const measuredSaas = saasMeasured[d.date];
      const saas = measuredSaas ?? saasEstimate;
      const total =
        gcp + vertexLlm + (openai ?? 0) + (anthropic ?? 0) + stt + saas;
      return {
        date: d.date,
        gcp,
        vertexLlm,
        openai,
        anthropic,
        stt,
        sttMeasured: measured != null,
        saas,
        saasMeasured: measuredSaas != null,
        oneTime: excess,
        total,
      };
    });
  return { daily, oneTime, missing };
}
