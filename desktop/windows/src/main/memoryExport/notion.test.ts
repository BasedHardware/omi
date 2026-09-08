// Notion export drives Electron's net.fetch (Chromium network stack) — mock it
// the same way gemini.test.ts does, then assert the create + append requests
// fire with the right method/URL/body shape and that a non-ok response throws.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({ fetch: vi.fn() }))

vi.mock('electron', () => ({ net: { fetch: h.fetch } }))

import { exportToNotion } from './notion'
import type { ExportMemory } from '../../shared/types'

const NOTION_VERSION = '2022-06-28'

function ok(body: unknown): { ok: true; status: number; json: () => Promise<unknown> } {
  return { ok: true, status: 200, json: async () => body }
}

function mems(n: number): ExportMemory[] {
  return Array.from({ length: n }, (_, i) => ({ content: `memory ${i}` }))
}

beforeEach(() => vi.clearAllMocks())
afterEach(() => vi.restoreAllMocks())

describe('exportToNotion', () => {
  it('creates a page via POST /v1/pages with auth headers and returns its url', async () => {
    h.fetch.mockResolvedValueOnce(ok({ id: 'page-1', url: 'https://notion.so/page-1' }))

    const url = await exportToNotion('secret-token', 'parent-123', mems(3))

    expect(url).toBe('https://notion.so/page-1')
    expect(h.fetch).toHaveBeenCalledTimes(1)

    const [reqUrl, init] = h.fetch.mock.calls[0]
    expect(reqUrl).toBe('https://api.notion.com/v1/pages')
    expect(init.method).toBe('POST')
    expect(init.headers).toMatchObject({
      Authorization: 'Bearer secret-token',
      'Notion-Version': NOTION_VERSION,
      'Content-Type': 'application/json'
    })
    const body = JSON.parse(init.body)
    expect(body.parent).toEqual({ page_id: 'parent-123' })
    expect(body.properties.title.title[0].text.content).toBe('Omi Memories')
    expect(body.children).toHaveLength(3)
    expect(body.children[0].type).toBe('bulleted_list_item')
  })

  it('appends overflow blocks via PATCH /v1/blocks/{id}/children in 100-block batches', async () => {
    // 250 memories -> 1 create (first 100) + 2 append batches (100 + 50).
    h.fetch
      .mockResolvedValueOnce(ok({ id: 'page-xyz', url: 'https://notion.so/page-xyz' }))
      .mockResolvedValueOnce(ok({}))
      .mockResolvedValueOnce(ok({}))

    await exportToNotion('tok', 'parent', mems(250))

    expect(h.fetch).toHaveBeenCalledTimes(3)

    const create = h.fetch.mock.calls[0]
    expect(create[0]).toBe('https://api.notion.com/v1/pages')
    expect(JSON.parse(create[1].body).children).toHaveLength(100)

    const append1 = h.fetch.mock.calls[1]
    expect(append1[0]).toBe('https://api.notion.com/v1/blocks/page-xyz/children')
    expect(append1[1].method).toBe('PATCH')
    expect(JSON.parse(append1[1].body).children).toHaveLength(100)

    const append2 = h.fetch.mock.calls[2]
    expect(append2[0]).toBe('https://api.notion.com/v1/blocks/page-xyz/children')
    expect(JSON.parse(append2[1].body).children).toHaveLength(50)
  })

  it('falls back to a notion.so URL from the page id when the response omits url', async () => {
    h.fetch.mockResolvedValueOnce(ok({ id: 'abc-def-123' }))
    const url = await exportToNotion('tok', 'parent', mems(1))
    expect(url).toBe('https://notion.so/abcdef123')
  })

  it('throws with status + body when the create call is not ok', async () => {
    h.fetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      text: async () => 'unauthorized'
    })
    await expect(exportToNotion('bad', 'parent', mems(1))).rejects.toThrow(
      /Notion create failed \(401\): unauthorized/
    )
  })

  it('throws with status + body when an append call is not ok', async () => {
    h.fetch
      .mockResolvedValueOnce(ok({ id: 'page-1', url: 'https://notion.so/page-1' }))
      .mockResolvedValueOnce({ ok: false, status: 400, text: async () => 'bad request' })
    await expect(exportToNotion('tok', 'parent', mems(150))).rejects.toThrow(
      /Notion append failed \(400\): bad request/
    )
  })
})
