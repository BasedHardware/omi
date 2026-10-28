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
 *         no usage API) once ≥2 snapshots exist and the day is covered by the
 *         series — a stale or broken series falls back to the dated console
 *         constant, flagged, never $0 or a phantom reset; Modulate modelled
 *         (measured volume × committed price, no vendor API exists) else
 *         Mercury cash; Deepgram combines independently (measured usage, else
 *         its own Mercury cash) so one provider never hides another
 *       + SaaS: a complete, fresh Mercury daily aggregate when available,
 *         otherwise a fixed monthly estimate
 *       + Infra (non-GCP): Mercury-categorized Modal/AWS/Runpod-class cash as
 *         a run rate with the SaaS cadence treatment (yearly and one-off
 *         charges amortized ÷12); never GCP (billing export) or STT/fee cash
 *         (their own lines), so no dollar is counted twice. While the producer
 *         labels the run rate partial it is a FLOOR (it cannot see annual
 *         bills posted before the ledger starts), so the day shows
 *         max(measured, dated fallback), still labelled partial. Mercury
 *         `stripe_fees` cash rejoins this line only on a day the measured fee
 *         line is unavailable — never on both lines, never on neither.
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
/** Non-GCP infra (Modal, AWS, Runpod, …) run-rate fallback, read 2026-10-23
 * read-only from the Mercury ledger (`mercury_vendor_spend_daily`, category
 * `infra_non_gcp`, 2026-07-04..2026-10-20) with the SaaS cadence treatment:
 * monthly cloud bills (Cloudflare, Hetzner) run at ≈ $114/mo; the once-a-year
 * Modal compute wire ($12,000 on 2026-01-08, the 13-month read-only check
 * recorded in the finops README) predates the ledger and amortizes ÷12 to
 * $1,000/mo through 2027-01-07. The `stripe_fees` vendor is excluded — its
 * cash is the measured Stripe fee line. Replaced per day by the FinOps
 * `mercury_infra_non_gcp_daily` run rate once that table has complete fresh
 * rows whose annual history is complete; while the producer still labels a
 * day partial (the ledger cannot see the Modal wire until the 400-day
 * backfill runs) the day shows max(measured, this constant) — see
 * `allInCost`. */
export const INFRA_MONTHLY_USD = 1114;
export const INFRA_AS_OF = "2026-10-23";
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
/** The infra fallback is a monthly run-rate constant like SaaS, so the SaaS
 * staleness threshold applies (35 days). */
export const INFRA_STALE_DAYS = SAAS_STALE_DAYS;
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
  /** The prepaid Vertex reserved-capacity (Provisioned Throughput) net USD
   * inside `vertexLlm` for the day. NOT subtracted from `total` — the all-in
   * stack counts every dollar; the variable-margin tile excludes it (David
   * 2026-10-23: prepaid, sunk). 0 when the billing read predates the column. */
  vertexReserved: number;
  openai: number | null;
  /** Reported Anthropic admin-API spend for the day (null = leg off). Only
   * non-zero values are counted in `total`; seats live in the SaaS line. */
  anthropic: number | null;
  stt: number;
  /** STT came from a measured vendor line (Soniox balance delta or Deepgram
   * usage), not the console constant; Modulate modelled volume is NOT measured. */
  sttMeasured: boolean;
  /** The Soniox leg of the day is measured (balance delta or usage line). */
  sttSonioxMeasured: boolean;
  /** Producer flag on the measured Soniox day ('gap_spread' | 'baseline_reset'
   * | 'snapshot_gap'). */
  sttFlag: string | null;
  /** The Soniox share of the STT line (balance-delta when measured). */
  sttSonioxUsd: number;
  /** The Modulate share of the STT line (modelled volume or Mercury cash). */
  sttModulateUsd: number;
  /** Modulate dollars came from the modelled volume line, not Mercury cash. */
  sttModulateModelled: boolean;
  /** The Deepgram share of the STT line (measured usage or Mercury cash). */
  sttDeepgramUsd: number;
  /** Deepgram dollars came from the measured usage line, not Mercury cash. */
  sttDeepgramMeasured: boolean;
  /** Mercury cash included for STT vendors with no usage feed that day. */
  sttCash: number;
  saas: number;
  /** SaaS came from a complete, fresh Mercury FinOps aggregate. */
  saasMeasured: boolean;
  /** Non-GCP infra dollars on the line: the measured run rate when complete,
   * max(measured, dated constant) while the producer labels it partial, or
   * the dated constant without a row — plus `infraFeesCash` (below). */
  infra: number;
  /** A complete, fresh Mercury FinOps infra row exists for the day. */
  infraMeasured: boolean;
  /** The producer's run rate for the day (fee cash excluded); null without a
   * row. Kept even when the dated fallback floors it, so the line can say so. */
  infraMeasuredUsd: number | null;
  /** The producer's partial reason (`history_under_12_months` or
   * `uncategorized_above_threshold`); null when complete or without a row. */
  infraPartial: string | null;
  /** The dated fallback replaced a partial measured run rate that was lower:
   * a partial run rate is a floor (annual bills before the ledger start are
   * invisible to it), never a reason to show less than the dated estimate. */
  infraFloored: boolean;
  /** Mercury `stripe_fees` cash run rate counted on the infra line because the
   * measured Stripe fee line is unavailable for the day; 0 whenever the fee
   * line owns that money (or there is no such cash). */
  infraFeesCash: number;
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
  line: "STT" | "SaaS" | "Infra";
  monthlyUsd: number;
  asOf: string;
  ageDays: number;
  /** This line's own threshold in days; an estimate older than it is `stale`. */
  staleDays: number;
  stale: boolean;
}

