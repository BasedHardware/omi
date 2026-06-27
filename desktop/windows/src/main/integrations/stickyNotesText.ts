// Pure helpers for turning raw Sticky Notes `Note` rows into importable notes.
// Sticky Notes stores bodies with lightweight markup + control chars; synthesis
// only needs the words, so we strip control characters and collapse whitespace
// rather than parsing the markup.
import type { StickyNote } from '../../shared/types'

// Sticky Notes prefixes each content block with a `\id=<guid>` anchor; the real
// note text follows it (e.g. `\id=<guid> My favorite movie is ...`). Strip these
// anchors so only the human text reaches synthesis, turning each block boundary
// into a newline.
const BLOCK_ANCHOR =
  /\\id=[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\s*/g

export function cleanNoteText(raw: string): string {
  if (!raw) return ''
  return raw
    .replace(BLOCK_ANCHOR, '\n') // drop block-id anchors, keep block boundaries
    .replace(/\r\n?/g, '\n') // normalize line endings first
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, ' ') // strip control chars (keep tab + newline)
    .replace(/[ \t]+/g, ' ')
    .replace(/ *\n */g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

/** A raw row read from the Sticky Notes `Note` table (before cleaning). */
export type RawNoteRow = {
  id: string
  text: string
  updatedAt: number
  deleted?: boolean
}

// Clean + filter raw rows: drop deleted and empty/whitespace-only notes, newest
// (highest updatedAt) first.
export function toStickyNotes(rows: RawNoteRow[]): StickyNote[] {
  return rows
    .filter((r) => !r.deleted)
    .map((r) => ({ id: r.id, text: cleanNoteText(r.text ?? ''), updatedAt: r.updatedAt }))
    .filter((n) => n.text.length > 0)
    .sort((a, b) => b.updatedAt - a.updatedAt)
}
