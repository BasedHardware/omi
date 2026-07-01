import { describe, it, expect, vi, afterEach } from 'vitest'
import { exportToNotion } from './notion'

afterEach(() => vi.unstubAllGlobals())

describe('exportToNotion', () => {
  it('splits a long memory across rich_text chunks without dropping the tail', async () => {
    const long = 'a'.repeat(5000)
    let body: {
      children: { bulleted_list_item: { rich_text: { text: { content: string } }[] } }[]
    } | null = null
    const fetchMock = vi.fn(async (_url: string, init: { body: string }) => {
      body = JSON.parse(init.body)
      return { ok: true, json: async () => ({ id: 'p1', url: 'https://notion.so/p1' }) }
    })
    vi.stubGlobal('fetch', fetchMock)

    await exportToNotion('tok', 'parent', [{ content: long, category: 'X' }])

    const richText = body!.children[0].bulleted_list_item.rich_text
    expect(richText.map((r) => r.text.content).join('')).toBe(long)
    expect(richText.length).toBe(3) // 5000 / 2000 => 3 chunks
  })

  it('chunks by UTF-16 units and never leaves a lone surrogate', async () => {
    const content = 'a' + '😀'.repeat(1000) // 2001 UTF-16 units, boundary lands mid-emoji
    let body: {
      children: { bulleted_list_item: { rich_text: { text: { content: string } }[] } }[]
    } | null = null
    const fetchMock = vi.fn(async (_url: string, init: { body: string }) => {
      body = JSON.parse(init.body)
      return { ok: true, json: async () => ({ id: 'p', url: 'u' }) }
    })
    vi.stubGlobal('fetch', fetchMock)

    await exportToNotion('tok', 'parent', [{ content, category: 'X' }])

    const richText = body!.children[0].bulleted_list_item.rich_text
    for (const r of richText) {
      expect(r.text.content.length).toBeLessThanOrEqual(2000)
      expect(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])/.test(r.text.content)).toBe(false) // no lone high surrogate
      expect(/(^|[^\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(r.text.content)).toBe(false) // no lone low surrogate
    }
    expect(richText.map((r) => r.text.content).join('')).toBe(content)
  })

  it('spills a memory beyond 100 chunks into multiple blocks instead of truncating', async () => {
    const content = 'a'.repeat(250_000) // 125 chunks of 2000
    let body: {
      children: { bulleted_list_item: { rich_text: { text: { content: string } }[] } }[]
    } | null = null
    const fetchMock = vi.fn(async (_url: string, init: { body: string }) => {
      body = JSON.parse(init.body)
      return { ok: true, json: async () => ({ id: 'p', url: 'u' }) }
    })
    vi.stubGlobal('fetch', fetchMock)

    await exportToNotion('tok', 'parent', [{ content, category: 'X' }])

    const blocks = body!.children
    expect(blocks.length).toBe(2) // ceil(125 / 100)
    const all = blocks
      .flatMap((b) => b.bulleted_list_item.rich_text.map((r) => r.text.content))
      .join('')
    expect(all).toBe(content)
  })
})
