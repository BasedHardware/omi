import { parseAttributes } from "./attributes";
import type { TimelineData, TimelineEvent, TimelineLabel } from "../types";

export const timelinePattern = /<timeline([^>]*)>([\s\S]*?)<\/timeline>/gi;
const eventPattern = /<event\s+([^>]*)>([\s\S]*?)<\/event>/gi;

function toLabelType(raw: string): TimelineLabel {
  const n = raw.toLowerCase().replace(/[\s_]/g, "");
  switch (n) {
    case "context":
      return "context";
    case "conflict":
      return "conflict";
    case "claim":
      return "claim";
    case "decision":
      return "decision";
    case "reaction":
      return "reaction";
    case "humanimpact":
      return "humanImpact";
    case "nextsteps":
      return "nextSteps";
    default:
      return "other";
  }
}

export function parseTimeline(match: RegExpExecArray): TimelineData | null {
  const attrs = parseAttributes(match[1] ?? "");
  const inner = match[2] ?? "";
  const events: TimelineEvent[] = [];
  let m: RegExpExecArray | null;
  eventPattern.lastIndex = 0;
  while ((m = eventPattern.exec(inner)) !== null) {
    const ea = parseAttributes(m[1] ?? "");
    const label = ea.label ?? "Event";
    events.push({
      time: ea.time ?? "",
      label,
      labelType: toLabelType(label),
      description: (m[2] ?? "").trim(),
    });
  }
  if (events.length === 0) return null;
  return { title: attrs.title, events };
}