/** Age of each manual cost constant on `now` (UTC days), against its own line's
 * staleness threshold: STT 14 days, SaaS 35 days. `broken` marks a line whose
 * measured feed stopped (e.g. the Soniox snapshot series no longer covering the
 * cutoff day): such a line is stale NOW, not only once its constant ages out —
 * a stale snapshot must never present the dated constant as current. */
export function estimateStatus(
  now: Date,
  measured: Partial<Record<EstimateStatus["line"], boolean>> = {},
  broken: Partial<Record<EstimateStatus["line"], boolean>> = {}
): EstimateStatus[] {
  const age = (asOf: string) =>
    Math.floor((now.getTime() - Date.parse(`${asOf}T00:00:00Z`)) / 86_400_000);
  return (
    [
      ["STT", STT_MONTHLY_USD, STT_AS_OF, STT_STALE_DAYS],
      ["SaaS", SAAS_MONTHLY_USD, SAAS_AS_OF, SAAS_STALE_DAYS],
      ["Infra", INFRA_MONTHLY_USD, INFRA_AS_OF, INFRA_STALE_DAYS],
    ] as const
  ).map(([line, monthlyUsd, asOf, staleDays]) => {
    const ageDays = age(asOf);
    return {
      line,
      monthlyUsd,
      asOf,
      ageDays,
      staleDays,
      stale: (!measured[line] && ageDays > staleDays) || Boolean(broken[line]),
    };
  });
}

/** Assemble the Soniox balance series for `VendorInputs` from the raw FinOps
 * read. `lastDay` is the last day a spend row covers — the series ends there,
 * and later days fall back to the dated constant instead of reading as $0. */
export function sonioxBalanceInputs(
  soniox: {
    snapshots: number;
    asOf: string | null;
    spend: Record<string, number | null>;
    flags: Record<string, string>;
  } | null,
  cutoff: string
): SonioxBalanceInputs | undefined {
  if (!soniox) return undefined;
  const days = Object.keys(soniox.spend).sort();
  return {
    ready: soniox.snapshots >= 2,
    firstDay: days[0] ?? soniox.asOf ?? cutoff,
    lastDay: days.at(-1) ?? soniox.asOf ?? cutoff,
    asOf: soniox.asOf,
    spend: soniox.spend,
    flags: soniox.flags,
  };
}

/** True when the live Soniox series exists but no longer covers `day` (the
 * snapshot pull stopped): uncovered days show the dated console constant, the
 * line must say so, and its estimate is stale immediately. */
export function sonioxSeriesBroken(
  vendor: VendorInputs | undefined,
  day: string
): boolean {
  const bal = vendor?.sonioxBalance;
  return !!bal?.ready && day > bal.lastDay;
}

/** Measured vendor inputs by date; every map is optional and absent means the
 * source is unavailable (never a silent zero). */
