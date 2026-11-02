import { MCP_MARKER_MISSING } from "./wall-mcp";
import { freshness } from "./qualified-activity";
import type { Metric, WallPayload } from "./wall-metrics";
import { formatWallValue, shortDate, wallCardSvg } from "./wall-card-svg";

export const WALL_LABELS: Partial<Record<Metric["id"], string>> = {
  "growth.wau": "Weekly active users",
  "growth.true_new_7d": "New users",
  "activation.rate": "Week-one activation",
  "retention.if_activated": "Retained if activated",
  "engagement.dau": "Daily active users",
  "engagement.mau": "Monthly active users",
  "engagement.assistant_success": "Answered questions",
  "revenue.arpmau": "ARPMAU",
  "revenue.mrr": "Monthly recurring revenue",
  "revenue.hardware_usd_week": "Hardware sales",
  "revenue.plan_prepay_usd_week": "Plan prepay · Shopify",
  "cost.net_day": "All-in cost / day",
  "cost.per_mau_month": "All-in cost / MAU · 30d",
  "cost.gross_margin_pct": "Gross margin · goal 60%",
  "health.crash_free": "Crash-free",
  "health.thumbs_positive": "Positive answers",
  "activation.capture_week1_share": "Saved capture · week one",
  "retention.established_week": "Established retention",
  "retention.day1_return": "Day-one return",
  "revenue.activated_paid_30d": "Activated to paid",
};
export function wallPresentation(payload: WallPayload, now = new Date()) {
  const tiles: Record<string, object> = {},
    series: Record<string, unknown> = {},
    presented: Metric[] = [];
  for (const source of payload.metrics) {
    const m = { ...source };
    const cadence = m.id.startsWith("cost.")
      ? "settled"
      : m.id.startsWith("activation.") ||
        m.id.startsWith("revenue.") ||
        m.id === "health.thumbs_positive" ||
        [
          "retention.if_activated",
          "retention.recovery",
          "retention.day1_return",
        ].includes(m.id)
      ? "daily"
      : "hourly";
    m.stale =
      Boolean(m.retainedSince) ||
      Boolean(payload.cacheStale) ||
      freshness(m.sourceRefreshedAt, m.dataThrough, cadence, now).stale;
    presented.push(m);
    const key = m.id.replaceAll(".", "_"),
      fixture = Boolean(m.fixture || m.reason?.includes("FIXTURE"));
    const dimmed =
      m.stale ||
      m.partial ||
      m.materialGap === true ||
      m.status === "null" ||
      fixture;
    const valueColor = dimmed ? "#8190a6" : "#f4f7fc";
    const delta =
      m.value != null && m.prev != null && m.prev !== 0
        ? (100 * (m.value - m.prev)) / Math.abs(m.prev)
        : null;
    const cohort =
      [
        "activation.rate",
        "activation.capture_week1_share",
        "retention.if_activated",
        "retention.recovery",
        "retention.day1_return",
      ].includes(m.id) && m.windowEnd
        ? new Date(Date.parse(m.windowEnd) - 86_400_000).toISOString()
        : null;
    const cohortDate = shortDate(cohort),
      through = shortDate(m.dataThrough);
    const period = cohort
      ? "cohort"
      : m.id === "retention.established_week" || m.id.includes("week")
      ? "week"
      : m.id === "growth.wau"
      ? "7 days"
      : m.id === "engagement.mau"
      ? "30 days"
      : "period";
    const change =
      m.unit === "percent" && m.value != null && m.prev != null
        ? m.value - m.prev
        : delta;
    const deltaText =
      change == null
        ? "Previous period unavailable"
        : `${change < 0 ? "−" : "+"}${Math.abs(change).toFixed(1)}${
            m.unit === "percent" ? " pp" : "%"
          } · prior ${period}`;
    const signal =
      change == null
        ? 0
        : change *
          ([
            "cost.net_day",
            "cost.per_mau_month",
            "revenue.payer_churn",
          ].includes(m.id)
            ? -1
            : 1);
    const deltaColor = dimmed
      ? "#8190a6"
      : signal > 0
      ? "#60a5fa"
      : signal < 0
      ? "#fb923c"
      : "#92a3ba";
    const mcpActivity = [
      "growth.wau",
      "engagement.dau",
      "engagement.mau",
    ].includes(m.id);
    const splitKeys: (keyof Metric["split"])[] = mcpActivity
      ? ["macos", "mobile", "other", "mcp"]
      : ["macos", "mobile", "other"];
    const splitValues = splitKeys.map((p) =>
      m.split[p] == null
        ? "—"
        : m.unit === "percent"
        ? `${m.split[p]!.toFixed(1)}%`
        : m.split[p]!.toLocaleString("en-US", { maximumFractionDigits: 0 })
    );
    // The route's classified cause, rather than an ID-based generic substitute.
    const missingReason =
      m.reason?.split(";")[0] || "Source refresh receipt missing";
    let footnote = through ? `as of ${through}` : "Refresh time unavailable";
    if (cohortDate)
      footnote += ` · cohort ${cohortDate}${
        m.denominator != null
          ? ` (n=${m.denominator.toLocaleString("en-US")})`
          : ""
      }`;
    if (m.status === "null") footnote = missingReason;
    else if (fixture) footnote = "FIXTURE · sample Stripe data";
    else if (m.stale)
      footnote = `Refresh overdue · ${
        through ? `as of ${through}` : "time unavailable"
      }`;
    else if (m.partial || m.materialGap)
      footnote = `Coverage incomplete · ${
        through ? `as of ${through}` : "refresh pending"
      }`;
    if (
      m.id === "revenue.arpmau" &&
      m.value != null &&
      m.materialGap &&
      !fixture
    )
      footnote = `Live MRR / MAU through ${through || "unknown"}`;
    if (m.id === "growth.true_new_7d" && !m.stale && m.value != null)
      footnote = `180-day lookback · ${
        through ? `as of ${through}` : "refresh pending"
      }`;
    if (
      m.id === "revenue.plan_prepay_usd_week" &&
      !fixture &&
      !m.stale &&
      !m.partial &&
      !m.materialGap &&
      m.value != null
    )
      footnote = `Shopify cash · ${
        through ? `as of ${through}` : "refresh pending"
      }`;
    if (mcpActivity && m.value != null && m.split.mcp == null)
      footnote = `${m.mcpReason || MCP_MARKER_MISSING}${
        m.stale ? " · stale" : through ? ` · ${through}` : ""
      }`;
    const hardwareUnits =
      m.id === "revenue.hardware_usd_week"
        ? payload.metrics.find((p) => p.id === "revenue.hardware_units_week")
            ?.value ?? null
        : null;
    const scope = [
      "health.crash_free",
      "health.thumbs_positive",
      "engagement.assistant_success",
    ].includes(m.id)
      ? "macOS"
      : "all";
    const display = formatWallValue(m.value, m.unit),
      label = WALL_LABELS[m.id] || m.label;
    const view = {
      label,
      scope,
      display,
      deltaText,
      deltaColor,
      valueColor,
      splitValues,
      footnote,
      missingReason,
      fixture,
      dimmed,
      hardwareUnits,
    };
    tiles[key] = {
      value: m.value,
      display,
      valueColor,
      delta,
      deltaText,
      deltaColor,
      macos: splitValues[0],
      mobile: splitValues[1],
      other: splitValues[2],
      ...(mcpActivity
        ? { mcp: splitValues[3], mcpReason: m.mcpReason || MCP_MARKER_MISSING }
        : {}),
      state:
        m.status === "null"
          ? "UNAVAILABLE"
          : fixture
          ? "FIXTURE"
          : m.stale
          ? "STALE"
          : m.partial
          ? "PARTIAL"
          : m.status.toUpperCase(),
      splitRow: `macOS ${splitValues[0]} · Mobile ${splitValues[1]} · Other ${
        splitValues[2]
      }${mcpActivity ? ` · MCP-only ${splitValues[3]}` : ""}`,
      footnote,
      reason: m.reason || "—",
      scope,
      cardSvg: wallCardSvg(m, view),
    };
    series[key] = m.trend.map((p) => ({
      date: `${p.date}T00:00:00Z`,
      value: p.value,
    }));
  }
  return { ...payload, metrics: presented, tiles, series };
}
