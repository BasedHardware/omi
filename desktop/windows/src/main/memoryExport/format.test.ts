import { describe, it, expect } from 'vitest'
import { formatMemoriesMarkdown } from './format'

describe('formatMemoriesMarkdown', () => {
  const at = new Date('2026-06-03T12:00:00Z')

  it('renders a title, export stamp, and category groups', () => {
    const md = formatMemoriesMarkdown(
      [
        { content: 'Has two cats', category: 'Personal' },
        { content: 'Prefers TypeScript', category: 'Work' },
        { content: 'Lives in Seattle', category: 'Personal' }
      ],
      at
    )
    expect(md).toBe(
      `# Omi Memories

_Exported 2026-06-03 · 3 memories_

## Personal

- Has two cats
- Lives in Seattle

## Work

- Prefers TypeScript
`
    )
  })

  it('falls back to "Other" when category is missing', () => {
    const md = formatMemoriesMarkdown([{ content: 'No category here' }], at)
    expect(md).toContain('## Other')
    expect(md).toContain('- No category here')
    expect(md).toContain('· 1 memory_')
  })

  it('collapses newlines inside a memory into one bullet', () => {
    const md = formatMemoriesMarkdown([{ content: 'line one\n  line two' }], at)
    expect(md).toContain('- line one line two')
  })
})