export interface SonioxBalanceInputs {
  /** ≥2 snapshots exist: the derived day-rate series is live (before that the
   * labelled dated console constant stays, David 2026-10-22). */
  ready: boolean;
  /** first UTC day covered by the derived spend series. */
  firstDay: string;
  /** last UTC day covered by a published spend row. Days after it have NO
   * measured value: they fall back to the dated constant, flagged — a stale
   * snapshot series must never read as $0 spend. */
  lastDay: string;
  /** latest snapshot's UTC day, shown as the as-of date. */
  asOf: string | null;
  /** date → measured daily USD (null = flagged baseline-reset day). */
  spend: Record<string, number | null>;
  /** date → producer flag ('gap_spread' | 'baseline_reset' | 'snapshot_gap'). */
  flags: Record<string, string>;
}
export interface ModulateModelledInputs {
  /** date → modelled USD (measured volume × committed price). */
  byDay: Record<string, { usd: number; priceAsOf?: string }>;
  price: number | null;
  priceAsOf: string | null;
}
export interface VendorInputs {
  /** date → measured STT vendor → USD (`soniox`/`deepgram`/…), kept
   * provider-specific so each provider combines with its own cash. */
  sttMeasured?: Record<string, Record<string, number>>;
  /** Soniox prepaid-balance day-rate series (replaces the usage line). */
  sonioxBalance?: SonioxBalanceInputs;
  /** Modulate modelled volume line (no vendor API exists). */
  modulateModelled?: ModulateModelledInputs;
  /** date → Mercury STT-vendor cash by vendor (soniox / deepgram / modulate). */
  sttCash?: Record<string, Record<string, number>>;
  /** date → complete, fresh Mercury SaaS daily USD. */
  saasMeasured?: Record<string, number>;
  /** date → complete, fresh Mercury non-GCP infra run-rate USD (never GCP,
   * STT or Stripe-fee cash — those are their own lines; the producer keeps
   * the stripe_fees vendor out of it so this never double-counts the fee line). */
  infraMeasured?: Record<string, number>;
  /** date → producer reason while the infra annual history is incomplete;
   * such a run rate is floored at the dated constant (see `allInCost`). */
  infraAnnualPartial?: Record<string, string>;
  /** date → run rate of the Mercury `stripe_fees` cash excluded from
   * `infraMeasured`; rejoins the infra line only on a day the measured fee
   * line is unavailable. */
  infraStripeFeesCash?: Record<string, number>;
  /** date → measured Stripe processing fee USD. */
  stripeFees?: Record<string, number>;
}

/** A date inside the live series with no published row: never a phantom
 * `baseline_reset` (that label is reserved for an actual lower cumulative
 * balance) and never silent $0 spend. */
export const SONIOX_GAP_FLAG = "snapshot_gap";

/** One day's STT line. Soniox: the measured balance-delta day-rate, but only
 * on days the snapshot series actually covers (`firstDay`..`lastDay`) AND the
 * day has a published row; a covered day with no row (snapshot gap) or a reset
 * row falls back to the labelled estimate — the FinOps usage line, else the
 * dated console constant — unmeasured and flagged, and beyond the last covered
 * day the same dated fallback returns. An unknown day is NEVER booked as $0:
 * that would silently drop Soniox spend from the all-in total (Luna r2 P1).
 * Modulate: the modelled volume line when present, otherwise Mercury cash
 * (labelled). Soniox Mercury cash is never added (prepaid recharge, not a
 * rate). Deepgram combines independently: measured usage when the FinOps line
 * has it, its Mercury cash otherwise — never suppressed by a Soniox
 * measurement. */
