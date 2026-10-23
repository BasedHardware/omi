import { BigQueryDate } from "@google-cloud/bigquery";
import { getGcpBillingClient } from "@/lib/services/gcp-billing";
import { WallSourceError } from "./wall-source-error";

/** Aggregate FinOps tables only; no user-level table is read.
 * plan_revenue_daily repeats rows across producer runs: keep the latest
 * computed_at per snapshot_date/plan and select by snapshot_date (the contract's
 * `date` vs `snapshot_date` offset). Known gaps, disclosed on the board: unmapped
 * enterprise prices are dropped; non-USD payers are counted but their MRR is
 * excluded (no implicit FX, `non_usd_paying_subs` marks the figure partial).
 */
export const FINOPS_HISTORY_QUERY = `
WITH revenue AS (
  SELECT FORMAT_DATE('%F', snapshot_date) AS day, plan, mrr_usd, paying_subs,
    MAX(computed_at) OVER (PARTITION BY snapshot_date) AS refreshed,
    MAX(paying_customers) OVER (PARTITION BY snapshot_date) AS paying_customers,
    MAX(non_usd_paying_subs) OVER (PARTITION BY snapshot_date) AS non_usd_paying_subs,
    ROW_NUMBER() OVER (PARTITION BY snapshot_date, plan ORDER BY computed_at DESC) AS rn
  FROM \`based-hardware.omi_finops.plan_revenue_daily\`
  WHERE snapshot_date >= DATE_SUB(@today, INTERVAL @days DAY) AND snapshot_date <= @today
)
SELECT TO_JSON_STRING(STRUCT(
  ARRAY(SELECT AS STRUCT day, plan, mrr_usd, paying_subs, paying_customers, non_usd_paying_subs, refreshed
        FROM revenue WHERE rn = 1 ORDER BY day) AS mrr
)) AS history`;

/** Same read before the `paying_customers`/`non_usd_paying_subs` columns existed
 * (the daily job adds them on its next run); the wall then falls back to the
 * per-plan item sums and labels the denominator item-based. */
const FINOPS_HISTORY_QUERY_LEGACY = `
WITH revenue AS (
  SELECT FORMAT_DATE('%F', snapshot_date) AS day, plan, mrr_usd, paying_subs,
    MAX(computed_at) OVER (PARTITION BY snapshot_date) AS refreshed,
    ROW_NUMBER() OVER (PARTITION BY snapshot_date, plan ORDER BY computed_at DESC) AS rn
  FROM \`based-hardware.omi_finops.plan_revenue_daily\`
  WHERE snapshot_date >= DATE_SUB(@today, INTERVAL @days DAY) AND snapshot_date <= @today
)
SELECT TO_JSON_STRING(STRUCT(
  ARRAY(SELECT AS STRUCT day, plan, mrr_usd, paying_subs, refreshed
        FROM revenue WHERE rn = 1 ORDER BY day) AS mrr
)) AS history`;

export interface FinopsHistory {
  /** snapshot_date → plan → monthly USD. */
  mrr: Record<string, Record<string, number>>;
  /** snapshot_date → total paying subscriptions (trialing excluded). */
  paying: Record<string, number>;
  /** snapshot_date → distinct paying customers (repeated book-wide count).
   * Empty when the table predates the column; the wall falls back to `paying`. */
  payingCustomers: Record<string, number>;
  /** snapshot_date → paying customers whose price is not USD (MRR partial). */
  nonUsdPaying: Record<string, number>;
  /** snapshot_date → producer computed_at, the book's own as-of watermark. */
  refreshed: Record<string, string>;
}

