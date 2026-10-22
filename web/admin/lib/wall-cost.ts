/** All-in daily cost for the TV wall ("count every cost line", David 2026-10-16;
 * scope 2026-10-22: software cost per customer — no marketing, hardware or COGS).
 *
 * total = GCP net of credits (spend-based CUD arrives as FEE_UTILIZATION_OFFSET
 *         credits) − one-time incident excess
 *       + OpenAI invoice (billing-mode leg)
 *       + Anthropic invoice ONLY on days the admin API reports non-zero spend:
 *         its Mercury cash is Claude team seats, which is SaaS, not per-customer
 *         cost (David 2026-10-22)
 *       + STT: the day's measured FinOps vendor lines when they exist, plus
 *         Mercury cash for the STT vendors with no usage feed (Modulate);
 *         otherwise the dated Soniox-console constant for the Soniox share
 *       + SaaS: a complete, fresh Mercury daily aggregate when available,
 *         otherwise a fixed monthly estimate
 *       + Stripe processing fees, measured from balance transactions. When the
 *         finops key lacks the read scope the line is UNAVAILABLE, never a guess.
 * Each manual estimate carries the date it was read and goes stale past its own
 * line's threshold (STT 14 days, David 2026-10-22; SaaS 35 days).
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
/** A manual estimate older than its line's threshold is flagged stale on the
 * cost frames. STT: 14 days (David 2026-10-22) — a daily measured feed exists,
 * so a console constant must not outlive two weeks. SaaS: a monthly constant. */
export const STT_STALE_DAYS = 14;
export const SAAS_STALE_DAYS = 35;
export const ESTIMATE_STALE_DAYS = SAAS_STALE_DAYS;
export const FEES_UNAVAILABLE_REASON =
  "Stripe processing fees unavailable: the finops Stripe key needs read access to balance transactions (GET /v1/balance_transactions, 'Balance' category)";
/** Mercury STT cash is invoiced spend for vendors with no usage feed
 * (Modulate ~$0.6k/mo). Soniox Mercury cash is prepaid auto-recharge
 * (ledger 2026-08..10: near-daily $100–$700 top-ups), never a daily rate, so
 * it reconciles monthly against the measured usage line and is never added
 * to a day. Deepgram cash counts only on days without any measured line. */
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
  /** Reported Anthropic admin-API spend for the day (null = leg off). Only
   * non-zero values are counted in `total`; seats live in the SaaS line. */
  anthropic: number | null;
  stt: number;
  /** STT came from a measured FinOps vendor line, not the console constant. */
  sttMeasured: boolean;
  /** Mercury cash included for STT vendors with no usage feed that day. */
  sttCash: number;
  saas: number;
  /** SaaS came from a complete, fresh Mercury FinOps aggregate. */
  saasMeasured: boolean;
  /** Measured Stripe processing fees; null = source unavailable, never a guess. */
  fees: number | null;
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
  /** This line's own threshold in days; an estimate older than it is `stale`. */
  staleDays: number;
  stale: boolean;
}

/** Age of each manual cost constant on `now` (UTC days), against its own line's
 * staleness threshold: STT 14 days, SaaS 35 days. */
export function estimateStatus(
  now: Date,
  measured: Partial<Record<EstimateStatus["line"], boolean>> = {}
): EstimateStatus[] {
  const age = (asOf: string) =>
    Math.floor((now.getTime() - Date.parse(`${asOf}T00:00:00Z`)) / 86_400_000);
  return (
    [
      ["STT", STT_MONTHLY_USD, STT_AS_OF, STT_STALE_DAYS],
      ["SaaS", SAAS_MONTHLY_USD, SAAS_AS_OF, SAAS_STALE_DAYS],
    ] as const
  ).map(([line, monthlyUsd, asOf, staleDays]) => {
    const ageDays = age(asOf);
    return {
      line,
      monthlyUsd,
      asOf,
      ageDays,
      staleDays,
      stale: !measured[line] && ageDays > staleDays,
    };
  });
}