export function sttLineFor(
  date: string,
  { sttMeasured, sonioxBalance, modulateModelled, sttCash }: VendorInputs
) {
  const cash = sttCash?.[date] || {};
  const vendors = sttMeasured?.[date] || {};
  const bal = sonioxBalance;
  const inSeries = !!bal?.ready && date >= bal.firstDay && date <= bal.lastDay;
  const spend = inSeries ? bal!.spend[date] : undefined;
  const flag = inSeries ? bal!.flags[date] : undefined;
  // Labelled fallback for any day without a published Soniox row: the FinOps
  // usage line when it has one, else the dated console constant.
  const fallbackUsd = vendors.soniox ?? STT_MONTHLY_USD / DAYS_PER_MONTH;
  const soniox = inSeries
    ? {
        usd: spend ?? fallbackUsd,
        measured: spend != null,
        flag:
          spend == null
            ? flag ?? SONIOX_GAP_FLAG
            : flag === "gap_spread"
            ? "gap_spread"
            : null,
      }
    : {
        usd: fallbackUsd,
        measured: vendors.soniox != null,
        flag: null,
      };
  const modelled = modulateModelled?.byDay[date];
  const modulateCash = cash.modulate ?? 0;
  const modulate = modelled
    ? { usd: modelled.usd, modelled: true }
    : { usd: modulateCash, modelled: false };
  // Per-provider: Deepgram's own measured line wins over its cash; a Soniox
  // measurement never hides Deepgram dollars again.
  const deepgramMeasured = vendors.deepgram ?? null;
  const deepgram = deepgramMeasured ?? cash.deepgram ?? 0;
  return {
    usd: soniox.usd + modulate.usd + deepgram,
    measured: soniox.measured || deepgramMeasured != null,
    sonioxMeasured: soniox.measured,
    flag: soniox.flag,
    sonioxUsd: soniox.usd,
    modulateUsd: modulate.usd,
    modulateModelled: modulate.modelled,
    deepgramUsd: deepgram,
    deepgramMeasured: deepgramMeasured != null,
    cash:
      (modulate.modelled ? 0 : modulateCash) +
      (deepgramMeasured != null ? 0 : cash.deepgram ?? 0),
  };
}

/** Modulate monthly reconciliation: modelled volume-line USD vs Mercury cash
 * (vendor map `modulate` → stt_vendor) over the trailing `days` ending at
 * `end` inclusive. Mercury cash is summed over EVERY day of the window,
 * independently of modelled-row coverage — a date with cash but no Prometheus
 * row (batch usage, a missing metric day) must widen the variance, not
 * disappear. Null when the modelled line has no days in the window. */
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
  let observed = 0;
  for (const [day, row] of Object.entries(modelled.byDay)) {
    if (day < start || day > end) continue;
    modelledUsd += row.usd;
    observed++;
  }
  if (!observed) return null;
  let cashUsd = 0;
  for (
    let d = new Date(`${start}T00:00:00Z`);
    d <= new Date(`${end}T00:00:00Z`);
    d = shiftDay(d, 1)
  ) {
    cashUsd += sttCash?.[d.toISOString().slice(0, 10)]?.modulate ?? 0;
  }
  return {
    modelledUsd,
    cashUsd,
    variancePct:
      modelledUsd > 0 ? (100 * (cashUsd - modelledUsd)) / modelledUsd : null,
  };
}

/** One day's non-GCP infra line. The producer's run rate replaces the dated
 * constant outright only once it is a complete measurement. While the
 * producer labels the day partial the run rate is a FLOOR: the cadence
 * treatment amortizes only charges the ledger holds, so an annual bill posted
 * before the ledger starts (the 2026-01-08 Modal wire, ≈$1,000/mo) contributes
 * nothing, and a vendor's first-seen charge is an ambiguous one-off ÷12 — it
 * cannot overcount the complete figure. The dated constant was read from the
 * same ledger plus that known wire, so the day shows max(measured, constant),
 * still labelled partial: never the ≈$114/mo visible slice in place of the
 * $1,114/mo the evidence supports (Luna r2 P1), while a measured run rate
 * that rises above the constant is used at once instead of hidden behind it.
 * Both partial reasons floor — `uncategorized_above_threshold` can hide an
 * unmatched annual infra wire just as a short ledger does. Once the producer
 * calls the annual history complete (≥365 covered days, after the 400-day
 * backfill) the measured value stands alone. Mercury `stripe_fees` cash —
 * kept out of the run rate because the measured fee line owns that money —
 * rejoins here only when that line has no value for the day, so the fees are
 * never on both lines and never on neither (Luna r2 P2). */
