import { describe, it, expect } from 'vitest'
import { parseMemoryDump } from './parse'

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

  it('strips markdown emphasis and headings', () => {
    const dump = `## Profile\n**Enjoys hiking**\n_Vegetarian_`
    expect(parseMemoryDump(dump)).toEqual(['Profile', 'Enjoys hiking', 'Vegetarian'])
  })

  it('returns nothing for empty input', () => {
    expect(parseMemoryDump('')).toEqual([])
    expect(parseMemoryDump('\n\n   \n')).toEqual([])
  })
})
