/**
 * Inline markdown: emphasis, code spans, links, and the escapes between them.
 *
 * The renderer this replaces did inline formatting with one alternation regex
 * and `String.split`, which cannot nest by construction. Measured against the
 * shipped build, `**see [docs](https://x.com) now**` rendered as bold text
 * containing the literal characters `[docs](https://x.com)`: the link was
 * destroyed by being bolded. `a \*not italic\* b` rendered the backslashes AND
 * italicised anyway. Both are structural consequences of a flat split, not
 * missing cases, which is why this is a scanner and returns a tree.
 *
 * Parsing is separated from rendering on purpose. Every rule here is decidable
 * from a string, so it is testable without a DOM, and the security rule that
 * matters most (which hrefs may become live links) lives in one function with
 * its own tests rather than inside a component.
 */

/** A parsed inline node. `code` is a leaf: its content is literal. */
export type InlineNode =
  | { kind: 'text'; value: string }
  | { kind: 'code'; value: string }
  | { kind: 'strong'; children: InlineNode[] }
  | { kind: 'em'; children: InlineNode[] }
  | { kind: 'del'; children: InlineNode[] }
  | { kind: 'link'; href: string; children: InlineNode[] }
  /** A link target this app refuses to make clickable; the label still shows. */
  | { kind: 'deadLink'; children: InlineNode[] }

/**
 * Schemes a chat reply may turn into a clickable link.
 *
 * Kept from the renderer this replaces, and the reasoning is worth repeating
 * because it is the whole reason there is an allowlist rather than a blocklist:
 * chat replies can be steered by indirect prompt injection, since the prompt
 * includes OCR of whatever is on the user's screen. A model can therefore be
 * induced to emit a `file://`, a UNC path, or a custom protocol handler.
 * Rendering those as live links enables one-click NTLM-hash leakage and OS
 * protocol-handler abuse. Anything not matched here still renders its label,
 * just not as a link.
 */
const SAFE_HREF = /^(https?:|mailto:)/i

export function isSafeHref(href: string): boolean {
  const trimmed = href.trim()
  if (trimmed === '') return false
  // Control characters and whitespace are stripped by URL parsers before the
  // scheme is read, so `java\tscript:alert(1)` reaches the browser as
  // `javascript:alert(1)` while sailing past a naive prefix test. Refusing any
  // href containing one means the string tested below is the string the
  // browser will act on.
  // eslint-disable-next-line no-control-regex -- rejecting control characters is the point
  if (/[\u0000-\u0020\u007f]/.test(trimmed)) return false
  return SAFE_HREF.test(trimmed)
}

/** Characters a backslash may escape, per CommonMark's punctuation set. */
const ESCAPABLE = new Set('\\`*_{}[]()#+-.!|~>')

/** True when `at` is inside a word, for the intraword-underscore rule. */
function isWordChar(source: string, at: number): boolean {
  if (at < 0 || at >= source.length) return false
  return /[\p{L}\p{N}]/u.test(source[at])
}

/**
 * Find the closing delimiter for a run that opened at `from`.
 *
 * Skips over code spans, so a `**` inside backticks never closes emphasis, and
 * respects backslash escapes. Returns -1 when the run never closes, which is
 * the normal state of a half-streamed reply and must stay literal text.
 */
function findCloser(
  source: string,
  from: number,
  delimiter: string,
  underscoreRule: boolean
): number {
  let i = from
  while (i < source.length) {
    const ch = source[i]
    if (ch === '\\' && i + 1 < source.length && ESCAPABLE.has(source[i + 1])) {
      i += 2
      continue
    }
    if (ch === '`') {
      const run = backtickRun(source, i)
      const end = findCodeClose(source, i + run, run)
      // An unterminated code span is not a code span; keep scanning past the
      // backticks rather than swallowing the rest of the line.
      i = end === -1 ? i + run : end + run
      continue
    }
    if (ch === delimiter[0]) {
      // Match against the whole run, not a prefix of it. A single `*` looking
      // for its closer must step over a `**` rather than close on its first
      // character: `*italic with **bold** inside*` otherwise closed the italic
      // on the opening `**` and produced garbage for the rest of the line.
      const run = charRun(source, i, delimiter[0])
      const closes = delimiter.length === 1 ? run === 1 : run >= 2
      if (!closes) {
        i += run
        continue
      }
      // `_` may not close inside a word, so `snake_case_name` is one word and
      // not an emphasised `case`.
      if (underscoreRule && isWordChar(source, i - 1) && isWordChar(source, i + delimiter.length)) {
        i += run
        continue
      }
      return i
    }
    i += 1
  }
  return -1
}

