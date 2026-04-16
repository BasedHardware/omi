import { parseAttributes } from "./attributes";
import { CHART_PALETTE, parseColor } from "../types";
import type { ChartKind, ChartSegment, ContentSegment } from "../types";

export const chartPattern = /<pie-chart([^>]*)>([\s\S]*?)<\/pie-chart>/gi;
const segmentPattern = /<segment\s+((?:[^>"]*|"[^"]*")+)\s*\/?>/gi;

function parseKind(raw: string | undefined): ChartKind {
  switch ((raw ?? "").toLowerCase()) {
    case "pie":
      return "pie";
    case "donut":
      return "donut";
    default:
      return "bar";
  }
}

export function parseChart(match: RegExpExecArray): ContentSegment | null {
  const attrs = parseAttributes(match[1] ?? "");
  const inner = match[2] ?? "";
  const segments: ChartSegment[] = [];
  let m: RegExpExecArray | null;
  let idx = 0;
  segmentPattern.lastIndex = 0;
  while ((m = segmentPattern.exec(inner)) !== null) {
    const sa = parseAttributes(m[1] ?? "");
    const label = sa.label ?? "";
    const value = Number.parseFloat(sa.value ?? "0");
    if (!label || Number.isNaN(value)) continue;
    const fallback = CHART_PALETTE[idx % CHART_PALETTE.length];
    segments.push({
      label,
      value,
      color: parseColor(sa.color, fallback),
    });
    idx++;
  }
  if (segments.length === 0) return null;
  return {
    kind: "chart",
    data: { title: attrs.title, kind: parseKind(attrs.type), segments },
  };
}
