import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { parseBlocks, type Block, type ListBlock } from '../lib/markdown/blocks'
import { parseInline, plainText, type InlineNode } from '../lib/markdown/inline'
import type { ColumnAlignment, MarkdownTable } from '../lib/markdown/table'

// Markdown for chat bubbles, rendered from a parsed tree rather than by regex
// substitution. The grammar and every rule in it live in `lib/markdown/`, which
// is pure and unit-tested without a DOM; this file only turns the tree into
// elements.
//
// Renders React elements, never raw HTML, so there is no injection surface: a
// `<script>` in a reply is text and stays text. The one place a reply gets to
// influence the DOM beyond its own characters is a link's href, which is
// allowlisted in `lib/markdown/inline.ts` — see the note there for why chat
// replies are treated as untrusted input.
//
// Images are deliberately not rendered. An `![alt](url)` becomes its alt text.
// A reply can be steered by whatever is on the user's screen, so rendering a
// remote image would let an injected URL fetch on load: a tracking pixel that
// reports the user's IP and that the chat was opened, with nothing clicked.

function renderInline(nodes: InlineNode[], keyPrefix = ''): React.ReactNode[] {
  return nodes.map((node, i) => {
    const key = `${keyPrefix}${i}`
    switch (node.kind) {
      case 'text':
        // The string itself, not a wrapping span. React escapes it either way,
        // and a span per text run buries the formatting elements a reader (or
        // a screen reader) is meant to find inside layers of anonymous nodes.
        return node.value
      case 'code':
        return (
          <code key={key} className="rounded bg-white/10 px-1 py-0.5 font-mono text-[0.85em]">
            {node.value}
          </code>
        )
      case 'strong':
        return <strong key={key}>{renderInline(node.children, `${key}.`)}</strong>
      case 'em':
        return <em key={key}>{renderInline(node.children, `${key}.`)}</em>
      case 'del':
        return (
          <del key={key} className="opacity-70">
            {renderInline(node.children, `${key}.`)}
          </del>
        )
      case 'link':
        return (
          <a
            key={key}
            href={node.href}
            target="_blank"
            rel="noreferrer"
            className="underline underline-offset-2 hover:text-white"
          >
            {renderInline(node.children, `${key}.`)}
          </a>
        )
      case 'deadLink':
        // The label still shows; only the navigation is withheld.
        return <span key={key}>{renderInline(node.children, `${key}.`)}</span>
    }
  })
}

// A fenced code block with a hover-revealed copy button pinned to its top-right.
// The button lives in a relatively-positioned wrapper (not inside <pre>), so it
// stays fixed while long lines scroll the <pre> horizontally, and toggles Copy →
// Check for 1.5s after a successful copy — the app's copy-feedback idiom
// (ConversationDetail). The group is named so the reveal is scoped to this block
// and never triggered by an ancestor's `group` hover. Block code only — inline
// code gets no button.
function CodeBlock({ code }: { code: string }): React.JSX.Element {
  const [copied, setCopied] = useState(false)
  const onCopy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard can be denied; the code is still selectable to copy by hand.
    }
  }
  return (
    <div className="group/codeblock relative my-2">
      <pre className="overflow-x-auto rounded-[10px] border border-line bg-white/[0.06] p-3 font-mono text-[0.85em]">
        <code>{code}</code>
      </pre>
      <button
        type="button"
        onClick={() => void onCopy()}
        title={copied ? 'Copied' : 'Copy code'}
        aria-label={copied ? 'Copied' : 'Copy code'}
        className="absolute right-2 top-2 rounded-md border border-line bg-black/40 p-1.5 text-white/60 opacity-0 backdrop-blur transition hover:text-white focus-visible:opacity-100 group-hover/codeblock:opacity-100"
      >
        {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  )
}

const ALIGN_CLASS: Record<ColumnAlignment, string> = {
  left: 'text-left',
  center: 'text-center',
  right: 'text-right'
}

/**
 * A table, in its own horizontal scroller.
 *
 * A wide table must not widen the chat column, so the scroller is the table's
 * and not the page's. macOS does the same thing and labels it for screen
 * readers; this carries that over.
 */