/** Length of the run of `ch` starting at `at`. */
function charRun(source: string, at: number, ch: string): number {
  let n = 0
  while (at + n < source.length && source[at + n] === ch) n += 1
  return n
}

function backtickRun(source: string, at: number): number {
  return charRun(source, at, '`')
}

/** Index of a closing backtick run of exactly `length`, or -1. */
function findCodeClose(source: string, from: number, length: number): number {
  let i = from
  while (i < source.length) {
    if (source[i] === '`') {
      const run = backtickRun(source, i)
      if (run === length) return i
      i += run
      continue
    }
    i += 1
  }
  return -1
}

/** Bare URLs become links. Trailing sentence punctuation is left outside. */
const AUTOLINK = /^https?:\/\/[^\s<>[\]()]+/i

function trimAutolink(url: string): string {
  let end = url.length
  while (end > 0 && '.,;:!?'.includes(url[end - 1])) end -= 1
  return url.slice(0, end)
}

/**
 * Parse one line (or run) of inline markdown into a tree.
 *
 * `depth` guards against a pathological nesting chain; content past it is
 * emitted as plain text rather than recursed into.
 */
export function parseInline(source: string, depth = 0): InlineNode[] {
  const nodes: InlineNode[] = []
  let text = ''
  let i = 0

  const flush = (): void => {
    if (text !== '') {
      nodes.push({ kind: 'text', value: text })
      text = ''
    }
  }

  while (i < source.length) {
    const ch = source[i]

    // Escapes first, so `\*` is a literal asterisk and not an opener.
    if (ch === '\\' && i + 1 < source.length && ESCAPABLE.has(source[i + 1])) {
      text += source[i + 1]
      i += 2
      continue
    }

    // Code spans outrank everything: their content is literal, which is what
    // makes `` `**not bold**` `` work.
    if (ch === '`') {
      const run = backtickRun(source, i)
      const close = findCodeClose(source, i + run, run)
      if (close !== -1) {
        flush()
        // CommonMark strips one leading and trailing space so `` ` `` can be
        // written as `` `` ` `` ``.
        let value = source.slice(i + run, close)
        if (value.length > 1 && value.startsWith(' ') && value.endsWith(' ')) {
          value = value.slice(1, -1)
        }
        nodes.push({ kind: 'code', value })
        i = close + run
        continue
      }
      text += source.slice(i, i + run)
      i += run
      continue
    }

    if (depth < 6) {
      const emphasis = tryEmphasis(source, i, depth)
      if (emphasis) {
        flush()
        nodes.push(emphasis.node)
        i = emphasis.next
        continue
      }

      // An image becomes its alt text. Nothing here fetches a remote URL, and
      // that is deliberate rather than unimplemented: a reply can be steered by
      // whatever is on the user's screen, so rendering `![](url)` would let an
      // injected address fetch on load — a tracking pixel reporting the user's
      // IP and that the chat was opened, with nothing clicked.
      if (ch === '!' && source[i + 1] === '[') {
        const image = tryLink(source, i + 1, depth)
        if (image && (image.node.kind === 'link' || image.node.kind === 'deadLink')) {
          flush()
          nodes.push(...image.node.children.map(stripLinks))
          i = image.next
          continue
        }
      }

      if (ch === '[') {
        const link = tryLink(source, i, depth)
        if (link) {
          flush()
          nodes.push(link.node)
          i = link.next
          continue
        }
      }
    }

    if ((ch === 'h' || ch === 'H') && (i === 0 || !isWordChar(source, i - 1))) {
      const match = AUTOLINK.exec(source.slice(i))
      if (match) {
        const href = trimAutolink(match[0])
        if (href.length > 0 && isSafeHref(href)) {
          flush()
          nodes.push({ kind: 'link', href, children: [{ kind: 'text', value: href }] })
          i += href.length
          continue
        }
      }
    }

    text += ch
    i += 1
  }

  flush()
  return nodes
}

