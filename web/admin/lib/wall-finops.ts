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
  SELECT FORMAT_DATE('%F', snapshot_date) AS day, plan, mrr_usd,
    ROW_NUMBER() OVER (PARTITION BY snapshot_date, plan ORDER BY computed_at DESC) AS rn
  FROM \`based-hardware.omi_finops.plan_revenue_daily\`
  WHERE snapshot_date >= DATE_SUB(@today, INTERVAL @days DAY) AND snapshot_date <= @today
)
SELECT TO_JSON_STRING(STRUCT(
  ARRAY(SELECT AS STRUCT day, plan, mrr_usd FROM revenue WHERE rn = 1 ORDER BY day) AS mrr
)) AS history`;

export interface FinopsHistory {
  /** snapshot_date → plan → monthly USD. */
  mrr: Record<string, Record<string, number>>;
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
  const parsed = JSON.parse(rows[0]?.history || "{}") as {
    mrr?: { day: string; plan: string; mrr_usd: number }[];
  };
  const history: FinopsHistory = { mrr: {} };
  for (const r of parsed.mrr || [])
    (history.mrr[r.day] ||= {})[r.plan] = Number(r.mrr_usd);
  return history;
}
