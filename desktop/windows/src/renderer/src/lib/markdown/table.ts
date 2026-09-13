/**
 * GFM tables.
 *
 * A table is the gap that motivated this whole change: measured against the
 * shipped renderer, a four-line GFM table came out as a single paragraph of
 * literal pipe characters. The model emits tables often, because it is the
 * natural shape for the comparisons a user asks for, and every one of them
 * arrived as unreadable text.
 *
 * The rules are ported from `OmiMarkdownTable.parse` in macOS'
 * `OmiMarkdown.swift`, including the two that are easy to get wrong: cells are
 * split on pipes that are neither escaped nor inside an inline code span, and
 * a row is only a row if the separator line parses as alignments for exactly
 * the header's columns.
 */

export type ColumnAlignment = 'left' | 'center' | 'right'

export type MarkdownTable = {
  header: string[]
  alignments: ColumnAlignment[]
  rows: string[][]
}

/**
 * Split one table line into cells.
 *
 * Two rules make this more than `line.split('|')`, and both come from macOS:
 *
 *  - `\|` is a literal pipe, not a cell boundary. Without it a cell can never
 *    contain a pipe, which matters as soon as the model tabulates anything
 *    involving shell syntax or alternation.
 *  - A pipe inside backticks is not a boundary either, so a cell holding
 *    `` `a | b` `` stays one cell.
 */
export function splitCells(line: string): string[] {
  let body = line.trim()
  if (body.startsWith('|')) body = body.slice(1)
  // A trailing pipe closes the row, unless it is escaped, in which case it is
  // content belonging to the last cell.
  if (body.endsWith('|') && !body.endsWith('\\|')) body = body.slice(0, -1)

  const cells: string[] = []
  let current = ''
  let inCode = false
  let i = 0
  while (i < body.length) {
    const ch = body[i]
    if (ch === '\\' && body[i + 1] === '|') {
      current += '|'
      i += 2
      continue
    }
    if (ch === '`') {
      inCode = !inCode
      current += ch
      i += 1
      continue
    }
    if (ch === '|' && !inCode) {
      cells.push(current.trim())
      current = ''
      i += 1
      continue
    }
    current += ch
    i += 1
  }
  cells.push(current.trim())
  return cells
}

/**
 * Read one separator cell as a column alignment, or null if it is not one.
 *
 * `---` left, `:---` left, `:---:` center, `---:` right. Three dashes minimum,
 * matching macOS and GFM; a two-dash cell is not a separator, which is what
 * stops an ordinary `| -- |` row from turning the paragraph above it into a
 * table header.
 */
export function parseAlignment(cell: string): ColumnAlignment | null {
  let marker = cell.trim()
  const leading = marker.startsWith(':')
  const trailing = marker.endsWith(':')
  if (leading) marker = marker.slice(1)
  if (trailing && marker.length > 0) marker = marker.slice(0, -1)
  if (marker.length < 3) return null
  for (const ch of marker) if (ch !== '-') return null
  if (leading && trailing) return 'center'
  if (trailing) return 'right'
  return 'left'
}

/** Pad or truncate a row to the header's column count, as macOS does. */
function normalize(cells: string[], columns: number): string[] {
  if (cells.length === columns) return cells
  if (cells.length > columns) return cells.slice(0, columns)
  return [...cells, ...Array<string>(columns - cells.length).fill('')]
}

/**
 * Try to read a table starting at `start`.
 *
 * Returns null unless the line and the one after it really are a header and a
 * separator, so an ordinary paragraph containing a pipe is never mistaken for
 * one. Body rows stop at the first blank line or any line with fewer than two
 * cells, which is what lets a table be followed immediately by prose.
 */
export function parseTable(
  lines: string[],
  start: number
): { table: MarkdownTable; nextIndex: number } | null {
  if (start + 1 >= lines.length) return null

  const header = splitCells(lines[start])
  const separator = splitCells(lines[start + 1])
  if (header.length < 2 || header.length !== separator.length) return null

  const alignments: ColumnAlignment[] = []
  for (const cell of separator) {
    const alignment = parseAlignment(cell)
    if (!alignment) return null
    alignments.push(alignment)
  }

  const rows: string[][] = []
  let cursor = start + 2
  while (cursor < lines.length) {
    // Subsumed by the cell-count rule below, since a blank line splits into a
    // single empty cell: a mutation audit confirmed removing this changes no
    // output. It stays because it states the rule a reader is looking for
    // ("a table ends at a blank line"), which the cell count only implies, and
    // because macOS carries the same pair.
    if (lines[cursor].trim() === '') break
    const cells = splitCells(lines[cursor])
    if (cells.length < 2) break
    rows.push(normalize(cells, header.length))
    cursor += 1
  }

  return { table: { header, alignments, rows }, nextIndex: cursor }
}