export async function fetchFinopsHistory(
  today: string,
  days = 200
): Promise<FinopsHistory> {
  const bq = getGcpBillingClient();
  if (!bq) throw new WallSourceError("FinOps BigQuery client unavailable");
  let rows: { history: string }[];
  let history: FinopsHistory;
  try {
    [rows] = await bq.query({
      query: FINOPS_HISTORY_QUERY,
      params: { today: new BigQueryDate(today), days },
      maximumBytesBilled: String(100 * 1024 * 1024),
      jobTimeoutMs: 30_000,
    });
    history = parseFinopsHistory(rows[0]?.history || "{}");
  } catch {
    try {
      [rows] = await bq.query({
        query: FINOPS_HISTORY_QUERY_LEGACY,
        params: { today: new BigQueryDate(today), days },
        maximumBytesBilled: String(100 * 1024 * 1024),
        jobTimeoutMs: 30_000,
      });
      history = parseFinopsHistory(rows[0]?.history || "{}");
    } catch {
      throw new WallSourceError("FinOps aggregate query failed", true);
    }
  }
  return history;
}

export function parseFinopsHistory(json: string): FinopsHistory {
  const parsed = JSON.parse(json) as {
    mrr?: {
      day: string;
      plan: string;
      mrr_usd: number;
      paying_subs: number;
      paying_customers?: number | null;
      non_usd_paying_subs?: number | null;
      refreshed: string;
    }[];
  };
  const history: FinopsHistory = {
    mrr: {},
    paying: {},
    payingCustomers: {},
    nonUsdPaying: {},
    refreshed: {},
  };
  for (const r of parsed.mrr || []) {
    (history.mrr[r.day] ||= {})[r.plan] = Number(r.mrr_usd);
    history.paying[r.day] =
      (history.paying[r.day] || 0) + Number(r.paying_subs);
    // Book-wide counts repeat on every plan row: take, do not sum.
    if (r.paying_customers != null)
      history.payingCustomers[r.day] = Number(r.paying_customers);
    if (r.non_usd_paying_subs != null)
      history.nonUsdPaying[r.day] = Number(r.non_usd_paying_subs);
    const t = Date.parse(r.refreshed);
    history.refreshed[r.day] = Number.isFinite(t)
      ? new Date(t).toISOString()
      : r.refreshed;
  }
  return history;
}

/** FinOps plan cost by day: the latest run's `fully_loaded` and `variable_total`
 * plan rows (USD and cost-active user-days) from `unit_cost_daily`, per-vendor
 * measured STT lines (provider-specific, never collapsed: Soniox and Deepgram
 * stay separate so each provider combines with its own cash), Mercury SaaS
 * aggregates (complete inputs; an annual-history gap keeps the amortized value
 * but labels the day partial with the producer's reason — until the ledger
 * covers 12 months the run rate cannot be called complete), and Mercury
 * STT-vendor cash by vendor (Modulate has no usage feed; Soniox/Deepgram cash
 * is a cross-check that must not be stacked on their measured usage). Each
 * source keeps its own latest run so a vendor line never hides plan rows.
 * Incomplete or older-than-3-day Mercury rows are omitted and the TV keeps its
 * dated estimate.
 */
