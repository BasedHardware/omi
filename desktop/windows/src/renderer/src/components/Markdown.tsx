import { useState } from 'react'
import { Check, Copy } from 'lucide-react'

// Minimal, dependency-free markdown for chat bubbles. Supports the subset the
// Omi chat actually emits — headings, bullet/numbered lists, fenced + inline
// code, bold, italic, and links. NOT a full CommonMark parser; anything it does
// not recognize falls through as plain text (so a half-streamed `**` just shows
// literally until the closing marker arrives). Renders React elements, never raw
// HTML, so there is no injection surface.

// One regex with the token captured, so String.split keeps the delimiters: the
// result alternates plain-text / token / plain-text. Bold is listed before
// italic so `**x**` matches bold, not two italics.
const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\n]+\*|_[^_\n]+_|\[[^\]]+\]\([^)]+\))/g

function renderInline(text: string): React.ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    if (!part) return null
    if (part.startsWith('**') && part.endsWith('**'))
      return <strong key={i}>{part.slice(2, -2)}</strong>
    if (part.startsWith('`') && part.endsWith('`'))
      return (
        <code key={i} className="rounded bg-white/10 px-1 py-0.5 font-mono text-[0.85em]">
          {part.slice(1, -1)}
        </code>
      )
    if (
      (part.startsWith('*') && part.endsWith('*')) ||
      (part.startsWith('_') && part.endsWith('_'))
    )
      return <em key={i}>{part.slice(1, -1)}</em>
    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part)
    if (link) {
      // Only http(s)/mailto links are clickable. Chat replies can be steered by
      // indirect prompt injection (the prompt includes OCR of whatever is on the
      // user's screen), so a model could emit a file://, UNC (\\host\share), or
      // custom-protocol href; rendering those as live links enables one-click
      // NTLM-hash leakage and OS protocol-handler abuse. Anything else falls back
      // to plain text — the label still shows, it just isn't a link.
      const href = link[2].trim()
      if (/^(https?:|mailto:)/i.test(href))
        return (
          <a key={i} href={href} target="_blank" rel="noreferrer" className="underline">
            {link[1]}
          </a>
        )
      return <span key={i}>{link[1]}</span>
    }
    return <span key={i}>{part}</span>
  })
}

const UL = /^\s*[-*+]\s+/
const OL = /^\s*\d+\.\s+/
const FENCE = /^```/
const HEADING = /^(#{1,6})\s+(.*)$/

// A fenced code block with a hover-revealed copy button pinned to its top-right.
// The button lives in a relatively-positioned wrapper (not inside <pre>), so it
// stays fixed while long lines scroll the <pre> horizontally, and toggles Copy →
// Check for 1.5s after a successful copy — the app's copy-feedback idiom
// (ConversationDetail). The group is named so the reveal is scoped to this block
// and never triggered by an ancestor's `group` hover. Block code only — inline
// code (renderInline) gets no button.
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

export function Markdown({ text }: { text: string }): React.JSX.Element {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const blocks: React.ReactNode[] = []
  let i = 0
  let key = 0

  while (i < lines.length) {
    const line = lines[i]

    if (FENCE.test(line.trim())) {
      const buf: string[] = []
      i++
      while (i < lines.length && !FENCE.test(lines[i].trim())) buf.push(lines[i++])
      i++ // consume closing fence
      blocks.push(<CodeBlock key={key++} code={buf.join('\n')} />)
      continue
    }

    const h = HEADING.exec(line)
    if (h) {
      blocks.push(
        <p key={key++} className="mb-1 mt-2 font-semibold">
          {renderInline(h[2])}
        </p>
      )
      i++
      continue
    }

    if (UL.test(line)) {
      const items: string[] = []
      while (i < lines.length && UL.test(lines[i])) items.push(lines[i++].replace(UL, ''))
      blocks.push(
        <ul key={key++} className="my-1 list-disc space-y-0.5 pl-5">
          {items.map((it, j) => (
            <li key={j}>{renderInline(it)}</li>
          ))}
        </ul>
      )
      continue
    }

    if (OL.test(line)) {
      const items: string[] = []
      while (i < lines.length && OL.test(lines[i])) items.push(lines[i++].replace(OL, ''))
      blocks.push(
        <ol key={key++} className="my-1 list-decimal space-y-0.5 pl-5">
          {items.map((it, j) => (
            <li key={j}>{renderInline(it)}</li>
          ))}
        </ol>
      )
      continue
    }

    if (line.trim() === '') {
      i++
      continue
    }

    // Paragraph: gather consecutive lines until a blank line or a block starter.
    const para: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !FENCE.test(lines[i].trim()) &&
      !HEADING.test(lines[i]) &&
      !UL.test(lines[i]) &&
      !OL.test(lines[i])
    )
      para.push(lines[i++])
    blocks.push(
      <p key={key++} className="whitespace-pre-wrap">
        {renderInline(para.join('\n'))}
      </p>
    )
  }

  return <div className="space-y-1">{blocks}</div>
}
