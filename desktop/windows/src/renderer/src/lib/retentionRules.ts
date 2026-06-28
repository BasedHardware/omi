import type { Memory } from '../hooks/useMemories'
import { isAppIndexMemory } from './memoryCleanup'
import { SCREEN_TAG } from './screenTag'

// A conversation normalized for the sweep: its id, where it lives, its kind (local
// only), and the plain transcript text.
export type SweepConvo = {
  id: string
  source: 'local' | 'cloud'
  kind?: string
  text: string
}

// Count real words in a transcript, dropping the section/speaker scaffolding the
// recorder adds ("Microphone:", "System audio:", "You:", "Speaker 1:").
export function transcriptWordCount(transcript: string): number {
  const cleaned = (transcript ?? '')
    .replace(/^(microphone|system audio):/gim, ' ')
    .replace(/^[A-Za-z ]{1,20}:/gm, ' ') // leading "You:" / "Speaker 1:" labels
    .replace(/\s+/g, ' ')
    .trim()
  if (!cleaned) return 0
  return cleaned.split(' ').filter(Boolean).length
}

// A conversation is "empty" (not worth keeping) under 5 real words.
export function isEmptyConversation(transcript: string): boolean {
  return transcriptWordCount(transcript) < 5
}

// Self-referential meta memories the synthesis sometimes writes
// ("The user has N memories stored…"). Anchored on the STORE phrasing
// (stored/saved/in Omi/app/account) so substantive content like "has 5 memories of
// the trip" / "from childhood" is NEVER matched.
export function isMetaJunkMemory(content: string): boolean {
  return /\buser has \d[\d,]* memories\s+(stored|saved|in (the )?(omi|app|application|account))\b/i.test(
    content ?? ''
  )
}

// All memory ids safe to remove: app/file-index synthesis (reused matcher),
// meta-junk, and exact-duplicate content (keep the first occurrence).
export function junkMemoryIds(memories: Memory[]): string[] {
  const ids = new Set<string>()
  const seen = new Set<string>()
  for (const m of memories) {
    const content = (m.content ?? '').trim()
    if (isAppIndexMemory(m) || isMetaJunkMemory(content)) {
      ids.add(m.id)
      continue
    }
    const norm = content.toLowerCase().replace(/\s+/g, ' ')
    if (norm) {
      if (seen.has(norm)) ids.add(m.id)
      else seen.add(norm)
    }
  }
  return [...ids]
}

// Why each junk memory is flagged — so a dry-run can show the user what would be
// removed (e.g. "mostly screen-synth") before they trust it. Categories are
// mutually exclusive and sum to `total` (== junkMemoryIds length).
export type RetentionMemoryBreakdown = {
  total: number
  screenSynth: number // SCREEN_TAG (screen-synthesis memories)
  appIndex: number // app/file-index synthesis (non-screen)
  meta: number // "user has N memories stored" self-referential
  duplicate: number // exact-duplicate content
}

export function memoryJunkBreakdown(memories: Memory[]): RetentionMemoryBreakdown {
  const b: RetentionMemoryBreakdown = { total: 0, screenSynth: 0, appIndex: 0, meta: 0, duplicate: 0 }
  const seen = new Set<string>()
  for (const m of memories) {
    const content = (m.content ?? '').trim()
    if (m.tags?.includes(SCREEN_TAG)) {
      b.screenSynth++
      b.total++
    } else if (isAppIndexMemory(m)) {
      b.appIndex++
      b.total++
    } else if (isMetaJunkMemory(content)) {
      b.meta++
      b.total++
    } else {
      const norm = content.toLowerCase().replace(/\s+/g, ' ')
      if (norm) {
        if (seen.has(norm)) {
          b.duplicate++
          b.total++
        } else {
          seen.add(norm)
        }
      }
    }
  }
  return b
}

export type RetentionPlan = {
  localConvoIds: string[]
  cloudConvoIds: string[]
  memoryIds: string[]
}

// Decide what to prune. Conservative and source-aware:
// - LOCAL recordings are THIS app's silence-split fragments, so prune the short
//   (<5-word) empties; never touch saved chats.
// - CLOUD conversations are account-wide (could be real short notes from the
//   user's phone/macOS), so prune only the TRULY empty ones (no transcript at
//   all) — never merely-short ones. The sweep also only feeds COMPLETED cloud
//   conversations here (it filters out still-`processing` ones), so an empty one
//   is genuinely empty, not mid-flight.
export function planRetention(convos: SweepConvo[], memories: Memory[]): RetentionPlan {
  const localConvoIds: string[] = []
  const cloudConvoIds: string[] = []
  for (const c of convos) {
    if (c.source === 'local') {
      if (c.kind !== 'chat' && isEmptyConversation(c.text)) localConvoIds.push(c.id)
    } else if (transcriptWordCount(c.text) === 0) {
      cloudConvoIds.push(c.id)
    }
  }
  return { localConvoIds, cloudConvoIds, memoryIds: junkMemoryIds(memories) }
}
