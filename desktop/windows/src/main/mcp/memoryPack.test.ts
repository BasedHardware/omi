import { describe, it, expect } from 'vitest'
import { buildMemoryPack, memoryPackChatUrl } from './memoryPack'
import type { ExportMemory } from '../../shared/types'

const MEMS: ExportMemory[] = [
  { content: 'Likes espresso', category: 'Preferences', createdAt: '2026-01-01T00:00:00Z' },
  { content: 'Building Omi', category: 'Projects', createdAt: '2026-01-01T00:00:00Z' }
]

describe('buildMemoryPack', () => {
  it('prepends the provider prompt, a rule, then the Markdown export', () => {
    const pack = buildMemoryPack('gemini', MEMS)
    expect(pack.startsWith('I’m attaching an Omi memory export.')).toBe(true)
    expect(pack).toContain('\n\n---\n\n')
    expect(pack).toContain('# Omi Memories')
    expect(pack).toContain('- Likes espresso')
  })

  it('uses the ChatGPT/Claude-specific prompts', () => {
    expect(buildMemoryPack('chatgpt', MEMS)).toContain('concise profile summary')
    expect(buildMemoryPack('claude', MEMS)).toContain('summarizing the most important things')
  })
})

describe('memoryPackChatUrl', () => {
  it('opens the provider chat (Mac destinationURL parity)', () => {
    expect(memoryPackChatUrl('chatgpt')).toBe('https://chatgpt.com/')
    expect(memoryPackChatUrl('claude')).toBe('https://claude.ai/new')
    expect(memoryPackChatUrl('gemini')).toBe('https://gemini.google.com/app')
  })
})
