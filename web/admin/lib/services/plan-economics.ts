import { getGcpBillingClient } from "@/lib/services/gcp-billing";

// Aggregate tables only: no user identifiers are read by the dashboard.
export const PLAN_ECONOMICS_QUERY = `
WITH cost_window AS (
  SELECT MAX(date) AS last_day
  FROM \`based-hardware.omi_finops.unit_cost_daily\`
  WHERE date BETWEEN DATE_SUB(@today, INTERVAL 32 DAY) AND DATE_SUB(@today, INTERVAL 2 DAY)
    AND segment_type = 'total' AND component = 'fully_loaded'
), cost AS (
  SELECT FORMAT_DATE('%F', date) AS day, segment_type, segment, component,
    usd, users, run_id, inputs_settled
  FROM \`based-hardware.omi_finops.unit_cost_daily\`, cost_window
  WHERE date BETWEEN DATE_SUB(last_day, INTERVAL 6 DAY) AND last_day
    AND segment_type IN ('plan', 'total')
    AND component IN ('variable_total', 'vertex_pt_fixed', 'fully_loaded', 'stt_vendor_low', 'stt_vendor_high')
), revenue AS (
  SELECT FORMAT_DATE('%F', date) AS day, plan, paying_subs, mrr_usd,
    FORMAT_DATE('%F', snapshot_date) AS snapshot_date, run_id
  FROM \`based-hardware.omi_finops.plan_revenue_daily\`, cost_window
  WHERE date = last_day
), reconciliation AS (
  SELECT FORMAT_DATE('%F', date) AS day, pool, delta_pct, run_id, inputs_settled
  FROM \`based-hardware.omi_finops.unit_cost_reconciliation\`, cost_window
  WHERE date BETWEEN DATE_SUB(last_day, INTERVAL 6 DAY) AND last_day
    AND pool != 'llm_openai_ledger_coverage'
)
SELECT TO_JSON_STRING(STRUCT(
  ARRAY(SELECT AS STRUCT * FROM cost) AS costs,
  ARRAY(SELECT AS STRUCT * FROM revenue) AS revenue,
  ARRAY(SELECT AS STRUCT * FROM reconciliation) AS reconciliation
)) AS snapshot`;

const COMPONENTS = [
  "variable_total",
  "vertex_pt_fixed",
  "fully_loaded",
  "stt_vendor_low",
  "stt_vendor_high",
] as const;
const POOLS = [
  "shared_gcp",
  "audio_pipeline_gcp",
  "vertex_paygo",
  "desktop_pools",
  "vertex_pt_fixed",
  "llm_openai",
  "llm_anthropic",
  "stt_vendor_low",
  "gcp_total_export",
  "one_time",
];
const LABELS: Record<string, string> = {
  basic: "Free",
  unlimited: "Omi Unlimited + Neo",
  unlimited_v2: "Omi Unlimited v2",
  plus: "Omi Plus",
  operator: "Operator",
  architect: "Omi Architect",
};
type Component = (typeof COMPONENTS)[number];
export interface CostRow {
  day: string;
  segment_type: "plan" | "total";
  segment: string;
  component: Component;
  usd: number;
  users: number;
  run_id: string;
  inputs_settled: boolean;
}
export interface RevenueRow {
  day: string;
  plan: string;
  paying_subs: number;
  mrr_usd: number;
  snapshot_date: string;
  run_id: string;
}
export interface EconomicsSnapshot {
  costs: CostRow[];
  revenue: RevenueRow[];
  reconciliation: {
    day: string;
    pool: string;
    delta_pct: number;
    run_id: string;
    inputs_settled: boolean;
  }[];
}
const DAY_MS = 86_400_000;
const shift = (day: string, days: number) =>
  new Date(Date.parse(day) + days * DAY_MS).toISOString().slice(0, 10);
const round = (v: number) => Math.round(v * 100) / 100;
const divide = (a: number, b: number) => (b > 0 ? round(a / b) : null);

export interface PlanEconomicsRow {
  plan: string;
  planName: string;
  mrr: number | null;
  subscribers: number | null;
  variableMonthly: number | null;
  fixedMonthly: number | null;
  allocatedMonthly: number | null;
  estimatedSttMonthly: number | null;
  estimatedCostMonthly: number | null;
  estimatedMarginPct: number | null;
  highSttMarginPct: number | null;
  revenuePerSubscriber: number | null;
  costPerSubscriber: number | null;
  contributionPerSubscriber: number | null;
  costPerActiveDay: number | null;
  activeUsersPerDay: number | null;
  unitBasis: string;
  status: string;
}

const LIMITATIONS =
  "7 settled usage days × 30/7: a 30-day cost run rate, not a monthly invoice. " +
  "Cost includes allocated shared overhead and fixed Vertex reservation. STT is a placeholder estimate " +
  "($0.0043/min; high case ×1.8). One-time charges and unconnected SaaS bills are excluded. " +
  "Unlimited and Neo share one cost plan. Subscriber units use active/past-due Stripe subscriptions, " +
  "not distinct people; active-user units use backend cost-active user-days. Plan and revenue are snapshots.";