export function infraLineFor(
  date: string,
  { infraMeasured, infraAnnualPartial, infraStripeFeesCash }: VendorInputs,
  /** The measured Stripe fee for the day as the stack books it; null = the
   * fee line has no value for the day (source dark or day not loaded). */
  fees: number | null
) {
  const estimate = INFRA_MONTHLY_USD / DAYS_PER_MONTH;
  const measured = infraMeasured?.[date] ?? null;
  const partial = measured == null ? null : infraAnnualPartial?.[date] ?? null;
  const floored = partial != null && (measured as number) < estimate;
  const base = measured == null || floored ? estimate : measured;
  const feesCash = fees == null ? infraStripeFeesCash?.[date] ?? 0 : 0;
  return {
    usd: base + feesCash,
    measured: measured != null,
    measuredUsd: measured,
    partial,
    floored,
    feesCash,
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
      const infra = infraLineFor(d.date, vendor, fees);
      const total =
        gcp +
        vertexLlm +
        (openai ?? 0) +
        anthropicCounted +
        stt.usd +
        saas +
        infra.usd +
        (fees ?? 0);
      return {
        date: d.date,
        gcp,
        vertexLlm,
        vertexReserved: hasComponents ? c.vertexReserved ?? 0 : 0,
        openai,
        anthropic,
        stt: stt.usd,
        sttMeasured: stt.measured,
        sttSonioxMeasured: stt.sonioxMeasured,
        sttFlag: stt.flag,
        sttSonioxUsd: stt.sonioxUsd,
        sttModulateUsd: stt.modulateUsd,
        sttModulateModelled: stt.modulateModelled,
        sttDeepgramUsd: stt.deepgramUsd,
        sttDeepgramMeasured: stt.deepgramMeasured,
        sttCash: stt.cash,
        saas,
        saasMeasured: measuredSaas != null,
        infra: infra.usd,
        infraMeasured: infra.measured,
        infraMeasuredUsd: infra.measuredUsd,
        infraPartial: infra.partial,
        infraFloored: infra.floored,
        infraFeesCash: infra.feesCash,
        fees,
        oneTime: excess,
        total,
      };
    });
  return { daily, oneTime, missing, feesUnavailable };
}

// ----------------------------------------------------------- variable margin

/** Variable margin (David, 2026-10-23; tile approved 2026-10-24):
 * (MRR − real monthly cost) ÷ MRR, goal 50%.
 * Real monthly cost = the trailing-7-day run rate (× 30.44/7) of
 *   GCP net of credits EXCLUDING only the prepaid Vertex reserved-capacity
 *   line — the GCP input is taken BEFORE the all-in wall's one-time-incident
 *   exclusion (`CostDay.gcp`/`vertexLlm` carry it post-exclusion, so the
 *   margin adds `oneTime` back; the Health/all-in wall keeps its own
 *   incident treatment, the margin's sole GCP exclusion is the reserved SKU)
 *   + OpenAI + Soniox + Modulate + Stripe fees — the vendor/non-GCP lines the
 *   FinOps stack already loads, with their existing labelled fallbacks.
 * Out of scope by the same ruling: marketing, hardware, SaaS tooling, non-GCP
 * infra, the Anthropic API leg and Deepgram. The all-in stack keeps counting
 * and labelling all of those; the margin never silently re-adds them. */
export const VARIABLE_MARGIN_TARGET = 0.5;
/** The contract's exact month factor (David 2026-10-23): the run rate scales
 * by 30.44/7, not the calendar 365.25/12 the all-in daily constants use. */
export const MARGIN_DAYS_PER_MONTH = 30.44;
/** Days in the run-rate window (the definition's trailing 7 days). */
export const VARIABLE_MARGIN_RUN_DAYS = 7;
/** Rendered sparkline length in days. */
export const VARIABLE_MARGIN_SERIES_DAYS = 60;
/** Stripe-fee fallback while no measured line exists: the 50%-margin baseline
 * table (2026-10-23), ≈$3.2K/mo. A labelled dated estimate exactly like the
 * STT console constant — replaced per day by the measured fee table, then by
 * the Mercury `stripe_fees` cash run rate, never a silent zero. */
export const STRIPE_FEES_MONTHLY_USD = 3200;
export const STRIPE_FEES_AS_OF = "2026-10-23";
export const STRIPE_FEES_SOURCE = `50%-margin baseline, ${STRIPE_FEES_AS_OF}`;
export const STRIPE_FEES_STALE_DAYS = SAAS_STALE_DAYS;

/** How the day's fee dollars were sourced; the disclosure names the rung. */
export type FeeSource = "measured" | "cash" | "estimate";

