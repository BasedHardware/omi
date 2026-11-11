import { describe, it, expect } from 'vitest'
import { parseMemoryDump } from './parse'
import { formatMemoriesMarkdown } from '../memoryExport/format'
import type { ExportMemory } from '../../shared/types'

describe('parseMemoryDump', () => {
  it('extracts bulleted memories and strips markers', () => {
    const dump = `- Has two cats named Mochi and Pip
* Prefers concise answers
• Works as a software engineer`
    expect(parseMemoryDump(dump)).toEqual([
      'Has two cats named Mochi and Pip',
      'Prefers concise answers',
      'Works as a software engineer'
    ])
  })

  it('handles common pasted markdown list markers', () => {
    const dump = `— Enjoys tea
‣ Uses Windows
⁃ Keeps notes in Obsidian`
    expect(parseMemoryDump(dump)).toEqual(['Enjoys tea', 'Uses Windows', 'Keeps notes in Obsidian'])
  })

  it('handles numbered lists', () => {
    const dump = `1. Lives in Seattle\n2) Is learning Spanish`
    expect(parseMemoryDump(dump)).toEqual(['Lives in Seattle', 'Is learning Spanish'])
  })

  it('drops markdown code fences around copied dumps', () => {
    const dump = '```markdown\n- Likes coffee\n- Prefers short replies\n```'
    expect(parseMemoryDump(dump)).toEqual(['Likes coffee', 'Prefers short replies'])
  })

  it('drops conversational scaffolding but keeps real memories', () => {
    const dump = `Sure! Here are your saved memories:
- Has a dog
That's everything I have.`
    expect(parseMemoryDump(dump)).toEqual(['Has a dog'])
  })

  it('dedupes case-insensitively', () => {
    const dump = `- Likes coffee\n- likes coffee\n- Likes tea`
    expect(parseMemoryDump(dump)).toEqual(['Likes coffee', 'Likes tea'])
  })

  it('strips markdown emphasis and drops heading lines', () => {
    // Heading lines are section labels, not memories — the exporter renders its
    // title and categories as headings, so keeping them would inject scaffolding.
    const dump = `## Profile\n**Enjoys hiking**\n_Vegetarian_`
    expect(parseMemoryDump(dump)).toEqual(['Enjoys hiking', 'Vegetarian'])
  })

  it('returns nothing for empty input', () => {
    expect(parseMemoryDump('')).toEqual([])
    expect(parseMemoryDump('\n\n   \n')).toEqual([])
  })

  // The offline fallback path when re-importing a file Omi itself exported: none
  // of the exporter's own scaffolding (title, "_Exported …_" stamp, category
  // headings) may survive as a memory, but every real content line must.
  describe('round-trips the real exporter without leaking scaffolding', () => {
    const memories: ExportMemory[] = [
      { content: 'Has two cats named Mochi and Pip', category: 'Personal' },
      { content: 'Works as a software engineer', category: 'Work' },
      { content: 'Prefers concise answers', category: 'Preferences' }
    ]
    // Import the real formatter (do NOT hand-copy its output) so the test tracks
    // the exporter if its layout ever changes.
    const exported = formatMemoriesMarkdown(memories, new Date('2026-07-15T00:00:00Z'))
    const parsed = parseMemoryDump(exported)

    it('keeps every real memory content line', () => {
      for (const m of memories) expect(parsed).toContain(m.content)
    })

    it('drops the title, export stamp, and category headings', () => {
      expect(parsed).not.toContain('Omi Memories')
      expect(parsed.some((l) => /^exported/i.test(l))).toBe(false)
      for (const cat of ['Personal', 'Work', 'Preferences']) {
        expect(parsed).not.toContain(cat)
      }
    })

    it('yields exactly the real memories, nothing more', () => {
      // Order-independent: the exporter groups by category (sorted), so parsed
      // order need not match input order — only the set must.
      expect([...parsed].sort()).toEqual(memories.map((m) => m.content).sort())
    })
  })
})
