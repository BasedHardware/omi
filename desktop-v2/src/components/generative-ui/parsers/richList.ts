import { parseAttributes } from "./attributes";
import type { ContentSegment, RichListItem } from "../types";

export const richListPattern = /<rich-list\s*>([\s\S]*?)<\/rich-list>/gi;
const itemPattern = /<item\s+((?:[^>"]*|"[^"]*")+)\s*\/?>/gi;

export function parseRichList(match: RegExpExecArray): ContentSegment | null {
  const inner = match[1] ?? "";
  const items: RichListItem[] = [];
  let m: RegExpExecArray | null;
  itemPattern.lastIndex = 0;
  while ((m = itemPattern.exec(inner)) !== null) {
    const attrs = parseAttributes(m[1] ?? "");
    if (!attrs.title) continue;
    items.push({
      title: attrs.title,
      description: attrs.description,
      thumbnailUrl: attrs.thumb,
      url: attrs.url,
    });
  }
  if (items.length === 0) return null;
  return { kind: "richList", items };
}