export interface VariableCostDay {
  date: string;
  /** The day's cost in the margin's scope. A line with no source contributes
   * 0 here and is named in `missing` — disclosed, never guessed, never $0 by
   * accident. */
  usd: number;
  /** GCP net of credits BEFORE the all-in wall's one-time-incident exclusion
   * (`allInCost` already removed `oneTime` from `gcp`/`vertexLlm`, so it is
   * added back), minus the prepaid Vertex reserved line — the margin's only
   * GCP exclusion. */
  gcp: number;
  /** The excluded prepaid line, kept visible for the tile's tooltip/status. */
  vertexReserved: number;
  /** null = the OpenAI invoice leg is off; counted as 0 and missing. */
  openai: number | null;
  soniox: number;
  /** True when Soniox is the measured balance-delta day-rate (or usage line),
   * false on the dated console constant or a flagged fallback day. */
  sonioxMeasured: boolean;
  /** The day's Soniox producer flag. `gap_spread` survives a non-null spend —
   * those dollars are an even-spread assumption, not a per-day measurement. */
  sonioxFlag: string | null;
  modulate: number;
  /** True when Modulate is the modelled volume line, false on Mercury cash. */
  modulateModelled: boolean;
  fees: number;
  feeSource: FeeSource;
  /** In-scope lines with no source that day (counted as 0, disclosed). */
  missing: string[];
}

/** One day of the margin's cost scope, off an `allInCost` day. The fee
 * fallback chain mirrors the all-in stack's rule (measured fee line first,
 * Mercury fee cash second) plus one more rung the margin needs: the dated
 * baseline estimate, because the definition includes fee dollars and the
 * measured table is still dark. */
export function variableCostDay(
  day: CostDay,
  feesCash: Record<string, number> | undefined = {}
): VariableCostDay {
  const missing: string[] = [];
  const openai = day.openai;
  if (openai == null) missing.push("OpenAI");
  // No modelled row and no cash row means no Modulate source at all (a
  // modelled row may legitimately hold 0; so may a cash row).
  if (!day.sttModulateModelled && !day.sttModulateUsd) missing.push("Modulate");
  const cash = feesCash[day.date];
  const fees = day.fees ?? cash ?? STRIPE_FEES_MONTHLY_USD / DAYS_PER_MONTH;
  const feeSource: FeeSource =
    day.fees != null ? "measured" : cash != null ? "cash" : "estimate";
  // The margin's GCP input is the day's raw billing net, not the wall's: the
  // one-time-incident excess `allInCost` removed goes back in, and only the
  // prepaid Vertex reserved SKU comes out (Luna r3 P1).
  const gcp = day.gcp + day.vertexLlm + day.oneTime - day.vertexReserved;
  return {
    date: day.date,
    usd: gcp + (openai ?? 0) + day.sttSonioxUsd + day.sttModulateUsd + fees,
    gcp,
    vertexReserved: day.vertexReserved,
    openai,
    soniox: day.sttSonioxUsd,
    sonioxMeasured: day.sttSonioxMeasured,
    sonioxFlag: day.sttFlag,
    modulate: day.sttModulateUsd,
    modulateModelled: day.sttModulateModelled,
    fees,
    feeSource,
    missing,
  };
}

export interface VariableMarginPoint {
  /** Window-end day (UTC), also the MRR day. */
  date: string;
  /** Trailing-7-day cost run rate × 30.44/7. Only emitted for a complete,
   * contiguous window — a partial window is no run rate. */
  costPerMonth: number;
  /** That day's FinOps book MRR; null when the day has no book snapshot. */
  mrr: number | null;
  /** (MRR − cost) ÷ MRR × 100; null without MRR. */
  marginPct: number | null;
  /** The cost line where margin equals the target: MRR × (1 − target). */
  goalCost: number | null;
  /** Per-line run rates on the same basis (the tooltip's stack). */
  gcpPerMonth: number;
  /** The prepaid Vertex reserved dollars left OUT of `costPerMonth`. */
  vertexReservedPerMonth: number;
  openaiPerMonth: number;
  sonioxPerMonth: number;
  modulatePerMonth: number;
  feesPerMonth: number;
  /** In-scope lines unsourced on any window day (counted as 0, disclosed). */
  missing: string[];
  /** True only when EVERY window day priced Soniox by a measured row with no
   * producer flag; a mixed window is disclosed through the day counts below
   * and is never labelled plain "measured" (Luna r3 P2). */
  sonioxMeasured: boolean;
  /** Window days Soniox spent on a fallback (console constant, usage line or
   * snapshot gap) instead of a measured row. */
  sonioxEstimateDays: number;
  /** Window days whose Soniox row carries the producer's `gap_spread` flag
   * (an even-spread assumption over a snapshot gap, not a measurement). */
  sonioxGapSpreadDays: number;
  /** How the window-end day priced Modulate/fees — the disclosure describes
   * the latest number, as `marginStatus` does. */
  modulateModelled: boolean;
  feeSource: FeeSource;
}

