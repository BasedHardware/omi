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

  // Fill the budget from the MOST RECENT activity backward: frames arrive
  // oldest-first, so the last block is the user's current screen. A proactive
  // insight must be about what they're doing NOW, so the newest blocks are kept
  // and the oldest are dropped when the budget is tight (the reverse of filling
  // from the front, which truncated away the current screen). The most-recent
  // block is always included — truncated if it alone exceeds the budget — so the
  // summary is never empty and is always anchored on the current screen.
  const selected: string[] = []
  let used = 0
  const SEP = 2 // '\n\n'
  for (let i = blocks.length - 1; i >= 0; i--) {
    const b = blocks[i]
    if (selected.length === 0) {
      selected.push(b.length > maxChars ? b.slice(0, maxChars) : b)
      used = selected[0].length
      continue
    }
    if (used + SEP + b.length > maxChars) break
    selected.push(b)
    used += SEP + b.length
  }
  // Emit oldest→newest so the model reads the current screen LAST (as "now").
  return selected.reverse().join('\n\n')
}
