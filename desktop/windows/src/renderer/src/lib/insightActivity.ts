// src/renderer/src/lib/insightActivity.ts
import type { RewindFrame } from '../../../shared/types'

// Slice to at most `max` UTF-16 units without splitting a surrogate pair, which
// would leave a lone surrogate — invalid UTF-8 that makes the Gemini body 400.
function sliceNoSplitSurrogate(s: string, max: number): string {
  if (s.length <= max) return s
  const c = s.charCodeAt(max - 1)
  const end = c >= 0xd800 && c <= 0xdbff ? max - 1 : max
  return s.slice(0, end)
}

// Group consecutive frames by app+window, concatenate distinct OCR lines, and
// cap total length. Output is a plain-text activity summary for the prompt.
export function summarizeActivity(frames: RewindFrame[], maxChars: number): string {
  const blocks: string[] = []
  let cur: { app: string; title: string; lines: string[]; seen: Set<string> } | null = null

  const flush = (): void => {
    if (cur && cur.lines.length) blocks.push(`## ${cur.app} — ${cur.title}\n${cur.lines.join('\n')}`)
  }
  for (const fr of frames) {
    const text = (fr.ocrText ?? '').trim()
    if (!text) continue
    if (!cur || cur.app !== fr.app || cur.title !== fr.windowTitle) {
      flush()
      cur = { app: fr.app, title: fr.windowTitle, lines: [], seen: new Set() }
    }
    if (!cur.seen.has(text)) {
      cur.seen.add(text)
      cur.lines.push(text)
    }
  }
  flush()

  let out = ''
  for (const b of blocks) {
    if (out === '') {
      // Always include the first block (truncated to the budget) so one verbose
      // screen never starves the summary — and we never make an empty Gemini call.
      out = sliceNoSplitSurrogate(b, maxChars)
      continue
    }
    if (out.length + 2 + b.length > maxChars) break
    out += '\n\n' + b
  }
  return out
}