export const FINOPS_PLAN_COST_QUERY = `
WITH runs AS (
  SELECT date, segment_type, segment, component, usd, users, inputs_settled,
    DENSE_RANK() OVER (PARTITION BY date, segment_type ORDER BY computed_at DESC, run_id DESC) AS rk
  FROM \`based-hardware.omi_finops.unit_cost_daily\`
  WHERE date >= DATE_SUB(@today, INTERVAL @days DAY) AND date <= @today
    AND ((segment_type = 'plan' AND component IN ('fully_loaded', 'variable_total'))
      OR (segment_type = 'total' AND REGEXP_CONTAINS(component, r'^stt_[a-z]+_measured$')))
), mercury AS (
  SELECT date, amount_usd,
    annual_history_complete AS annual_complete,
    annual_history_reason AS annual_reason,
    ROW_NUMBER() OVER (PARTITION BY date ORDER BY computed_at DESC, run_id DESC) AS rk
  FROM \`based-hardware.omi_finops.mercury_saas_daily\`
  WHERE date >= DATE_SUB(@today, INTERVAL @days DAY) AND date <= @today
    AND inputs_complete = TRUE
    AND computed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 DAY)
), mercury_stt AS (
  SELECT date, vendor, amount_usd,
    ROW_NUMBER() OVER (PARTITION BY date, vendor ORDER BY computed_at DESC, run_id DESC) AS rk
  FROM \`based-hardware.omi_finops.mercury_vendor_spend_daily\`
  WHERE date >= DATE_SUB(@today, INTERVAL @days DAY) AND date <= @today
    AND category = 'stt_vendor'
)
SELECT TO_JSON_STRING(STRUCT(
  ARRAY(SELECT AS STRUCT FORMAT_DATE('%F', date) AS day, segment AS plan,
          SUM(IF(component = 'fully_loaded', usd, NULL)) AS usd,
          SUM(IF(component = 'fully_loaded', users, NULL)) AS users,
          SUM(IF(component = 'variable_total', usd, NULL)) AS varUsd,
          SUM(IF(component = 'variable_total', users, NULL)) AS varUsers,
          ANY_VALUE(inputs_settled) AS settled
        FROM runs WHERE rk = 1 AND segment_type = 'plan' GROUP BY day, plan ORDER BY day, plan) AS plans,
  ARRAY(SELECT AS STRUCT FORMAT_DATE('%F', date) AS day, component, SUM(usd) AS usd
        FROM runs WHERE rk = 1 AND segment_type = 'total' GROUP BY day, component ORDER BY day, component) AS stt,
  ARRAY(SELECT AS STRUCT FORMAT_DATE('%F', date) AS day, amount_usd AS usd, IFNULL(annual_complete, FALSE) AS annual_complete, IFNULL(annual_reason, '') AS annual_reason
        FROM mercury WHERE rk = 1 ORDER BY day) AS saas,
  ARRAY(SELECT AS STRUCT FORMAT_DATE('%F', date) AS day, vendor,
          amount_usd AS usd
        FROM mercury_stt WHERE rk = 1 ORDER BY day, vendor) AS sttCash
)) AS history`;

export interface PlanCostHistory {
  /** date → FinOps plan segment → fully-loaded and variable USD with
   * cost-active user-days. Only days whose inputs are settled; an unsettled
   * day is absent. */
  plans: Record<
    string,
    Record<
      string,
      { usd: number; users: number; varUsd: number; varUsers: number }
    >
  >;
  /** date → measured STT vendor → USD (`stt_<vendor>_measured`), kept
   * provider-specific (soniox / deepgram / …) so vendors never collapse. */
  sttMeasured: Record<string, Record<string, number>>;
  /** date → complete, fresh Mercury SaaS USD; explicit zeroes are retained.
   * A day whose annual history is incomplete keeps its amortized value here and
   * is listed in `saasAnnualPartial` with the producer's reason — the run rate
   * stays measured but is labelled partial, never complete, until the ledger
   * covers 12 months. */
  saasMeasured: Record<string, number>;
  /** Mercury SaaS days labelled partial: day → producer reason
   * (`history_under_12_months` or `uncategorized_above_threshold`). */
  saasAnnualPartial: Record<string, string>;
  /** date → Mercury STT-vendor cash by vendor (soniox/deepgram/modulate). */
  sttCash: Record<string, Record<string, number>>;
}

export async function fetchPlanCostHistory(
  today: string,
  days = 40
): Promise<PlanCostHistory> {
  const bq = getGcpBillingClient();
  if (!bq) throw new WallSourceError("FinOps BigQuery client unavailable");
  let rows: { history: string }[];
  try {
    [rows] = await bq.query({
      query: FINOPS_PLAN_COST_QUERY,
      params: { today: new BigQueryDate(today), days },
      maximumBytesBilled: String(100 * 1024 * 1024),
      jobTimeoutMs: 30_000,
    });
  } catch {
    throw new WallSourceError("FinOps plan cost query failed", true);
  }
  return parsePlanCost(rows[0]?.history || "{}");
}

