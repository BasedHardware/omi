import type { ExportMemory } from '../../shared/types'

// Render memories as a single Markdown document, grouped by category, used by
// the Obsidian and plain-file targets (Notion builds its own block payload).
// Mirrors the macOS MemoryExportService layout: a title, an export stamp, then
// one bullet per memory under a category heading.
export function formatMemoriesMarkdown(memories: ExportMemory[], now = new Date()): string {
  const date = now.toISOString().slice(0, 10)
  const noun = memories.length === 1 ? 'memory' : 'memories'
  const lines: string[] = ['# Omi Memories', '', `_Exported ${date} · ${memories.length} ${noun}_`, '']

  const groups = new Map<string, ExportMemory[]>()
  for (const m of memories) {
    const cat = (m.category ?? '').trim() || 'Other'
    const arr = groups.get(cat) ?? []
    arr.push(m)
    groups.set(cat, arr)
  }

  for (const [cat, items] of [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    lines.push(`## ${cat}`, '')
    for (const m of items) lines.push(`- ${m.content.replace(/\s*\n\s*/g, ' ').trim()}`)
    lines.push('')
  }

  return lines.join('\n').trimEnd() + '\n'
}
