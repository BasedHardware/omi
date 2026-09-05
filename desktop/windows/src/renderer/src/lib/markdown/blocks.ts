/**
 * Block-level markdown: the shape of a reply before any of it is rendered.
 *
 * The scanner order is load-bearing and is macOS' (`OmiMarkdownDocument.init`):
 * fenced code first, then tables, then everything else. Code first is what
 * keeps a `---` or a `| a | b |` inside a code sample literal instead of
 * turning it into a rule or a table.
 *
 * Everything here is a pure function of the source text, so the whole block
 * grammar is testable without a DOM.
 */

import { parseTable, type MarkdownTable } from './table'

export type ListItem = {
  /** The item's own inline source, without its marker. */
  text: string
  /** Nested list, if this item has one. */
  children: ListBlock | null
  /** GFM task state: null when the item is not a task item. */
  checked: boolean | null
}

export type ListBlock = {
  kind: 'list'
  ordered: boolean
  /** The number the first item is labelled with, for `3.`-style lists. */
  start: number
  items: ListItem[]
}

export type Block =
  | { kind: 'paragraph'; text: string }
  | { kind: 'heading'; level: number; text: string }
  | { kind: 'code'; language: string | null; text: string }
  | { kind: 'quote'; blocks: Block[] }
  | { kind: 'table'; table: MarkdownTable }
  | { kind: 'thematicBreak' }
  | ListBlock