export function parsePlanCost(json: string): PlanCostHistory {
  const parsed = JSON.parse(json) as {
    plans?: {
      day: string;
      plan: string;
      usd: number;
      users: number;
      varUsd: number | null;
      varUsers: number | null;
      settled: boolean | null;
    }[];
    stt?: { day: string; component: string; usd: number }[];
    saas?: {
      day: string;
      usd: number;
      annual_complete?: boolean | null;
      annual_reason?: string | null;
    }[];
    sttCash?: { day: string; vendor: string; usd: number }[];
  };
  const unsettled = new Set(
    (parsed.plans || []).filter((r) => r.settled === false).map((r) => r.day)
  );
  const history: PlanCostHistory = {
    plans: {},
    sttMeasured: {},
    saasMeasured: {},
    saasAnnualPartial: {},
    sttCash: {},
  };
  for (const r of parsed.plans || []) {
    if (unsettled.has(r.day)) continue;
    history.plans[r.day] ||= {};
    history.plans[r.day][r.plan] = {
      usd: Number(r.usd),
      users: Number(r.users),
      varUsd: Number(r.varUsd ?? 0),
      varUsers: Number(r.varUsers ?? 0),
    };
  }
  // `stt_soniox_measured` -> soniox: the vendor key of the per-provider line.
  for (const r of parsed.stt || []) {
    const vendor = r.component.replace(/^stt_/, "").replace(/_measured$/, "");
    (history.sttMeasured[r.day] ||= {})[vendor] =
      (history.sttMeasured[r.day]?.[vendor] || 0) + Number(r.usd);
  }
  for (const r of parsed.saas || []) {
    // inputs_complete already gated the query; an annual-history gap keeps the
    // amortized value (measured, best run rate) and labels the day partial.
    history.saasMeasured[r.day] = Number(r.usd);
    if (r.annual_complete === false) {
      history.saasAnnualPartial[r.day] =
        r.annual_reason || "history_under_12_months";
    }
  }
  for (const r of parsed.sttCash || [])
    (history.sttCash[r.day] ||= {})[r.vendor] = Number(r.usd);
  return history;
}

/** Cost frames the health wall renders (`healthFrames` slices its daily
 * backbone to this many days). */
export const HEALTH_COST_DAYS = 60;

/** The health frames end at the D−2 cutoff, so their oldest rendered day is
 * today−61. Both the fee and the infra history reads below default to a
 * window covering every rendered day plus one spare: a Mercury stripe_fees
 * cash day outside the infra read is silently dropped from the wall when the
 * measured fee line is dark (Luna r2 P2), and a fee day outside the fee read
 * would hand its day to that cash fallback for no reason. */
const HEALTH_HISTORY_DAYS = HEALTH_COST_DAYS + 2;

/** Measured Stripe processing fees, read from the FinOps table the producer
 * creates on its first successful balance-transaction pull. Until the finops
 * Stripe key gains read scope for `GET /v1/balance_transactions`, the table
 * does not exist: that is an unavailable line reported on the wall, never an
 * estimate (David 2026-10-22). Kept out of the plan-cost query so a missing
 * table can never fail the plan/STT/SaaS read.
 * `foreign_transaction_count` is carried alongside: those rows sit in a
 * non-USD balance and carry no conversion data of their own, so their fees are
 * NOT in `fee_usd` — the wall labels the line partial rather than calling the
 * USD figure complete.
 */
export const FINOPS_STRIPE_FEE_QUERY = `
SELECT FORMAT_DATE('%F', date) AS day, fee_usd, foreign_transaction_count
FROM \`based-hardware.omi_finops.stripe_fee_daily\`
WHERE date >= DATE_SUB(@today, INTERVAL @days DAY) AND date <= @today
ORDER BY day`;

export interface StripeFeeHistory {
  /** date → measured net fee USD (USD rows only). */
  fees: Record<string, number>;
  /** date → balance transactions held in a non-USD currency that day. */
  foreign: Record<string, number>;
}