type Attempt = { node: InlineNode; next: number }

/** `**strong**`, `__strong__`, `*em*`, `_em_`, `~~del~~`. */
function tryEmphasis(source: string, at: number, depth: number): Attempt | null {
  const specs: { delimiter: string; kind: 'strong' | 'em' | 'del'; underscoreRule: boolean }[] = [
    { delimiter: '**', kind: 'strong', underscoreRule: false },
    { delimiter: '__', kind: 'strong', underscoreRule: true },
    { delimiter: '~~', kind: 'del', underscoreRule: false },
    { delimiter: '*', kind: 'em', underscoreRule: false },
    { delimiter: '_', kind: 'em', underscoreRule: true }
  ]
  for (const spec of specs) {
    if (!source.startsWith(spec.delimiter, at)) continue
    // `_` may not open inside a word either: `a_b_c` is one word.
    if (spec.underscoreRule && isWordChar(source, at - 1)) continue
    const from = at + spec.delimiter.length
    // An empty run (`****`) is not emphasis.
    if (source.startsWith(spec.delimiter, from)) continue
    const close = findCloser(source, from, spec.delimiter, spec.underscoreRule)
    if (close === -1) continue
    const inner = source.slice(from, close)
    if (inner.trim() === '') continue
    return {
      node: { kind: spec.kind, children: parseInline(inner, depth + 1) },
      next: close + spec.delimiter.length
    }
  }
  return null
}

/** `[label](href)`. The label is parsed, so a bolded link keeps both. */
function tryLink(source: string, at: number, depth: number): Attempt | null {
  const labelEnd = findLinkLabelEnd(source, at + 1)
  if (labelEnd === -1) return null
  if (source[labelEnd + 1] !== '(') return null
  // Balanced, not the first `)`. Parentheses are common in real URLs
  // (Wikipedia disambiguators) and in the very hrefs this app refuses, so
  // `[x](javascript:alert(1))` has to be read whole to be judged at all.
  const hrefEnd = findHrefEnd(source, labelEnd + 2)
  if (hrefEnd === -1) return null

  const label = source.slice(at + 1, labelEnd)
  const href = source.slice(labelEnd + 2, hrefEnd).trim()
  // Links do not nest; a link inside a label is flattened to its label text.
  const children = parseInline(label, depth + 1).map(stripLinks)
  const node: InlineNode = isSafeHref(href)
    ? { kind: 'link', href, children }
    : { kind: 'deadLink', children }
  return { node, next: hrefEnd + 1 }
}

/** Index of the `)` closing a link destination, honouring nesting and escapes. */
function findHrefEnd(source: string, from: number): number {
  let depth = 0
  let i = from
  while (i < source.length) {
    const ch = source[i]
    if (ch === '\\' && i + 1 < source.length) {
      i += 2
      continue
    }
    if (ch === '(') depth += 1
    else if (ch === ')') {
      if (depth === 0) return i
      depth -= 1
    }
    i += 1
  }
  return -1
}

/** Index of the `]` closing a label, honouring nesting and escapes. */
function findLinkLabelEnd(source: string, from: number): number {
  let depth = 0
  let i = from
  while (i < source.length) {
    const ch = source[i]
    if (ch === '\\' && i + 1 < source.length) {
      i += 2
      continue
    }
    if (ch === '[') depth += 1
    else if (ch === ']') {
      if (depth === 0) return i
      depth -= 1
    }
    i += 1
  }
  return -1
}

function stripLinks(node: InlineNode): InlineNode {
  if (node.kind === 'link' || node.kind === 'deadLink') {
    return { kind: 'text', value: plainText(node.children) }
  }
  if (node.kind === 'strong' || node.kind === 'em' || node.kind === 'del') {
    return { ...node, children: node.children.map(stripLinks) }
  }
  return node
}

/** The visible text of a node list, for labels and accessibility. */
export function plainText(nodes: InlineNode[]): string {
  return nodes
    .map((n) => {
      switch (n.kind) {
        case 'text':
        case 'code':
          return n.value
        default:
          return plainText(n.children)
      }
    })
    .join('')
}
