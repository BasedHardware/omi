/** All-in daily cost for the TV wall ("count every cost line", David 2026-10-16;
 * scope 2026-10-22: software cost per customer — no marketing, hardware or COGS).
 *
 * total = GCP net of credits (spend-based CUD arrives as FEE_UTILIZATION_OFFSET
 *         credits) − one-time incident excess
 *       + OpenAI invoice (billing-mode leg)
 *       + Anthropic invoice ONLY on days the admin API reports non-zero spend:
 *         its Mercury cash is Claude team seats, which is SaaS, not per-customer
 *         cost (David 2026-10-22)
 *       + STT: Soniox measured from prepaid-balance deltas (the org key has
 *         no usage API) once ≥2 snapshots exist, else the dated console
 *         constant; Modulate modelled (measured volume × committed price, no
 *         vendor API exists) else Mercury cash; Deepgram cash only on days
 *         with no measured line
 *       + SaaS: a complete, fresh Mercury daily aggregate when available,
 *         otherwise a fixed monthly estimate
 *       + Stripe processing fees, measured from balance transactions. When the
 *         finops key lacks the read scope the line is UNAVAILABLE, never a guess.
 * Each manual estimate carries the date it was read and goes stale past its own
 * line's threshold (STT 14 days, David 2026-10-22; SaaS 35 days).
 * A line that cannot be sourced is reported in `missing`, never dropped silently.
 */
import { isLlmService } from "./services/gcp-billing";
import { shiftDay } from "./qualified-activity";

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
/** The Soniox measured day-rate needs the org-key balance snapshots the daily
 * finops job takes; dark table or unmounted key = unavailable, never a guess. */
export const SONIOX_UNAVAILABLE_REASON =
  "Soniox measured STT unavailable: the balance-snapshot line is dark (org key unmounted or the producer table not created yet)";
/** Modulate has no usage or balance API; the modelled line needs the
 * Prometheus per-provider seconds series and the committed rate-card price. */
export const MODULATE_UNAVAILABLE_REASON =
  "Modulate modelled STT unavailable: the Prometheus modulate audio-seconds series or the committed rate-card price is missing";
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
  /** Producer flag on the measured Soniox day ('gap_spread' | 'baseline_reset'). */
  sttFlag: string | null;
  /** The Soniox share of the STT line (balance-delta when measured). */
  sttSonioxUsd: number;
  /** The Modulate share of the STT line (modelled volume or Mercury cash). */
  sttModulateUsd: number;
  /** Modulate dollars came from the modelled volume line, not Mercury cash. */
  sttModulateModelled: boolean;
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
export interface SonioxBalanceInputs {
  /** ≥2 snapshots exist: the derived day-rate series is live (before that the
   * labelled dated console constant stays, David 2026-10-22). */
  ready: boolean;
  /** first UTC day covered by the derived spend series. */
  firstDay: string;
  /** latest snapshot's UTC day, shown as the as-of date. */
  asOf: string | null;
  /** date → measured daily USD (null = flagged baseline-reset day). */
  spend: Record<string, number | null>;
  /** date → producer flag ('gap_spread' | 'baseline_reset'). */
  flags: Record<string, string>;
}
export interface ModulateModelledInputs {
  /** date → modelled USD (measured volume × committed price). */
  byDay: Record<string, { usd: number; priceAsOf?: string }>;
  price: number | null;
  priceAsOf: string | null;
}
export interface VendorInputs {
  /** date → measured STT USD from FinOps usage lines (Deepgram legacy). */
  sttMeasured?: Record<string, number>;
  /** Soniox prepaid-balance day-rate series (replaces the usage line). */
  sonioxBalance?: SonioxBalanceInputs;
  /** Modulate modelled volume line (no vendor API exists). */
  modulateModelled?: ModulateModelledInputs;
  /** date → Mercury STT-vendor cash by vendor (soniox / deepgram / modulate). */
  sttCash?: Record<string, Record<string, number>>;
  /** date → complete, fresh Mercury SaaS daily USD. */
  saasMeasured?: Record<string, number>;
  /** date → measured Stripe processing fee USD. */
  stripeFees?: Record<string, number>;
}

/** One day's STT line. Soniox: the measured balance-delta day-rate once the
 * snapshot series is live (≥2 snapshots), otherwise the labelled dated
 * console constant; a baseline-reset day inside the series is unmeasured and
 * flagged, never the constant again. Modulate: the modelled volume line when
 * present, otherwise Mercury cash (labelled). Soniox Mercury cash is never
 * added (prepaid recharge, not a rate). Deepgram cash only on days without a
 * measured Soniox line, so no vendor counts twice. */
export function sttLineFor(
  date: string,
  { sttMeasured, sonioxBalance, modulateModelled, sttCash }: VendorInputs
) {
  const cash = sttCash?.[date] || {};
  const usage = sttMeasured?.[date];
  const bal = sonioxBalance;
  const inSeries = !!bal?.ready && date >= bal.firstDay;
  const spend = inSeries ? bal!.spend[date] : undefined;
  const flag = inSeries ? bal!.flags[date] : undefined;
  const soniox = inSeries
    ? {
        usd: spend ?? 0,
        measured: spend != null,
        flag:
          spend == null
            ? flag ?? "baseline_reset"
            : flag === "gap_spread"
            ? "gap_spread"
            : null,
      }
    : {
        usd: usage ?? STT_MONTHLY_USD / DAYS_PER_MONTH,
        measured: usage != null,
        flag: null,
      };
  const modelled = modulateModelled?.byDay[date];
  const modulateCash = cash.modulate ?? 0;
  const modulate = modelled
    ? { usd: modelled.usd, modelled: true }
    : { usd: modulateCash, modelled: false };
  const deepgram = soniox.measured ? 0 : cash.deepgram ?? 0;
  return {
    usd: soniox.usd + modulate.usd + deepgram,
    measured: soniox.measured,
    flag: soniox.flag,
    sonioxUsd: soniox.usd,
    modulateUsd: modulate.usd,
    modulateModelled: modulate.modelled,
    cash: (modulate.modelled ? 0 : modulateCash) + deepgram,
  };
}

/** Modulate monthly reconciliation: modelled volume-line USD vs Mercury cash
 * (vendor map `modulate` → stt_vendor) over the trailing `days` ending at
 * `end` inclusive. Null when the modelled line has no days in the window. */
export function modulateReconciliation(
  modelled: ModulateModelledInputs | undefined,
  sttCash: Record<string, Record<string, number>> | undefined,
  end: string,
  days = 30
): { modelledUsd: number; cashUsd: number; variancePct: number | null } | null {
  if (!modelled) return null;
  const start = shiftDay(new Date(`${end}T00:00:00Z`), -(days - 1))
    .toISOString()
    .slice(0, 10);
  let modelledUsd = 0;
  let cashUsd = 0;
  let observed = 0;
  for (const [day, row] of Object.entries(modelled.byDay)) {
    if (day < start || day > end) continue;
    modelledUsd += row.usd;
    cashUsd += sttCash?.[day]?.modulate ?? 0;
    observed++;
  }
  if (!observed) return null;
  return {
    modelledUsd,
    cashUsd,
    variancePct:
      modelledUsd > 0 ? (100 * (cashUsd - modelledUsd)) / modelledUsd : null,
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
        sttFlag: stt.flag,
        sttSonioxUsd: stt.sonioxUsd,
        sttModulateUsd: stt.modulateUsd,
        sttModulateModelled: stt.modulateModelled,
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
