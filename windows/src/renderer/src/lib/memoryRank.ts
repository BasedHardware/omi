import type { Memory } from '../hooks/useMemories'

// Tokens too short or too generic to carry meaning when correlating a folder
// name / question with saved memories. Keeps the overlap score from matching on
// filler words ("the project I am working on" shouldn't match everything).
const STOP = new Set([
  'the',
  'and',
  'for',
  'with',
  'that',
  'this',
  'you',
  'your',
  'are',
  'was',
  'from',
  'have',
  'has',
  'what',
  'who',
  'how',
  'why',
  'about',
  'project',
  'projects',
  'recent',
  'recently',
  'working',
  'work',
  'folder',
  'folders',
  'file',
  'files'
])

// Split arbitrary text (including folder-style slugs like "omi-windows" or
// "sandbox_chat_kg") into meaningful lowercase tokens.
function tokenize(s: string): string[] {
  return s
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((t) => t.length >= 3 && !STOP.has(t))
}

// Rank saved memories by how well they overlap the query (a folder/project name
// or the user's question), returning the top `limit` memory contents (trimmed).
// Score is the count of distinct query tokens present in the memory; ties break
// toward more recent memories. Zero-overlap memories are dropped, so an empty
// or all-filler query yields []. Pure — no I/O.
export function rankMemories(memories: Memory[], query: string, limit: number): string[] {
  const qTokens = new Set(tokenize(query))
  if (qTokens.size === 0) return []
  return memories
    .map((mem) => {
      const mTokens = new Set(tokenize(mem.content))
      let score = 0
      for (const t of qTokens) if (mTokens.has(t)) score++
      return { mem, score }
    })
    .filter((s) => s.score > 0)
    .sort(
      (a, b) =>
        b.score - a.score ||
        new Date(b.mem.created_at).getTime() - new Date(a.mem.created_at).getTime()
    )
    .slice(0, limit)
    .map((s) => s.mem.content.trim())
}
