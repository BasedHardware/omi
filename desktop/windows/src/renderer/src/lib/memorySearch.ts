import type { Memory } from '../hooks/useMemories'

function searchableText(memory: Memory): string {
  return [
    memory.headline,
    memory.content,
    memory.category,
    memory.visibility,
    ...(memory.tags ?? [])
  ]
    .filter(Boolean)
    .join('\n')
    .toLowerCase()
}

export function memoryMatchesSearch(memory: Memory, query: string): boolean {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
  if (terms.length === 0) return true

  const haystack = searchableText(memory)
  return terms.every((term) => haystack.includes(term))
}

export function filterMemories(memories: Memory[], query: string): Memory[] {
  const trimmed = query.trim()
  if (!trimmed) return memories
  return memories.filter((memory) => memoryMatchesSearch(memory, trimmed))
}
