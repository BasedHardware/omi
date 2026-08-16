import { describe, it, expect, vi } from 'vitest'
import { createLaneClient, LaneError, type LaneRequest } from './laneClient'

const request = (over: Partial<LaneRequest> = {}): LaneRequest => ({
  operation: 'proactive_reasoning',
  prompt: 'stable',
  uncachedPrompt: 'volatile',
  jsonSchema: { type: 'object' },
  cacheKey: 'director:v1',
  maxCompletionTokens: 800,
  ...over
})

const envelope = (content = '{"decision":"silence"}') => ({
  operation: 'proactive_reasoning',
  lane: 'omi:auto:desktop-proactive-reasoning',
  provider_model: 'gpt-5.6-luna',
  usage: { cached_tokens: 100, cache_write_tokens: 0 },
  cache_write: false,
  fallback_class: 'none',
  response: { choices: [{ message: { content } }] }
})

function jsonResponse(
  status: number,
  body: unknown,
  headers: Record<string, string> = {}
): Response {
  return new Response(JSON.stringify(body), { status, headers })
}

const session = () => ({ desktopApiBase: 'https://desktop.example', token: 'tok' })

describe('createLaneClient', () => {
  it('posts the exact body shape and parses the envelope', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, envelope()))
    const client = createLaneClient({ fetchImpl, getSession: session })
    const result = await client.complete(request({ imageBase64Jpeg: 'AAAA' }))

    expect(result.content).toBe('{"decision":"silence"}')
    expect(result.providerModel).toBe('gpt-5.6-luna')
    expect(result.cachedTokens).toBe(100)

    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('https://desktop.example/v1/desktop/proactivity/completions')
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok')
    const body = JSON.parse(init.body as string)
    expect(body.operation).toBe('proactive_reasoning')
    expect(body.cache_key).toBe('director:v1')
    expect(body.max_completion_tokens).toBe(800)
    expect(body.response_format).toEqual({
      type: 'json_schema',
      json_schema: { name: 'desktop_proactivity', strict: true, schema: { type: 'object' } }
    })
    expect(body.messages[0].content).toEqual([
      { type: 'text', text: 'stable' },
      { type: 'text', text: 'volatile' },
      { type: 'image_url', image_url: { url: 'data:image/jpeg;base64,AAAA' } }
    ])
    // No temperature is ever sent on this path.
    expect('temperature' in body).toBe(false)
  })

  it('omits the volatile part and image when absent', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, envelope()))
    const client = createLaneClient({ fetchImpl, getSession: session })
    await client.complete(request({ uncachedPrompt: undefined, cacheKey: undefined }))
    const body = JSON.parse(
      (fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1].body as string
    )
    expect(body.messages[0].content).toEqual([{ type: 'text', text: 'stable' }])
    expect('cache_key' in body).toBe(false)
  })

  it('arms a clamped per-operation cooldown on 429 and throws before the network while cooling', async () => {
    let nowMs = 1_000_000
    const fetchImpl = vi.fn(async () => jsonResponse(429, {}, { 'Retry-After': '10' }))
    const client = createLaneClient({ fetchImpl, getSession: session, now: () => nowMs })

    await expect(client.complete(request())).rejects.toMatchObject({
      kind: 'quota_cooldown',
      status: 429
    })
    // Retry-After 10s clamps up to the 60s minimum.
    expect(client.cooldownRemainingMs('proactive_reasoning')).toBe(60_000)

    await expect(client.complete(request())).rejects.toMatchObject({ kind: 'quota_cooldown' })
    expect(fetchImpl).toHaveBeenCalledTimes(1)

    // The other operation is unaffected; time passing clears the cooldown.
    expect(client.cooldownRemainingMs('proactive_extraction')).toBe(0)
    nowMs += 61_000
    fetchImpl.mockResolvedValueOnce(jsonResponse(200, envelope()))
    await expect(client.complete(request())).resolves.toBeTruthy()
  })

  it('keeps a longer existing cooldown and honors large Retry-After up to the hour cap', async () => {
    let nowMs = 0
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(429, {}, { 'Retry-After': '7200' }))
    const client = createLaneClient({ fetchImpl, getSession: session, now: () => nowMs })
    await expect(client.complete(request())).rejects.toBeInstanceOf(LaneError)
    expect(client.cooldownRemainingMs('proactive_reasoning')).toBe(3_600_000)
    nowMs = 10
    expect(client.cooldownRemainingMs('proactive_reasoning')).toBe(3_599_990)
  })

  it('classifies http errors, decode failures, invalid envelopes, and missing sessions', async () => {
    const client = (impl: () => Promise<Response>, hasSession = true) =>
      createLaneClient({ fetchImpl: impl, getSession: hasSession ? session : () => null })

    await expect(
      client(async () => jsonResponse(500, {})).complete(request())
    ).rejects.toMatchObject({
      kind: 'http_error',
      status: 500
    })
    await expect(
      client(async () => new Response('not json', { status: 200 })).complete(request())
    ).rejects.toMatchObject({ kind: 'decode' })
    await expect(
      client(async () => jsonResponse(200, { operation: 'x' })).complete(request())
    ).rejects.toMatchObject({ kind: 'invalid_response' })
    await expect(
      client(async () => jsonResponse(200, envelope()), false).complete(request())
    ).rejects.toMatchObject({
      kind: 'network'
    })

    const err = new LaneError('http_error', 'lane returned 500', 500)
    expect(err.provenance()).toEqual({ failure: 'http_error', status: 500 })
  })

  it('reset clears cooldowns (owner change)', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(429, {}, {}))
    const client = createLaneClient({ fetchImpl, getSession: session, now: () => 0 })
    await expect(client.complete(request())).rejects.toBeInstanceOf(LaneError)
    expect(client.cooldownRemainingMs('proactive_reasoning')).toBeGreaterThan(0)
    client.reset()
    expect(client.cooldownRemainingMs('proactive_reasoning')).toBe(0)
  })
})
