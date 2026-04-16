import { parseColor } from "../types";
import type { ContentSegment } from "../types";

export const highlightPattern =
  /<highlight(?:\s+color="([^"]*)")?>([\s\S]*?)<\/highlight>/gi;

export function parseHighlight(match: RegExpExecArray): ContentSegment | null {
  const color = parseColor(match[1], "#F9D71C");
  const text = (match[2] ?? "").trim();
  if (!text) return null;
  return { kind: "highlight", data: { text, color } };
}