/** Measured vendor inputs by date; every map is optional and absent means the
 * source is unavailable (never a silent zero). */
export interface VendorInputs {
  /** date → measured STT USD from FinOps usage lines (Soniox, Deepgram). */
  sttMeasured?: Record<string, number>;
  /** date → Mercury STT-vendor cash by vendor (soniox / deepgram / modulate). */
  sttCash?: Record<string, Record<string, number>>;
  /** date → complete, fresh Mercury SaaS daily USD. */
  saasMeasured?: Record<string, number>;
  /** date → measured Stripe processing fee USD. */
  stripeFees?: Record<string, number>;
}

/** One day's STT line: the measured usage total when it exists, otherwise the
 * dated Soniox constant; plus Mercury cash for vendors with no usage feed.
 * Soniox cash is never added (prepaid recharge, not a rate). Deepgram cash
 * only on days with no measured line at all, so no vendor counts twice. */
export function sttLineFor(
  date: string,
  { sttMeasured, sttCash }: VendorInputs
) {
  const measured = sttMeasured?.[date];
  const cash = sttCash?.[date] || {};
  const modulate = cash.modulate ?? 0;
  const deepgram = measured == null ? cash.deepgram ?? 0 : 0;
  return {
    usd: (measured ?? STT_MONTHLY_USD / DAYS_PER_MONTH) + modulate + deepgram,
    measured: measured != null,
    cash: modulate + deepgram,
  };
}

/** Measured date maps replace their dated estimates for those days; an
 * unavailable source stays visible in `missing` and never becomes a guess. */
export function allInCost(
  days: BillingDay[],
  coverage: { openai?: boolean; anthropic?: boolean } = {},
  vendor: VendorInputs = {},
  /** The fee source itself is unreachable (missing key scope) — distinct from
   * a day simply not being loaded yet. */
  feesUnavailable: string | null = null
) {
  const oneTime = oneTimeExcess(days);
  const missing: string[] = [];
  if (coverage.openai === false) missing.push("OpenAI invoice");
  if (feesUnavailable) missing.push("Stripe processing fees");
  const saasEstimate = SAAS_MONTHLY_USD / DAYS_PER_MONTH;
  const daily: CostDay[] = [...days]
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((d) => {
      const c = (d.components || {}) as Record<string, number>;
      const excess = oneTime.get(d.date)?.usd ?? 0;
      const llmExcess = oneTime.get(d.date)?.llmUsd ?? 0;
      const hasComponents = d.components != null;
      const openai = coverage.openai === false ? null : c.openai ?? 0;
      const anthropic = coverage.anthropic === false ? null : c.anthropic ?? 0;
      // Team seats are SaaS cash (Mercury); the API leg counts only real spend.
      const anthropicCounted =
        anthropic != null && anthropic > 0 ? anthropic : 0;
      // Without components the billing total is GCP + invoices already.
      const gcpNet = hasComponents
        ? (c.gcpInfra ?? 0) + (c.vertexLlm ?? 0)
        : d.total;
      const vertexLlm = (c.vertexLlm ?? 0) - llmExcess;
      const gcp = gcpNet - excess - vertexLlm;
      const stt = sttLineFor(d.date, vendor);
      const measuredSaas = vendor.saasMeasured?.[d.date];
      const saas = measuredSaas ?? saasEstimate;
      const fees = feesUnavailable ? null : vendor.stripeFees?.[d.date] ?? null;
      const total =
        gcp +
        vertexLlm +
        (openai ?? 0) +
        anthropicCounted +
        stt.usd +
        saas +
        (fees ?? 0);
      return {
        date: d.date,
        gcp,
        vertexLlm,
        openai,
        anthropic,
        stt: stt.usd,
        sttMeasured: stt.measured,
        sttCash: stt.cash,
        saas,
        saasMeasured: measuredSaas != null,
        fees,
        oneTime: excess,
        total,
      };
    });
  return { daily, oneTime, missing, feesUnavailable };
}