export async function fetchStripeFeeHistory(
  today: string,
  days = HEALTH_HISTORY_DAYS
): Promise<StripeFeeHistory> {
  const bq = getGcpBillingClient();
  if (!bq) throw new WallSourceError("FinOps BigQuery client unavailable");
  let rows: {
    day: string;
    fee_usd: string | number;
    foreign_transaction_count: string | number;
  }[];
  try {
    [rows] = await bq.query({
      query: FINOPS_STRIPE_FEE_QUERY,
      params: { today: new BigQueryDate(today), days },
      maximumBytesBilled: String(10 * 1024 * 1024),
      jobTimeoutMs: 30_000,
    });
  } catch {
    // NUMERIC arrives as a string; both parse. Missing table = unavailable line.
    throw new WallSourceError(
      "Stripe fees unavailable (finops key lacks balance-transaction read scope)"
    );
  }
  const history: StripeFeeHistory = { fees: {}, foreign: {} };
  for (const r of rows) {
    history.fees[r.day] = Number(r.fee_usd);
    history.foreign[r.day] = Number(r.foreign_transaction_count ?? 0);
  }
  return history;
}

/** Mercury non-GCP infra run rate (Modal, AWS, Runpod, …), produced by the
 * daily FinOps job with the same cadence treatment as the SaaS run rate:
 * yearly and one-off charges amortize ÷12 (the one-off ambiguity is labelled
 * `estimated` on the producer via `annual_estimated_usd`). Kept out of the
 * plan-cost query so a dark table — it stays dark until the first load after
 * the table ships — can never fail the plan/STT/SaaS read; it is an
 * unavailable line like the fee table, never a guess.
 * `stripe_fees_usd` is the run rate of the Mercury `stripe_fees` vendor the
 * producer keeps OUT of `amount_usd` (that money is the measured fee line's);
 * the cost stack adds it back to infra only on a day the measured fee line is
 * unavailable, so the cash is never counted twice and never dropped from both.
 * The table is created whole with this column (#23356); a live table that
 * predates it fails this read, which degrades to the labelled dated fallback.
 */
export const FINOPS_INFRA_QUERY = `
WITH infra AS (
  SELECT date, amount_usd,
    IFNULL(stripe_fees_usd, 0) AS stripe_fees_usd,
    annual_history_complete AS annual_complete,
    annual_history_reason AS annual_reason,
    ROW_NUMBER() OVER (PARTITION BY date ORDER BY computed_at DESC, run_id DESC) AS rk
  FROM \`based-hardware.omi_finops.mercury_infra_non_gcp_daily\`
  WHERE date >= DATE_SUB(@today, INTERVAL @days DAY) AND date <= @today
    AND inputs_complete = TRUE
    AND computed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 DAY)
)
SELECT TO_JSON_STRING(STRUCT(
  ARRAY(SELECT AS STRUCT FORMAT_DATE('%F', date) AS day, amount_usd AS usd, stripe_fees_usd,
          IFNULL(annual_complete, FALSE) AS annual_complete, IFNULL(annual_reason, '') AS annual_reason
        FROM infra WHERE rk = 1 ORDER BY day) AS infra
)) AS history`;

export interface InfraHistory {
  /** date → complete, fresh Mercury non-GCP infra run-rate USD; explicit
   * zeroes are retained. A day whose annual history is incomplete keeps its
   * amortized value and lands in `infraAnnualPartial` with the producer's
   * reason — the cost stack then floors it at the dated fallback (a partial
   * run rate cannot see annual bills posted before the ledger starts). */
  infraMeasured: Record<string, number>;
  /** infra run-rate days labelled partial: day → producer reason
   * (`history_under_12_months` or `uncategorized_above_threshold`). */
  infraAnnualPartial: Record<string, string>;
  /** date → run rate of the Mercury `stripe_fees` cash the producer excluded
   * from `infraMeasured`; counted on the infra line only when the measured
   * Stripe fee line is unavailable for that day. */
  infraStripeFeesCash: Record<string, number>;
}

