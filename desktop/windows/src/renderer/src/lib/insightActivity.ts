// src/renderer/src/lib/insightActivity.ts
import type { RewindFrame } from '../../../shared/types'

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
      out = b.length > maxChars ? b.slice(0, maxChars) : b
      continue
    }
    if (out.length + b.length > maxChars) break
    out += '\n\n' + b
  }
  return out
}
