import { parseAttributes } from "./attributes";
import type { AccordionItem, ContentSegment } from "../types";

export const accordionPattern = /<accordion([^>]*)>([\s\S]*?)<\/accordion>/gi;
const sectionPattern = /<section\s+([^>]*)>([\s\S]*?)<\/section>/gi;

export function parseAccordion(match: RegExpExecArray): ContentSegment | null {
  const attrs = parseAttributes(match[1] ?? "");
  const inner = match[2] ?? "";
  const items: AccordionItem[] = [];
  let m: RegExpExecArray | null;
  sectionPattern.lastIndex = 0;
  while ((m = sectionPattern.exec(inner)) !== null) {
    const sa = parseAttributes(m[1] ?? "");
    const title = (sa.title ?? "").trim();
    const content = (m[2] ?? "").trim();
    if (!title && !content) continue;
    items.push({ title: title || "Untitled", content });
  }
  if (items.length === 0) return null;
  // Flutter accepts both allow-multiple and multiple; parseAttributes lowercases the key already as-is.
  const multi = attrs["allow-multiple"] ?? attrs.multiple;
  return {
    kind: "accordion",
    data: {
      title: attrs.title,
      items,
      allowMultiple: (multi ?? "").toLowerCase() === "true",
    },
  };
}
