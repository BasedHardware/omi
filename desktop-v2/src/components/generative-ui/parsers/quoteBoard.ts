import { parseAttributes } from "./attributes";
import type { Quote, QuoteBoardData, QuoteRecordStatus } from "../types";

export const quoteBoardPattern = /<quote-board>([\s\S]*?)<\/quote-board>/gi;
const quotePattern = /<quote\s+([^>]*)>([\s\S]*?)<\/quote>/gi;

function toRecordStatus(raw: string | undefined): QuoteRecordStatus {
  if (!raw) return "unclear";
  const n = raw.toLowerCase().replace(/[\s_]/g, "");
  switch (n) {
    case "ontherecord":
      return "onTheRecord";
    case "background":
      return "background";
    case "offtherecord":
      return "offTheRecord";
    default:
      return "unclear";
  }
}

export function parseQuoteBoard(match: RegExpExecArray): QuoteBoardData | null {
  const inner = match[1] ?? "";
  const quotes: Quote[] = [];
  let m: RegExpExecArray | null;
  quotePattern.lastIndex = 0;
  while ((m = quotePattern.exec(inner)) !== null) {
    const qa = parseAttributes(m[1] ?? "");
    quotes.push({
      speaker: qa.speaker ?? "Unknown",
      time: qa.time ?? "",
      recordStatus: toRecordStatus(qa.record),
      quote: (m[2] ?? "").trim(),
    });
  }
  if (quotes.length === 0) return null;
  return { quotes };
}
