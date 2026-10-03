import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({ fetch: vi.fn() }))
vi.mock('electron', () => ({ net: { fetch: h.fetch } }))

import { embedBatch, embedOne } from './embeddingClient'
import { EMBED_DIM, EMBED_MODEL } from './embedVector'
import { geminiClientPlatform } from '../../shared/geminiProxy'

const session = (): { desktopApiBase: string; token: string } => ({
  desktopApiBase: 'd',
  token: 't'
})

const ok = (values: number[] = new Array(EMBED_DIM).fill(0.5)): unknown => ({
  ok: true,
  json: async () => ({ embedding: { values } })
})

beforeEach(() => vi.clearAllMocks())

describe('embeddingClient — attribution transport', () => {
  it('emits the bounded attribution headers on the proxy request', async () => {
    h.fetch.mockResolvedValueOnce(ok())
    const vec = await embedOne(session(), 'hello', 'RETRIEVAL_QUERY')
    expect(vec).toHaveLength(EMBED_DIM)

    const [url, init] = h.fetch.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`d/v1/proxy/gemini/models/${EMBED_MODEL}:embedContent`)
    expect(init.method).toBe('POST')
    expect(init.headers).toMatchObject({
      'Content-Type': 'application/json',
      Authorization: 'Bearer t',
      'X-Omi-Lane': 'embedding',
      'X-Omi-Workload': 'maintenance'
    })
    expect((init.headers as Record<string, string>)['X-Omi-Client-Platform']).toBe(
      geminiClientPlatform(process.platform)
    )
    const body = JSON.parse(init.body as string)
    expect(body.model).toBe(`models/${EMBED_MODEL}`)
    expect(body.taskType).toBe('RETRIEVAL_QUERY')
  })

  it('batch embeds carry the same bounded attribution headers', async () => {
    h.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ embeddings: [{ values: new Array(EMBED_DIM).fill(0.25) }] })
    })
    const [vec] = await embedBatch(session(), ['doc text'], 'RETRIEVAL_DOCUMENT')
    expect(vec).toHaveLength(EMBED_DIM)

    const [url, init] = h.fetch.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`d/v1/proxy/gemini/models/${EMBED_MODEL}:batchEmbedContents`)
    expect(init.headers).toMatchObject({
      'X-Omi-Lane': 'embedding',
      'X-Omi-Workload': 'maintenance'
    })
    const body = JSON.parse(init.body as string)
    expect(body.requests).toHaveLength(1)
    expect(body.requests[0].model).toBe(`models/${EMBED_MODEL}`)
  })
})
