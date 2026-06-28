// src/renderer/src/lib/screenGrouping.ts
import type { ScreenFrameLite } from '../../../shared/types'

export type ScreenSegment = { app: string; windowTitle: string; text: string }

// Group consecutive frames sharing app+window into one segment, concatenating
// distinct OCR lines in order (drop exact consecutive duplicates and blanks).
export function groupFrames(frames: ScreenFrameLite[]): ScreenSegment[] {
  const out: ScreenSegment[] = []
  let cur: { app: string; windowTitle: string; lines: string[]; seen: Set<string> } | null = null

  for (const fr of frames) {
    const text = (fr.ocrText ?? '').trim()
    if (!text) continue
    const sameContext = cur && cur.app === fr.app && cur.windowTitle === fr.windowTitle
    if (!sameContext) {
      if (cur) out.push({ app: cur.app, windowTitle: cur.windowTitle, text: cur.lines.join('\n') })
      cur = { app: fr.app, windowTitle: fr.windowTitle, lines: [], seen: new Set() }
    }
    if (cur && !cur.seen.has(text)) {
      cur.seen.add(text)
      cur.lines.push(text)
    }
  }
  if (cur && cur.lines.length) {
    out.push({ app: cur.app, windowTitle: cur.windowTitle, text: cur.lines.join('\n') })
  }
  return out
}

// Keep whole segments until the cumulative text length would exceed maxChars.
export function budgetSegments(segments: ScreenSegment[], maxChars: number): ScreenSegment[] {
  const out: ScreenSegment[] = []
  let used = 0
  for (const s of segments) {
    if (used + s.text.length > maxChars) break
    out.push(s)
    used += s.text.length
  }
  return out
}
