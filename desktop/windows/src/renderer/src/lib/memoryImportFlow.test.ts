import { describe, expect, it } from 'vitest'
import { memoryImportApp, readMemoryImportStats, recordMemoryImport } from './memoryImportFlow'

function fakeStorage(seed?: Record<string, string>): Storage {
  const data = new Map(Object.entries(seed ?? {}))
  return {
    get length() {
      return data.size
    },
    clear: () => data.clear(),
    getItem: (key: string) => data.get(key) ?? null,
    key: (index: number) => Array.from(data.keys())[index] ?? null,
    removeItem: (key: string) => {
      data.delete(key)
    },
    setItem: (key: string, value: string) => {
      data.set(key, value)
    }
  }
}

describe('memoryImportFlow', () => {
  it('builds source-specific app metadata and prompts', () => {
    const chatgpt = memoryImportApp('chatgpt')
    const claude = memoryImportApp('claude')

    expect(chatgpt.label).toBe('ChatGPT')
    expect(chatgpt.url).toBe('https://chatgpt.com/')
    expect(chatgpt.prompt).toContain('ChatGPT currently remembers')
    expect(chatgpt.responsePlaceholder).toContain('ChatGPT')

    expect(claude.label).toBe('Claude')
    expect(claude.url).toBe('https://claude.ai/new')
    expect(claude.prompt).toContain('Claude currently remembers')
    expect(claude.responsePlaceholder).toContain('Claude')
  })

  it('records last-import count and timestamp per source', () => {
    const storage = fakeStorage()

    let stats = recordMemoryImport('chatgpt', 3, 1700000000000, storage)
    expect(stats.chatgpt).toEqual({ count: 3, importedAt: 1700000000000 })
    expect(stats.claude).toBeUndefined()

    stats = recordMemoryImport('claude', 2, 1800000000000, storage)
    expect(stats.chatgpt).toEqual({ count: 3, importedAt: 1700000000000 })
    expect(stats.claude).toEqual({ count: 2, importedAt: 1800000000000 })
    expect(readMemoryImportStats(storage)).toEqual(stats)
  })

  it('ignores malformed stored stats', () => {
    const storage = fakeStorage({
      'omi.memoryImport.stats.v1': JSON.stringify({
        chatgpt: { count: '3', importedAt: 1700000000000 },
        claude: { count: 4, importedAt: 1800000000000 },
        other: { count: 9, importedAt: 1900000000000 }
      })
    })

    expect(readMemoryImportStats(storage)).toEqual({
      claude: { count: 4, importedAt: 1800000000000 }
    })
  })
})