/** Build one comparable snapshot; never join live MRR to a stale cost book. */
export function buildPlanEconomics(snapshot: EconomicsSnapshot, today: string) {
  const totals = snapshot.costs.filter((r) => r.segment_type === "total");
  const days = Array.from(new Set(totals.map((r) => r.day))).sort();
  const windowEnd = days.at(-1) ?? null;
  const windowStart = windowEnd ? shift(windowEnd, -6) : null;
  const snapshotDates = Array.from(
    new Set(snapshot.revenue.map((r) => r.snapshot_date))
  );
  const revenueAsOf = snapshotDates.length === 1 ? snapshotDates[0] : null;
  const expectedDays = windowEnd
    ? Array.from({ length: 7 }, (_, i) => shift(windowEnd, i - 6))
    : [];
  let problem = !windowEnd
    ? "Cost feed unavailable"
    : windowEnd < shift(today, -3)
    ? `Cost feed stale: latest usage day ${windowEnd}`
    : windowEnd > shift(today, -2)
    ? "Cost feed is not settled"
    : days.join() !== expectedDays.join()
    ? "Cost feed has missing days"
    : "";

  const runs = new Map<string, string>();
  for (const day of expectedDays) {
    const daily = totals.filter((r) => r.day === day);
    const runIds = new Set(daily.map((r) => r.run_id));
    if (runIds.size !== 1 || !daily[0]?.run_id)
      problem ||= "Cost feed contains mixed runs";
    runs.set(day, daily[0]?.run_id ?? "");
    for (const component of COMPONENTS) {
      if (daily.filter((r) => r.component === component).length !== 1)
        problem ||= "Cost feed has incomplete totals";
    }
    const checks = snapshot.reconciliation.filter((r) => r.day === day);
    if (
      POOLS.some(
        (pool) => checks.filter((r) => r.pool === pool).length !== 1
      ) ||
      checks.some(
        (r) =>
          !r.inputs_settled ||
          r.run_id !== runs.get(day) ||
          !Number.isFinite(r.delta_pct) ||
          Math.abs(r.delta_pct) > 0.5
      )
    ) {
      problem ||= "Cost reconciliation is unavailable or failed";
    }
  }
  if (
    snapshot.costs.some(
      (r) =>
        !r.inputs_settled ||
        r.run_id !== runs.get(r.day) ||
        !Number.isFinite(r.usd) ||
        !Number.isInteger(r.users) ||
        r.users < 0
    )
  ) {
    problem ||= "Cost feed contains invalid or unsettled rows";
  }
  const planCosts = snapshot.costs.filter((r) => r.segment_type === "plan");
  const keys = new Set<string>();
  for (const row of planCosts) {
    const key = `${row.day}:${row.segment}:${row.component}`;
    if (keys.has(key)) problem ||= "Cost feed contains duplicate rows";
    keys.add(key);
    const siblings = planCosts.filter(
      (r) => r.day === row.day && r.segment === row.segment
    );
    if (
      siblings.length !== COMPONENTS.length ||
      siblings.some((r) => r.users !== row.users)
    ) {
      problem ||= "Cost feed has incomplete plan components";
    }
  }
  // Missing plans cannot quietly disappear from the displayed bill.
  for (const total of totals) {
    const parts = planCosts.filter(
      (r) => r.day === total.day && r.component === total.component
    );
    const sum = parts.reduce((n, r) => n + r.usd, 0);
    if (Math.abs(sum - total.usd) > 0.01)
      problem ||= "Plan costs do not reconcile to the total";
    if (parts.reduce((n, r) => n + r.users, 0) !== total.users)
      problem ||= "Plan user counts do not reconcile to the total";
  }
  const revenueValid =
    snapshot.revenue.length > 0 &&
    revenueAsOf !== null &&
    revenueAsOf >= shift(today, -3) &&
    revenueAsOf <= today &&
    new Set(snapshot.revenue.map((r) => r.plan)).size ===
      snapshot.revenue.length &&
    snapshot.revenue.every(
      (r) =>
        r.day === windowEnd &&
        r.run_id === runs.get(r.day) &&
        Number.isFinite(r.mrr_usd) &&
        r.mrr_usd >= 0 &&
        Number.isInteger(r.paying_subs) &&
        r.paying_subs >= 0
    );
  const plans = Array.from(
    new Set([
      ...planCosts.map((r) => r.segment),
      ...snapshot.revenue.map((r) => r.plan),
    ])
  );
  const rows: PlanEconomicsRow[] = plans
    .map((plan) => {
      const costs = planCosts.filter((r) => r.segment === plan);
      const monthly = (component: Component) =>
        (costs
          .filter((r) => r.component === component)
          .reduce((n, r) => n + r.usd, 0) *
          30) /
        7;
      const hasCost = costs.length > 0 && !problem;
      const userDays = costs
        .filter((r) => r.component === "fully_loaded")
        .reduce((n, r) => n + r.users, 0);
      const revenue =
        revenueValid && !problem
          ? snapshot.revenue.find((r) => r.plan === plan)
          : undefined;
      const free = plan === "basic";
      const mrr = free && !problem ? 0 : revenue?.mrr_usd ?? null;
      const subs = free && !problem ? 0 : revenue?.paying_subs ?? null;
      const cost = monthly("fully_loaded") + monthly("stt_vendor_low");
      const highCost = monthly("fully_loaded") + monthly("stt_vendor_high");
      return {
        plan,
        planName: LABELS[plan] ?? `Unmapped (${plan})`,
        mrr,
        subscribers: subs,
        variableMonthly: hasCost ? round(monthly("variable_total")) : null,
        fixedMonthly: hasCost ? round(monthly("vertex_pt_fixed")) : null,
        allocatedMonthly: hasCost ? round(monthly("fully_loaded")) : null,
        estimatedSttMonthly: hasCost ? round(monthly("stt_vendor_low")) : null,
        estimatedCostMonthly: hasCost ? round(cost) : null,
        estimatedMarginPct:
          hasCost && mrr !== null && mrr > 0
            ? round((100 * (mrr - cost)) / mrr)
            : null,
        highSttMarginPct:
          hasCost && mrr !== null && mrr > 0
            ? round((100 * (mrr - highCost)) / mrr)
            : null,
        revenuePerSubscriber:
          mrr !== null && subs !== null ? divide(mrr, subs) : null,
        costPerSubscriber: hasCost && subs !== null ? divide(cost, subs) : null,
        contributionPerSubscriber:
          hasCost && mrr !== null && subs !== null
            ? divide(mrr - cost, subs)
            : null,
        costPerActiveDay: hasCost ? divide((cost * 7) / 30, userDays) : null,
        activeUsersPerDay: hasCost ? round(userDays / 7) : null,
        unitBasis:
          problem ||
          (free
            ? "Free: no paid subscribers"
            : !revenue
            ? "Revenue/subscriber mapping unavailable"
            : subs === 0
            ? "No paid subscribers in snapshot"
            : "Subscriber units use paid subscriptions"),
        status:
          problem ||
          (!hasCost
            ? "Cost unavailable"
            : !free && !revenue
            ? "Revenue unavailable"
            : "Includes estimated STT"),
      };
    })
    .sort(
      (a, b) => (b.mrr ?? -1) - (a.mrr ?? -1) || a.plan.localeCompare(b.plan)
    );
  const status =
    problem ||
    (!revenueValid
      ? "Revenue snapshot unavailable or stale"
      : rows.some((r) => r.status.endsWith("unavailable"))
      ? "Partial plan coverage — includes estimated STT"
      : "Current — includes estimated STT");
  return {
    rows,
    partial:
      Boolean(problem) ||
      !revenueValid ||
      rows.some((r) => r.status.endsWith("unavailable")),
    status: [
      {
        status,
        window: windowStart
          ? `${windowStart} to ${windowEnd} (UTC)`
          : "Unavailable",
        revenueAsOf: revenueAsOf ?? "Unavailable",
        basis:
          "Allocated billed costs + estimated STT. Excludes one-time charges and unconnected SaaS.",
        methodology: LIMITATIONS,
      },
    ],
  };
}

