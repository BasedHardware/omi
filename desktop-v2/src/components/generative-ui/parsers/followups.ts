import { parseAttributes } from "./attributes";
import type { FollowupItem, FollowupType, FollowupsData } from "../types";

export const followupsPattern = /<followups>([\s\S]*?)<\/followups>/gi;
const itemPattern = /<item\s+([^>]*)>([\s\S]*?)<\/item>/gi;

function toFollowupType(raw: string | undefined): FollowupType {
  if (!raw) return "other";
  const n = raw.toLowerCase().replace(/[\s_-]/g, "");
  switch (n) {
    case "factcheck":
      return "factCheck";
    case "verification":
      return "verification";
    case "question":
      return "question";
    default:
      return "other";
  }
}

export function parseFollowups(match: RegExpExecArray): FollowupsData | null {
  const inner = match[1] ?? "";
  const items: FollowupItem[] = [];
  let m: RegExpExecArray | null;
  itemPattern.lastIndex = 0;
  while ((m = itemPattern.exec(inner)) !== null) {
    const ia = parseAttributes(m[1] ?? "");
    items.push({
      type: toFollowupType(ia.type),
      content: (m[2] ?? "").trim(),
    });
  }
  if (items.length === 0) return null;
  return { items };
}
