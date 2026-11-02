import type { Metric } from "./wall-metrics";

export const HERO_METRICS = new Set([
  "growth.wau",
  "activation.rate",
  "retention.if_activated",
  "revenue.arpmau",
  "health.crash_free",
]);
export const SMALL_METRICS = new Set([
  "revenue.plan_prepay_usd_week",
  "revenue.payer_churn",
  "cost.gross_margin_pct",
]);
export function cardHeight(id: string): number {
  return SMALL_METRICS.has(id)
    ? 102
    : id === "revenue.arpmau"
    ? 174
    : HERO_METRICS.has(id)
    ? 210
    : 144;
}
export function formatWallValue(value: number | null, unit: string): string {
  if (value == null) return "—";
  if (unit === "percent") return `${value.toFixed(1)}%`;
  if (!unit.startsWith("USD"))
    return value.toLocaleString("en-US", { maximumFractionDigits: 0 });
  const n = Math.abs(value),
    sign = value < 0 ? "−" : "";
  if (n >= 1_000_000)
    return `${sign}$${(n / 1_000_000).toLocaleString("en-US", {
      maximumFractionDigits: n >= 10_000_000 ? 0 : 1,
    })}M`;
  if (n >= 10_000)
    return `${sign}$${Math.round(n / 1_000).toLocaleString("en-US")}K`;
  if (n >= 1_000)
    return `${sign}$${(n / 1_000).toLocaleString("en-US", {
      maximumFractionDigits: 2,
    })}K`;
  if (n > 0 && n < 0.01) return `${sign}<$0.01`;
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: n >= 100 ? 0 : 2,
  });
}
export function shortDate(value: string | null): string | null {
  if (!value || !Number.isFinite(Date.parse(value))) return null;
  return new Date(value).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}
const escape = (s: string) =>
  s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
export interface CardView {
  label: string;
  scope: string;
  display: string;
  deltaText: string;
  deltaColor: string;
  valueColor: string;
  splitValues: string[];
  footnote: string;
  missingReason: string;
  fixture: boolean;
  dimmed: boolean;
  hardwareUnits: number | null;
}
/** A data-only SVG for Grafana's built-in Canvas SVG icon; Grafana sanitizes it.
 * No scripts, stylesheets, links, foreignObject, external images, or user content.
 */