// Short in-process cache coalesces the three panels. No durable stale fallback.
let cached:
  | { at: number; today: string; snapshot: EconomicsSnapshot }
  | undefined;
let pending: { today: string; value: Promise<EconomicsSnapshot> } | undefined;
export async function fetchPlanEconomics(now = new Date()) {
  const today = now.toISOString().slice(0, 10);
  if (
    cached &&
    cached.today === today &&
    now.getTime() - cached.at < 30 * 60_000
  ) {
    return buildPlanEconomics(cached.snapshot, today);
  }
  if (!pending || pending.today !== today) {
    const bq = getGcpBillingClient();
    if (!bq) throw new Error("Plan economics billing client unavailable");
    const value = bq
      .query({
        query: PLAN_ECONOMICS_QUERY,
        params: { today },
        types: { today: "DATE" },
        location: "US",
        maximumBytesBilled: "100000000",
      })
      .then(([rows]) => {
        if (!rows[0]?.snapshot)
          throw new Error("Plan economics query returned no snapshot");
        return JSON.parse(rows[0].snapshot) as EconomicsSnapshot;
      });
    pending = { today, value };
  }
  const current = pending;
  try {
    const snapshot = await current.value;
    const result = buildPlanEconomics(snapshot, today);
    cached = { at: now.getTime(), today, snapshot };
    return result;
  } finally {
    if (pending === current) pending = undefined;
  }
}