/** The variable-margin series: one point per day whose trailing 7 cost days
 * are all present and contiguous. MRR comes from `mrrFor` for the window-end
 * day only (that day's book or null — never a neighbour's book). */
export function variableMarginSeries(
  daily: CostDay[],
  mrrFor: (day: string) => number | null,
  options: { feesCash?: Record<string, number>; days?: number } = {}
): VariableMarginPoint[] {
  const run = VARIABLE_MARGIN_RUN_DAYS;
  const scale = MARGIN_DAYS_PER_MONTH / run;
  const costs = [...daily]
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((d) => variableCostDay(d, options.feesCash));
  const points: VariableMarginPoint[] = [];
  for (let i = run - 1; i < costs.length; i++) {
    const end = costs[i].date;
    const window: VariableCostDay[] = [];
    for (let k = 0; k < run; k++) {
      const day = costs[i - k];
      if (
        !day ||
        day.date !==
          shiftDay(new Date(`${end}T00:00:00Z`), -k)
            .toISOString()
            .slice(0, 10)
      ) {
        window.length = 0; // a gap anywhere: no run rate for this day
        break;
      }
      window.push(day);
    }
    if (!window.length) continue;
    const sum = (pick: (c: VariableCostDay) => number) =>
      window.reduce((s, c) => s + pick(c), 0);
    const costPerMonth = sum((c) => c.usd) * scale;
    const mrr = mrrFor(end);
    // Source flags aggregate over the WHOLE window, not the end day: a
    // measured latest day must not hide console-estimate or gap-spread days
    // inside the same run rate (Luna r3 P2).
    const sonioxEstimateDays = window.filter((c) => !c.sonioxMeasured).length;
    const sonioxGapSpreadDays = window.filter(
      (c) => c.sonioxFlag === "gap_spread"
    ).length;
    points.push({
      date: end,
      costPerMonth,
      mrr,
      marginPct:
        mrr != null && mrr > 0 ? (100 * (mrr - costPerMonth)) / mrr : null,
      goalCost:
        mrr != null && mrr > 0 ? mrr * (1 - VARIABLE_MARGIN_TARGET) : null,
      gcpPerMonth: sum((c) => c.gcp) * scale,
      vertexReservedPerMonth: sum((c) => c.vertexReserved) * scale,
      openaiPerMonth: sum((c) => c.openai ?? 0) * scale,
      sonioxPerMonth: sum((c) => c.soniox) * scale,
      modulatePerMonth: sum((c) => c.modulate) * scale,
      feesPerMonth: sum((c) => c.fees) * scale,
      missing: Array.from(new Set(window.flatMap((c) => c.missing))),
      sonioxMeasured: sonioxEstimateDays === 0 && sonioxGapSpreadDays === 0,
      sonioxEstimateDays,
      sonioxGapSpreadDays,
      modulateModelled: costs[i].modulateModelled,
      feeSource: costs[i].feeSource,
    });
  }
  return points.slice(-(options.days ?? VARIABLE_MARGIN_SERIES_DAYS));
}

export interface VariableMarginStatusContext {
  now: Date;
  /** The Soniox balance series, for "n/a since <last covered day>". */
  soniox?: SonioxBalanceInputs;
  /** The fee-scope reason while the measured fee table is unreachable. */
  feesUnavailable?: string | null;
  /** Paying subscriptions excluded from the window-end day's book because
   * their price is not USD — the MRR is a USD-only, partial denominator and
   * the tile says so with the count. Null when the FinOps table predates the
   * count column. */
  nonUsdPaying?: number | null;
}

