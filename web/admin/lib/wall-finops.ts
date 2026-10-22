import { BigQueryDate } from "@google-cloud/bigquery";
import { getGcpBillingClient } from "@/lib/services/gcp-billing";
import { WallSourceError } from "./wall-source-error";

/** Aggregate FinOps tables only; no user-level table is read.
 * plan_revenue_daily repeats rows across producer runs: keep the latest
 * computed_at per snapshot_date/plan and select by snapshot_date (the contract's
 * `date` vs `snapshot_date` offset). Known gaps, disclosed on the board: unmapped
 * enterprise prices are dropped and two JPY subscriptions are booked as yen/100.
 */
export const FINOPS_HISTORY_QUERY = `
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
  try {
    [rows] = await bq.query({
      query: FINOPS_HISTORY_QUERY,
      params: { today: new BigQueryDate(today), days },
      maximumBytesBilled: String(100 * 1024 * 1024),
      jobTimeoutMs: 30_000,
    });
  } catch {
    throw new WallSourceError("FinOps aggregate query failed", true);
  }
  return parseFinopsHistory(rows[0]?.history || "{}");
}

export function parseFinopsHistory(json: string): FinopsHistory {
  const parsed = JSON.parse(json) as {
    mrr?: {
      day: string;
      plan: string;
      mrr_usd: number;
      paying_subs: number;
      refreshed: string;
    }[];
  };
  const history: FinopsHistory = { mrr: {}, paying: {}, refreshed: {} };
  for (const r of parsed.mrr || []) {
    (history.mrr[r.day] ||= {})[r.plan] = Number(r.mrr_usd);
    history.paying[r.day] =
      (history.paying[r.day] || 0) + Number(r.paying_subs);
    const t = Date.parse(r.refreshed);
    history.refreshed[r.day] = Number.isFinite(t)
      ? new Date(t).toISOString()
      : r.refreshed;
  }
  return history;
}

/** FinOps plan cost by day: the latest run's `fully_loaded` and `variable_total`
 * plan rows (USD and cost-active user-days) from `unit_cost_daily`, measured STT
 * vendor lines, complete fresh Mercury SaaS aggregates, and Mercury STT-vendor
 * cash by vendor (Modulate has no usage feed; Soniox/Deepgram cash is a
 * cross-check that must not be stacked on their measured usage). Each source
 * keeps its own latest run so a vendor line never hides plan rows. Incomplete or
 * older-than-3-day Mercury rows are omitted and the TV keeps its dated estimate.
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
  ARRAY(SELECT AS STRUCT FORMAT_DATE('%F', date) AS day, SUM(usd) AS usd
        FROM runs WHERE rk = 1 AND segment_type = 'total' GROUP BY day ORDER BY day) AS stt,
  ARRAY(SELECT AS STRUCT FORMAT_DATE('%F', date) AS day, amount_usd AS usd
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
  /** date → measured STT vendor USD (empty until the FinOps line exists). */
  sttMeasured: Record<string, number>;
  /** date → complete, fresh Mercury SaaS USD; explicit zeroes are retained. */
  saasMeasured: Record<string, number>;
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
    stt?: { day: string; usd: number }[];
    saas?: { day: string; usd: number }[];
    sttCash?: { day: string; vendor: string; usd: number }[];
  };
  const unsettled = new Set(
    (parsed.plans || []).filter((r) => r.settled === false).map((r) => r.day)
  );
  const history: PlanCostHistory = {
    plans: {},
    sttMeasured: {},
    saasMeasured: {},
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
  for (const r of parsed.stt || []) history.sttMeasured[r.day] = Number(r.usd);
  for (const r of parsed.saas || [])
    history.saasMeasured[r.day] = Number(r.usd);
  for (const r of parsed.sttCash || [])
    (history.sttCash[r.day] ||= {})[r.vendor] = Number(r.usd);
  return history;
}

/** Measured Stripe processing fees, read from the FinOps table the producer
 * creates on its first successful balance-transaction pull. Until the finops
 * Stripe key gains read scope for `GET /v1/balance_transactions`, the table
 * does not exist: that is an unavailable line reported on the wall, never an
 * estimate (David 2026-10-22). Kept out of the plan-cost query so a missing
 * table can never fail the plan/STT/SaaS read.
 */
export const FINOPS_STRIPE_FEE_QUERY = `
SELECT FORMAT_DATE('%F', date) AS day, fee_usd
FROM \`based-hardware.omi_finops.stripe_fee_daily\`
WHERE date >= DATE_SUB(@today, INTERVAL @days DAY) AND date <= @today
ORDER BY day`;

export async function fetchStripeFeeHistory(
  today: string,
  days = 40
): Promise<Record<string, number>> {
  const bq = getGcpBillingClient();
  if (!bq) throw new WallSourceError("FinOps BigQuery client unavailable");
  let rows: { day: string; fee_usd: string | number }[];
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
  const fees: Record<string, number> = {};
  for (const r of rows) fees[r.day] = Number(r.fee_usd);
  return fees;
}