export async function fetchInfraHistory(
  today: string,
  days = HEALTH_HISTORY_DAYS
): Promise<InfraHistory> {
  const bq = getGcpBillingClient();
  if (!bq) throw new WallSourceError("FinOps BigQuery client unavailable");
  let rows: { history: string }[];
  try {
    [rows] = await bq.query({
      query: FINOPS_INFRA_QUERY,
      params: { today: new BigQueryDate(today), days },
      maximumBytesBilled: String(10 * 1024 * 1024),
      jobTimeoutMs: 30_000,
    });
  } catch {
    throw new WallSourceError(
      "Infra (non-GCP) run rate unavailable (mercury_infra_non_gcp_daily dark: table not created yet or the daily job is stale)"
    );
  }
  return parseInfra(rows[0]?.history || "{}");
}

export function parseInfra(json: string): InfraHistory {
  const parsed = JSON.parse(json) as {
    infra?: {
      day: string;
      usd: number;
      stripe_fees_usd?: number | string | null;
      annual_complete?: boolean | null;
      annual_reason?: string | null;
    }[];
  };
  const history: InfraHistory = {
    infraMeasured: {},
    infraAnnualPartial: {},
    infraStripeFeesCash: {},
  };
  for (const r of parsed.infra || []) {
    history.infraMeasured[r.day] = Number(r.usd);
    // NUMERIC arrives as a string; an absent column (older row) is no cash.
    history.infraStripeFeesCash[r.day] = Number(r.stripe_fees_usd ?? 0);
    if (r.annual_complete === false) {
      history.infraAnnualPartial[r.day] =
        r.annual_reason || "history_under_12_months";
    }
  }
  return history;
}

/** Soniox measured day-rate, derived on the producer from prepaid-balance
 * snapshots (`vendor_balance_snapshot` → `vendor_balance_spend_daily`): the
 * organization key has no usage/invoice API, only the balance endpoint, so
 * consecutive-snapshot deltas ARE the daily spend. A `usd` of null is a
 * baseline-reset day (unmeasured, flagged); `gap_spread` days carry an
 * even-spread assumption. Kept out of the plan-cost query so a dark table
 * (org key unmounted before the first snapshot) can never fail the
 * plan/STT/SaaS read — it is an unavailable line, like the fee table.
 */
export const FINOPS_VENDOR_BALANCE_QUERY = `
WITH spend AS (
  SELECT FORMAT_DATE('%F', date) AS day, SUM(usd) AS usd, IFNULL(MAX(flag), '') AS flag
  FROM \`based-hardware.omi_finops.vendor_balance_spend_daily\`
  WHERE vendor = 'soniox' AND date >= DATE_SUB(@today, INTERVAL @days DAY) AND date <= @today
  GROUP BY day
), snaps AS (
  SELECT COUNT(1) AS n, MAX(FORMAT_TIMESTAMP('%FT%TZ', ts)) AS latest,
    FORMAT_DATE('%F', MAX(date)) AS last_day
  FROM \`based-hardware.omi_finops.vendor_balance_snapshot\`
  WHERE vendor = 'soniox'
)
SELECT TO_JSON_STRING(STRUCT(
  ARRAY(SELECT AS STRUCT day, usd, flag FROM spend ORDER BY day) AS spend,
  (SELECT n FROM snaps) AS snapshots,
  (SELECT latest FROM snaps) AS latest_ts,
  (SELECT last_day FROM snaps) AS as_of
)) AS history`;

export interface VendorBalanceHistory {
  /** Total snapshots stored (the producer writes one per successful day). */
  snapshots: number;
  /** Latest snapshot timestamp (producer clock), shown as the as-of date. */
  latestTs: string | null;
  /** UTC day of the latest snapshot. */
  asOf: string | null;
  /** date → measured daily USD; null = flagged baseline-reset day. */
  spend: Record<string, number | null>;
  /** date → producer flag ('' normal, 'gap_spread', 'baseline_reset'). */
  flags: Record<string, string>;
}