/** The tile's disclosure lines: the MRR names its source (the FinOps plan
 * book) and its partial-currency caveat, every in-scope cost line names its
 * source, and a missing or stale one names itself (e.g. "Soniox: n/a since
 * 2026-10-10 — console est. in use"), so the margin can never silently
 * undercount. */
export function variableMarginLineStatus(
  point: VariableMarginPoint | undefined,
  ctx: VariableMarginStatusContext
): string[] {
  const money = (v: number | null) =>
    v == null ? "—" : `$${Math.round(v).toLocaleString("en-US")}/mo`;
  const age = (asOf: string) =>
    Math.floor(
      (ctx.now.getTime() - Date.parse(`${asOf}T00:00:00Z`)) / 86_400_000
    );
  if (!point)
    return ["Variable margin: no complete settled 7-day cost window yet"];
  const missing = new Set(point.missing);
  const lines: string[] = [`through ${point.date}`];
  // The MRR line identifies a missing book (the headline then shows no value,
  // never the previous day's margin) and the partial-currency caveat.
  const nonUsdCaveat =
    ctx.nonUsdPaying == null
      ? " — non-USD paying subs excluded (count n/a)"
      : ` — ${ctx.nonUsdPaying} non-USD paying subs excluded`;
  lines.push(
    point.mrr == null
      ? "MRR: n/a (no book snapshot that day)"
      : `MRR: FinOps plan book ${money(point.mrr)}${nonUsdCaveat}`
  );
  lines.push(
    `GCP net ex reserved ${money(point.gcpPerMonth)} (${money(
      point.vertexReservedPerMonth
    )} prepaid Vertex reserved excluded)`
  );
  lines.push(
    missing.has("OpenAI")
      ? "OpenAI: n/a (invoice leg off)"
      : `OpenAI: invoice ${money(point.openaiPerMonth)}`
  );
  const sttStale = age(STT_AS_OF) > STT_STALE_DAYS ? ", STALE" : "";
  const sonioxBroken = !!ctx.soniox?.ready && point.date > ctx.soniox.lastDay;
  // How many of the window's days were NOT a clean measurement, so a mixed
  // window is never labelled plain "measured" (Luna r3 P2).
  const run = VARIABLE_MARGIN_RUN_DAYS;
  const sonioxMix = [
    point.sonioxEstimateDays
      ? `${point.sonioxEstimateDays}/${run} days est.`
      : "",
    point.sonioxGapSpreadDays
      ? `${point.sonioxGapSpreadDays}/${run} days gap-spread`
      : "",
  ]
    .filter(Boolean)
    .join(", ");
  lines.push(
    point.sonioxMeasured
      ? `Soniox: measured ${money(point.sonioxPerMonth)}`
      : sonioxBroken
      ? `Soniox: n/a since ${ctx.soniox!.lastDay} — console est. ${money(
          STT_MONTHLY_USD
        )} (as of ${STT_AS_OF}${sttStale}${sonioxMix ? `; ${sonioxMix}` : ""})`
      : point.sonioxEstimateDays >= run
      ? `Soniox: console est. ${money(
          STT_MONTHLY_USD
        )} (as of ${STT_AS_OF}${sttStale})`
      : `Soniox: ${point.sonioxEstimateDays ? "" : "measured "}${money(
          point.sonioxPerMonth
        )} — ${sonioxMix}`
  );
  lines.push(
    missing.has("Modulate")
      ? "Modulate: n/a (no modelled or Mercury-cash line)"
      : point.modulateModelled
      ? `Modulate: modelled ${money(point.modulatePerMonth)}`
      : `Modulate: Mercury cash ${money(point.modulatePerMonth)}`
  );
  const feesStale =
    age(STRIPE_FEES_AS_OF) > STRIPE_FEES_STALE_DAYS ? ", STALE" : "";
  lines.push(
    point.feeSource === "measured"
      ? `Stripe fees: measured ${money(point.feesPerMonth)}`
      : point.feeSource === "cash"
      ? `Stripe fees: Mercury cash ${money(point.feesPerMonth)}`
      : `Stripe fees: est. ${money(
          STRIPE_FEES_MONTHLY_USD
        )} (${STRIPE_FEES_SOURCE}${feesStale}${
          ctx.feesUnavailable ? "; measured line unavailable" : ""
        })`
  );
  return lines;
}