export function wallCardSvg(metric: Metric, view: CardView): string {
  const h = cardHeight(metric.id),
    small = SMALL_METRICS.has(metric.id),
    hero = HERO_METRICS.has(metric.id);
  const accent = view.dimmed ? "#516176" : "#60a5fa",
    muted = "#92a3ba";
  const text = (
    value: string,
    x: number,
    y: number,
    size: number,
    color = muted,
    weight = 400,
    anchor = "start"
  ) =>
    `<text x="${(x / 260) * 100}%" y="${
      (y / h) * 100
    }%" font-size="${size}" fill="${color}" font-weight="${weight}" text-anchor="${anchor}">${escape(
      value
    )}</text>`;
  // Percentage positions fill each column at both widths; text stays at its
  // specified pixel size rather than stretching with the Canvas panel.
  let svg = `<svg xmlns="http://www.w3.org/2000/svg" data-omi-card="${escape(
    metric.id
  )}" width="100%" height="100%" font-family="Inter,system-ui,sans-serif" role="img" aria-label="${escape(
    view.label + " " + view.display
  )}"><rect x="0.5" y="0.5" width="99.6%" height="99.5%" rx="11" fill="#172131" stroke="#304056"/>`;
  if (hero)
    svg += `<rect x="0" y="${
      1700 / h
    }%" width="3" height="30" rx="1.5" fill="${accent}"/>`;
  svg += text(view.label, 14, 23, 12.5, "#d8e1ed", 600);
  const chip = view.scope === "macOS" ? 48 : 32;
  svg += `<svg x="${((246 - chip) / 260) * 100}%" y="${
    1000 / h
  }%" width="${chip}" height="19"><rect width="${chip}" height="19" rx="7" fill="#26374d"/><text x="${
    chip / 2
  }" y="13" font-size="9.5" fill="#b7c7dc" font-weight="500" text-anchor="middle">${escape(
    view.scope
  )}</text></svg>`;
  const valueY = small ? 52 : h >= 200 ? 80 : h >= 170 ? 68 : 58;
  const valueSize = small
    ? 25
    : h >= 200
    ? 49
    : hero
    ? 41
    : ["revenue.mrr", "revenue.hardware_usd_week"].includes(metric.id)
    ? 33
    : 29;
  svg += text(view.display, 14, valueY, valueSize, view.valueColor, 700);
  if (view.hardwareUnits != null)
    svg += text(
      `${view.hardwareUnits.toLocaleString("en-US")} devices`,
      246,
      valueY - 1,
      10.5,
      view.valueColor,
      500,
      "end"
    );
  if (small) {
    svg += text("macOS — · Mobile — · Other —", 14, 70, 9);
    svg += text(
      metric.value == null
        ? view.missingReason.slice(0, 43) +
            (view.missingReason.length > 43 ? "…" : "")
        : view.footnote,
      14,
      89,
      9.2
    );
  } else {
    const deltaY = h >= 200 ? 105 : h >= 170 ? 89 : 77;
    svg += text(
      metric.value == null ? "Awaiting source" : view.deltaText,
      14,
      deltaY,
      10,
      metric.value == null ? muted : view.deltaColor,
      500
    );
    const labelY = h >= 200 ? 126 : h >= 170 ? 107 : 94;
    const labels =
      view.splitValues.length === 4
        ? ["macOS", "Mobile", "Other", "MCP-only"]
        : ["macOS", "Mobile", "Other"];
    const spacing = view.splitValues.length === 4 ? 58 : 80;
    labels.forEach((p, i) => {
      svg += text(p, 14 + i * spacing, labelY, 8.8);
      svg += text(
        view.splitValues[i],
        14 + i * spacing,
        labelY + 14,
        11.2,
        "#c2cedd",
        500
      );
    });
    const top = h >= 200 ? 154 : h >= 170 ? 131 : 114,
      height = h >= 200 ? 24 : h >= 170 ? 14 : 8;
    const points = metric.trend.map((p, i) => ({ index: i, value: p.value }));
    const finite = points.filter(
      (p): p is { index: number; value: number } =>
        p.value != null && Number.isFinite(p.value)
    );
    if (metric.value == null) {
      // Missing-value reasons use the trend area; full detail stays in diagnostics.
      const words = view.missingReason.split(/\s+/);
      const lines: string[] = [""];
      for (const word of words) {
        const i = lines.length - 1;
        if ((lines[i] + " " + word).trim().length > 38) lines.push(word);
        else lines[i] = (lines[i] + " " + word).trim();
      }
      lines.slice(0, 2).forEach((line, i) => {
        svg += text(
          line + (i === 1 && lines.length > 2 ? "…" : ""),
          14,
          h - 23 + i * 12,
          8.6
        );
      });
    } else if (finite.length >= 2) {
      const min = Math.min(...finite.map((p) => p.value)),
        max = Math.max(...finite.map((p) => p.value)),
        span = max - min || 1;
      // A missing bucket breaks the line; it never joins across unavailable periods.
      let path = "",
        last = -2;
      for (const p of finite) {
        const x = (232 * p.index) / Math.max(1, points.length - 1),
          y = height - ((p.value - min) / span) * height;
        path += `${p.index === last + 1 ? "L" : "M"}${x.toFixed(2)} ${y.toFixed(
          2
        )} `;
        last = p.index;
      }
      svg += `<svg x="${(14 / 260) * 100}%" y="${(top / h) * 100}%" width="${
        (232 / 260) * 100
      }%" height="${
        (height / h) * 100
      }%" viewBox="0 0 232 ${height}" preserveAspectRatio="none"><path vector-effect="non-scaling-stroke" d="${path.trim()}" fill="none" stroke="${accent}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
    } else svg += text("Trend not available yet", 14, top + height - 1, 8.8);
    if (metric.value != null) svg += text(view.footnote, 14, h - 8, 8.6);
  }
  if (view.fixture)
    svg += text("FIXTURE", 246, valueY + 18, 8.8, "#9eabc0", 600, "end");
  return svg + "</svg>";
}