function TableBlock({ table }: { table: MarkdownTable }): React.JSX.Element {
  return (
    <div className="my-2 overflow-x-auto" role="region" aria-label="Scrollable table" tabIndex={0}>
      <table className="w-full border-collapse text-[0.95em]">
        <thead>
          <tr>
            {table.header.map((cell, i) => (
              <th
                key={i}
                scope="col"
                className={`border border-line px-2 py-1 font-semibold ${ALIGN_CLASS[table.alignments[i] ?? 'left']}`}
              >
                {renderInline(parseInline(cell))}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, r) => (
            <tr key={r}>
              {row.map((cell, c) => (
                <td
                  key={c}
                  className={`border border-line px-2 py-1 align-top ${ALIGN_CLASS[table.alignments[c] ?? 'left']}`}
                >
                  {renderInline(parseInline(cell))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ListItems({ list, keyPrefix }: { list: ListBlock; keyPrefix: string }): React.JSX.Element {
  const className = list.ordered ? 'my-1 list-decimal space-y-0.5 pl-5' : 'my-1 space-y-0.5 pl-5'
  const items = list.items.map((item, i) => (
    <li key={i} className={item.checked === null ? undefined : 'list-none -ml-5 flex gap-2'}>
      {item.checked !== null && (
        <input
          type="checkbox"
          checked={item.checked}
          readOnly
          // A rendered reply is a transcript, not a form: the box shows what
          // the model wrote and clicking it would edit nothing.
          aria-label={plainText(parseInline(item.text))}
          className="mt-1 h-3.5 w-3.5 shrink-0 accent-white/70"
        />
      )}
      <span>
        {renderInline(parseInline(item.text), `${keyPrefix}${i}.`)}
        {item.children && <ListItems list={item.children} keyPrefix={`${keyPrefix}${i}.`} />}
      </span>
    </li>
  ))
  return list.ordered ? (
    <ol className={className} start={list.start}>
      {items}
    </ol>
  ) : (
    <ul className={`${className} ${list.items.some((i) => i.checked !== null) ? '' : 'list-disc'}`}>
      {items}
    </ul>
  )
}

/** Heading sizes. All six are distinguishable; the shipped renderer's were not. */
const HEADING_CLASS: Record<number, string> = {
  1: 'mb-1 mt-3 text-[1.35em] font-semibold',
  2: 'mb-1 mt-3 text-[1.2em] font-semibold',
  3: 'mb-1 mt-2 text-[1.1em] font-semibold',
  4: 'mb-1 mt-2 font-semibold',
  5: 'mb-1 mt-2 font-semibold opacity-90',
  6: 'mb-1 mt-2 text-[0.95em] font-semibold opacity-80'
}

function renderBlocks(blocks: Block[], keyPrefix = ''): React.ReactNode[] {
  return blocks.map((block, i) => {
    const key = `${keyPrefix}${i}`
    switch (block.kind) {
      case 'paragraph':
        return (
          <p key={key} className="whitespace-pre-wrap">
            {renderInline(parseInline(block.text), `${key}.`)}
          </p>
        )
      case 'heading': {
        const Tag = `h${block.level}` as 'h1'
        return (
          <Tag key={key} className={HEADING_CLASS[block.level] ?? HEADING_CLASS[6]}>
            {renderInline(parseInline(block.text), `${key}.`)}
          </Tag>
        )
      }
      case 'code':
        return <CodeBlock key={key} code={block.text} />
      case 'quote':
        return (
          <blockquote
            key={key}
            className="my-2 space-y-1 border-l-2 border-line pl-3 text-white/80"
          >
            {renderBlocks(block.blocks, `${key}.`)}
          </blockquote>
        )
      case 'table':
        return <TableBlock key={key} table={block.table} />
      case 'thematicBreak':
        return <hr key={key} className="my-3 border-line" />
      case 'list':
        return <ListItems key={key} list={block} keyPrefix={`${key}.`} />
    }
  })
}

export function Markdown({ text }: { text: string }): React.JSX.Element {
  return <div className="space-y-1">{renderBlocks(parseBlocks(text))}</div>
}
