import { freshness } from "./qualified-activity";
import type { Metric, WallPayload } from "./wall-metrics";

export function wallPresentation(payload: WallPayload, now = new Date()) {
  const tiles: Record<string, object> = {},
    series: Record<string, unknown> = {};
  const presented: Metric[] = [];
  for (const source of payload.metrics) {
    const m: Metric = { ...source };
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
    m.stale = freshness(m.sourceRefreshedAt, m.dataThrough, cadence, now).stale;
    presented.push(m);
    const key = m.id.replaceAll(".", "_");
    const delta =
      m.value != null && m.prev != null && m.prev !== 0
        ? (100 * (m.value - m.prev)) / Math.abs(m.prev)
        : null;
    const split = (p: "macos" | "mobile" | "other") => {
      const n = m.split[p];
      if (n == null) return "—";
      if (m.unit === "percent") {
        const c = m.splitCounts?.[p];
        return `${n.toFixed(1)}%${
          c ? ` (${c.numerator}/${c.denominator})` : ""
        }`;
      }
      return n.toLocaleString("en-US", { maximumFractionDigits: 1 });
    };
    const state =
      m.status === "null"
        ? "UNAVAILABLE"
        : m.stale
        ? "STALE"
        : m.partial
        ? "PARTIAL"
        : m.reason?.includes("FIXTURE")
        ? "FIXTURE"
        : m.reason?.includes("LOCAL AGGREGATE REPLAY")
        ? "REPLAY"
        : m.status.toUpperCase();
    const missingReason: Partial<Record<Metric["id"], string>> = {
      "health.crash_free": "Crash coverage unverified",
      "health.thumbs_positive": "Vote source unavailable",
      "revenue.payer_churn": "Payer history unavailable",
      "revenue.activated_paid_30d": "Billing identity unavailable",
      "revenue.arpmau": "Same-cutoff MRR unavailable",
      "cost.gross_margin_pct": "Revenue/costs incomplete",
    };
    const shortSplit = (p: "macos" | "mobile" | "other") =>
      split(p).split(" (")[0];
    const cohort =
      [
        "activation.rate",
        "activation.capture_week1_share",
        "retention.if_activated",
        "retention.recovery",
        "retention.day1_return",
      ].includes(m.id) && m.windowEnd
        ? new Date(Date.parse(m.windowEnd) - 86_400_000)
            .toISOString()
            .slice(0, 10)
        : null;
    const display =
      m.value == null
        ? "—"
        : m.unit === "percent"
        ? `${m.value.toFixed(1)}%`
        : m.unit.startsWith("USD")
        ? m.value.toLocaleString("en-US", {
            style: "currency",
            currency: "USD",
            maximumFractionDigits: m.id === "revenue.arpmau" ? 4 : 2,
          })
        : m.value.toLocaleString("en-US", { maximumFractionDigits: 0 });
    const hardwareUnits =
      m.id === "revenue.hardware_usd_week"
        ? payload.metrics.find(
            (metric) => metric.id === "revenue.hardware_units_week"
          )?.value
        : null;
    tiles[key] = {
      value: m.value,
      display,
      valueColor:
        m.stale || m.partial || m.status === "null" ? "#6b7280" : "#f3f4f6",
      delta,
      macos: split("macos"),
      mobile: split("mobile"),
      other: split("other"),
      state,
      splitRow: `macOS ${shortSplit("macos")} · Mobile ${shortSplit(
        "mobile"
      )} · Other ${shortSplit("other")}`,
      footnote:
        m.status === "null"
          ? `N/A · ${missingReason[m.id] || "Source unavailable"}`
          : `${
              hardwareUnits != null
                ? `${hardwareUnits.toLocaleString("en-US")} devices · `
                : ""
            }${state} · ${
              cohort
                ? `cohort ${cohort}`
                : m.dataThrough?.slice(0, 10) || "no watermark"
            }${m.denominator != null ? ` · n=${m.denominator}` : ""}`,
      reason: m.reason || "—",
      scope:
        m.split.macos == null
          ? "All · no platform attribution"
          : "Primary platform",
      // Grey unavailable/stale/partial headline fields are selected separately by the board.
      healthyValue:
        m.stale || m.partial || m.status === "null" ? null : m.value,
      dimValue: m.stale || m.partial || m.status === "null" ? m.value : null,
    };
    series[key] = m.trend.map((p) => ({
      date: `${p.date}T00:00:00Z`,
      value: p.value,
    }));
  }
  return { ...payload, metrics: presented, tiles, series };
}