const FENCE = /^\s*```/
const HEADING = /^(#{1,6})\s+(.*)$/
const UNORDERED = /^(\s*)([-*+])\s+(.*)$/
const ORDERED = /^(\s*)(\d{1,9})[.)]\s+(.*)$/
const QUOTE = /^\s*>\s?(.*)$/
const TASK = /^\[([ xX])\]\s+(.*)$/

/**
 * A thematic break: at least three of the same marker, whitespace ignored.
 *
 * Ported from macOS' `isThematicBreak`, and deliberately checked after fenced
 * code so `---` inside a code sample stays literal. It also has to be checked
 * before paragraphs: in the renderer this replaces there was no rule at all, so
 * `Before\n---\nAfter` came out as one paragraph with the dashes in the middle
 * of it.
 */
export function isThematicBreak(line: string): boolean {
  const markers = line.replace(/\s/g, '')
  if (markers.length < 3) return false
  const marker = markers[0]
  if (marker !== '-' && marker !== '*' && marker !== '_') return false
  for (const ch of markers) if (ch !== marker) return false
  return true
}

/** Width of a line's leading whitespace, with tabs counted as four columns. */
function indentWidth(prefix: string): number {
  let width = 0
  for (const ch of prefix) width += ch === '\t' ? 4 : 1
  return width
}

type ListLine = { indent: number; ordered: boolean; start: number; text: string }

function readListLine(line: string): ListLine | null {
  const unordered = UNORDERED.exec(line)
  if (unordered) {
    return { indent: indentWidth(unordered[1]), ordered: false, start: 1, text: unordered[3] }
  }
  const ordered = ORDERED.exec(line)
  if (ordered) {
    return {
      indent: indentWidth(ordered[1]),
      ordered: true,
      start: Number(ordered[2]),
      text: ordered[3]
    }
  }
  return null
}

/**
 * Read a list, including nested lists, starting at `start`.
 *
 * Nesting is by indentation relative to the list's own first item, which is
 * what the renderer this replaces threw away: it matched list markers with a
 * leading-whitespace-tolerant regex and then stripped the indentation, so every
 * item of every depth landed in one flat `<ul>` and the structure the model
 * expressed was silently lost.
 */
function readList(lines: string[], start: number): { block: ListBlock; nextIndex: number } {
  const first = readListLine(lines[start])
  if (!first) throw new Error('readList called on a line that is not a list item')

  const items: ListItem[] = []
  let cursor = start

  while (cursor < lines.length) {
    const parsed = readListLine(lines[cursor])
    if (!parsed || parsed.indent < first.indent) break
    // Indent is decided before marker type, and the order matters: a nested
    // numbered list under a bullet is a different type at a DEEPER level, so
    // testing the type first ended the outer list and dropped the nesting.
    if (parsed.indent > first.indent) {
      // Deeper than this list: attach to the item above, or start one if the
      // source opened at a deeper indent than its parent (malformed but real).
      const nested = readList(lines, cursor)
      const owner = items[items.length - 1]
      if (owner) owner.children = nested.block
      else items.push({ text: '', children: nested.block, checked: null })
      cursor = nested.nextIndex
      continue
    }
    // Same level, different marker: a new list. A bullet list directly after a
    // numbered one is not absorbed into it.
    if (parsed.ordered !== first.ordered) break

    const task = TASK.exec(parsed.text)
    items.push({
      text: task ? task[2] : parsed.text,
      children: null,
      checked: task ? task[1].toLowerCase() === 'x' : null
    })
    cursor += 1
  }

  return {
    block: { kind: 'list', ordered: first.ordered, start: first.start, items },
    nextIndex: cursor
  }
}

/**
 * Parse a reply into blocks.
 *
 * Never throws and never drops input: anything the grammar does not recognise
 * falls through as paragraph text, which is what keeps a half-streamed reply
 * readable while its closing markers are still arriving.
 */
export function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n/g, '\n').split('\n')
  const blocks: Block[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    if (FENCE.test(line)) {
      const language = line.trim().slice(3).trim()
      const body: string[] = []
      i += 1
      while (i < lines.length && !FENCE.test(lines[i])) body.push(lines[i++])
      // A fence with no closer keeps the rest of the reply as code. That is the
      // shipped behaviour and it is kept deliberately: while a reply streams,
      // the closing fence has not arrived yet, and showing the code block
      // forming reads better than showing raw markdown that reflows the moment
      // it closes. macOS makes the opposite choice and keeps an unclosed
      // fence as text; the divergence is pinned by a test in blocks.test.ts.
      if (i < lines.length) i += 1
      blocks.push({
        kind: 'code',
        language: language === '' ? null : language,
        text: body.join('\n')
      })
      continue
    }

    const table = parseTable(lines, i)
    if (table) {
      blocks.push({ kind: 'table', table: table.table })
      i = table.nextIndex
      continue
    }

    if (isThematicBreak(line)) {
      blocks.push({ kind: 'thematicBreak' })
      i += 1
      continue
    }

    const heading = HEADING.exec(line)
    if (heading) {
      blocks.push({ kind: 'heading', level: heading[1].length, text: heading[2] })
      i += 1
      continue
    }

    if (QUOTE.test(line)) {
      const quoted: string[] = []
      while (i < lines.length && QUOTE.test(lines[i])) {
        quoted.push(QUOTE.exec(lines[i])![1])
        i += 1
      }
      // Recursive, so a quote can hold a list or a code block, which is how
      // the model formats a quoted example.
      blocks.push({ kind: 'quote', blocks: parseBlocks(quoted.join('\n')) })
      continue
    }

    if (readListLine(line)) {
      const list = readList(lines, i)
      blocks.push(list.block)
      i = list.nextIndex
      continue
    }

    if (line.trim() === '') {
      i += 1
      continue
    }

    // Reaching here means this line starts no other block, so it belongs to a
    // paragraph. Taking it unconditionally before testing the next line
    // guarantees forward progress, which a `while` guarding on the CURRENT line
    // would not: every one of those conditions was already checked above, so
    // the guard could only ever be vacuously true, and a future edit that made
    // it false would spin.
    const paragraph: string[] = []
    do {
      paragraph.push(lines[i])
      i += 1
    } while (i < lines.length && !startsBlock(lines, i))
    blocks.push({ kind: 'paragraph', text: paragraph.join('\n') })
  }

  return blocks
}

/** Whether line `i` begins a block, and so ends the paragraph before it. */
function startsBlock(lines: string[], i: number): boolean {
  const line = lines[i]
  return (
    line.trim() === '' ||
    FENCE.test(line) ||
    HEADING.test(line) ||
    QUOTE.test(line) ||
    isThematicBreak(line) ||
    readListLine(line) !== null ||
    parseTable(lines, i) !== null
  )
}
