import { describe, it, expect, vi, afterEach } from 'vitest'
import { exportToNotion } from './notion'

afterEach(() => vi.unstubAllGlobals())

describe('exportToNotion', () => {
  it('splits a long memory across rich_text chunks without dropping the tail', async () => {
    const long = 'a'.repeat(5000)
    let body: { children: { bulleted_list_item: { rich_text: { text: { content: string } }[] } }[] } | null =
      null
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
})
