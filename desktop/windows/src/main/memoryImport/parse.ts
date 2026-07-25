// Parse a pasted ChatGPT/Claude "memory dump" — the assistant's full response
// when asked to list everything it remembers — into individual memory strings.
// Mirrors the macOS import path: strip list markup + conversational scaffolding,
// dedupe, and keep the rest. The Settings UI shows the result for review before
// anything is sent to the backend, so erring toward keeping a line is safe.

// Opener/closer scaffolding lines that are not memories themselves. Kept tight
// so real third-person memory lines ("Has two cats", "Prefers concise answers")
// are never dropped.
const SCAFFOLDING = [
  /^sure[,!. ]/i,
  /^here(?:'s| is| are)\b.*\bmemor/i,
  /^below (?:is|are)\b/i,
  /^these are\b.*\bmemor/i,
  /^(?:your |the )?saved memories\b/i,
  /^(?:here are )?the (?:things|details) (?:i|that i) (?:remember|know)/i,
  /^let me know\b/i,
  /^(?:and )?that'?s (?:all|everything)\b/i,
  /^is there anything\b/i,
  /^i (?:currently )?(?:remember|have stored|don'?t have)\b.*(?:memor|the following|about you)/i,
  // Omi's own export stamp ("_Exported <date> · N memories_", italics already
  // stripped) — so a user who exports and re-imports doesn't inject it as a memory.
  /^exported\s+\d{4}-\d{2}-\d{2}\b/i
]

// Remove a single leading list marker: -, *, common bullet/dash markers,
// or "1." / "1)".
function stripMarker(line: string): string {
  return line.replace(/^\s*(?:[-*\u2022\u2013\u2014\u2023\u2043]\s+|\d+[.)]\s+)/, '')
}

// Strip surrounding markdown emphasis / heading syntax.
function stripFormatting(s: string): string {
  let t = s.trim()
  t = t.replace(/^#{1,6}\s+/, '') // markdown heading
  t = t.replace(/^\*\*([\s\S]*)\*\*$/, '$1') // **bold**
  t = t.replace(/^_([\s\S]*)_$/, '$1') // _italic_
  return t.trim()
}

function isMarkdownFence(line: string): boolean {
  return /^\s*(?:```|~~~)/.test(line)
}

// A markdown heading line is structural, never a memory. The exporter renders
// its title ("# Omi Memories") and every category ("## Personal") as headings,
// and section headers in any pasted dump are labels, not memories. Detected on
// the RAW line — before stripFormatting would turn "## Personal" into the bogus
// memory "Personal".
function isMarkdownHeading(line: string): boolean {
  return /^\s*#{1,6}\s+/.test(line)
}

export function parseMemoryDump(dump: string): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const raw of dump.split(/\r?\n/)) {
    if (isMarkdownFence(raw)) continue
    if (isMarkdownHeading(raw)) continue
    const stripped = stripFormatting(stripMarker(raw))
    if (stripped.length < 3) continue // blank lines, stray numbering/punctuation
    if (SCAFFOLDING.some((re) => re.test(stripped))) continue
    const key = stripped.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(stripped)
  }
  return out
}