export async function fetchVendorBalanceHistory(
  today: string,
  days = 40
): Promise<VendorBalanceHistory> {
  const bq = getGcpBillingClient();
  if (!bq) throw new WallSourceError("FinOps BigQuery client unavailable");
  let rows: { history: string }[];
  try {
    [rows] = await bq.query({
      query: FINOPS_VENDOR_BALANCE_QUERY,
      params: { today: new BigQueryDate(today), days },
      maximumBytesBilled: String(10 * 1024 * 1024),
      jobTimeoutMs: 30_000,
    });
  } catch {
    throw new WallSourceError(
      "Soniox measured STT unavailable (balance line dark: org key unmounted or table not created)"
    );
  }
  return parseVendorBalance(rows[0]?.history || "{}");
}

export function parseVendorBalance(json: string): VendorBalanceHistory {
  const parsed = JSON.parse(json) as {
    spend?: { day: string; usd: number | null; flag: string | null }[];
    snapshots?: number;
    latest_ts?: string | null;
    as_of?: string | null;
  };
  const history: VendorBalanceHistory = {
    snapshots: Number(parsed.snapshots ?? 0),
    latestTs: parsed.latest_ts ?? null,
    asOf: parsed.as_of ?? null,
    spend: {},
    flags: {},
  };
  for (const r of parsed.spend || []) {
    history.spend[r.day] = r.usd == null ? null : Number(r.usd);
    if (r.flag) history.flags[r.day] = r.flag;
  }
  return history;
}

/** Modelled Modulate STT cost: measured Prometheus audio seconds × the
 * committed rate-card price (producer table `stt_modulate_modelled_daily`).
 * Modulate has no usage/balance API, so this line is never measured; the
 * monthly Mercury cash reconciliation (wall side) shows the variance.
 */
export const FINOPS_MODULATE_MODELLED_QUERY = `
SELECT FORMAT_DATE('%F', date) AS day, audio_seconds, usd, price_usd_per_hour,
  FORMAT_DATE('%F', price_as_of) AS price_as_of
FROM \`based-hardware.omi_finops.stt_modulate_modelled_daily\`
WHERE date >= DATE_SUB(@today, INTERVAL @days DAY) AND date <= @today
ORDER BY day`;

export interface ModulateModelledDay {
  usd: number;
  seconds: number;
  pricePerHour: number;
  priceAsOf: string;
}

export async function fetchModulateModelled(
  today: string,
  days = 40
): Promise<{
  byDay: Record<string, ModulateModelledDay>;
  price: number | null;
  priceAsOf: string | null;
}> {
  const bq = getGcpBillingClient();
  if (!bq) throw new WallSourceError("FinOps BigQuery client unavailable");
  let rows: {
    day: string;
    audio_seconds: string | number;
    usd: string | number;
    price_usd_per_hour: string | number;
    price_as_of: string;
  }[];
  try {
    [rows] = await bq.query({
      query: FINOPS_MODULATE_MODELLED_QUERY,
      params: { today: new BigQueryDate(today), days },
      maximumBytesBilled: String(10 * 1024 * 1024),
      jobTimeoutMs: 30_000,
    });
  } catch {
    throw new WallSourceError(
      "Modulate modelled STT unavailable (Prometheus series or committed price missing)"
    );
  }
  const byDay: Record<string, ModulateModelledDay> = {};
  let price: number | null = null;
  let priceAsOf: string | null = null;
  for (const r of rows) {
    byDay[r.day] = {
      usd: Number(r.usd),
      seconds: Number(r.audio_seconds),
      pricePerHour: Number(r.price_usd_per_hour),
      priceAsOf: r.price_as_of,
    };
    price = Number(r.price_usd_per_hour);
    priceAsOf = r.price_as_of;
  }
  return { byDay, price, priceAsOf };
}
