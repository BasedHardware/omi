import { parseAttributes } from "./attributes";
import type { ContentSegment, TableCell, TableRow } from "../types";

// Match the block, then extract attributes from the opening tag separately.
// We use `table-data` as the primary tag to avoid clashing with HTML <table>.
// Both `<table>` and `<table-data>` are supported for parity with Flutter.
export const tablePattern = /<table(?:-data)?(?:\s+[^>]*)?>([\s\S]*?)<\/table(?:-data)?>/gi;
const attrPattern = /<table(?:-data)?\s+([^>]*)>/i;
const rowPattern = /<row>([\s\S]*?)<\/row>/gi;
const cellPattern = /<cell>([\s\S]*?)<\/cell>/gi;

export function parseTable(match: RegExpExecArray): ContentSegment | null {
  const full = match[0];
  const content = match[1] ?? "";
  const am = attrPattern.exec(full);
  const attrs = parseAttributes(am?.[1] ?? "");

  const rows: TableRow[] = [];
  let rm: RegExpExecArray | null;
  rowPattern.lastIndex = 0;
  while ((rm = rowPattern.exec(content)) !== null) {
    const cells: TableCell[] = [];
    let cm: RegExpExecArray | null;
    cellPattern.lastIndex = 0;
    while ((cm = cellPattern.exec(rm[1] ?? "")) !== null) {
      const v = (cm[1] ?? "").trim();
      if (v) cells.push({ content: v });
    }
    if (cells.length > 0) rows.push({ cells });
  }
  if (rows.length === 0) return null;
  return { kind: "table", data: { title: attrs.title, rows } };
}
