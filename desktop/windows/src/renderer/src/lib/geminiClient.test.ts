import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  auth: { currentUser: null as null | { getIdToken(): Promise<string> } },
  fetch: vi.fn()
}))

vi.mock('./firebase', () => ({ auth: h.auth }))

import { generate } from './geminiClient'
import { GeminiLane } from '../../../shared/geminiAttribution'

const g = globalThis as { window?: { electron?: { process?: { platform?: string } } } }

function okJson(text = 'hello'): Response {
  return {
    ok: true,
    status: 200,
    json: async () => ({ candidates: [{ content: { parts: [{ text }] } }] })
  } as unknown as Response
}

beforeEach(() => {
  h.fetch.mockReset()
  h.auth.currentUser = { getIdToken: async () => 'firebase-token' }
  vi.stubGlobal('fetch', h.fetch)
  g.window = { electron: { process: { platform: 'win32' } } }
})

describe('renderer geminiClient — attribution transport', () => {
  it('sends the bounded attribution headers once on success', async () => {
    h.fetch.mockResolvedValueOnce(okJson('answer'))
    const text = await generate({
      model: 'gemini-2.5-flash',
      parts: [{ text: 'prompt' }],
      lane: GeminiLane.liveNotes,
      workload: 'extraction',
      systemPrompt: 'sys',
      thinkingBudget: 0
    })
    expect(text).toBe('answer')
    expect(h.fetch).toHaveBeenCalledTimes(1)
    const [url, init] = h.fetch.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/v1/proxy/gemini/models/gemini-2.5-flash:generateContent')
    expect(init.method).toBe('POST')
    expect(init.headers).toEqual({
      'Content-Type': 'application/json',
      Authorization: 'Bearer firebase-token',
      'X-Omi-Lane': 'live_notes',
      'X-Omi-Workload': 'extraction',
      'X-App-Platform': 'windows'
    })
    const body = JSON.parse(init.body as string)
    expect(body.contents).toEqual([{ role: 'user', parts: [{ text: 'prompt' }] }])
    expect(body.systemInstruction).toEqual({ parts: [{ text: 'sys' }] })
    expect(body.generationConfig).toEqual({ thinkingConfig: { thinkingBudget: 0 } })
  })

  it('maps a linux preload platform onto the wire value', async () => {
    g.window = { electron: { process: { platform: 'linux' } } }
    h.fetch.mockResolvedValueOnce(okJson())
    await generate({
      model: 'gemini-2.5-flash',
      parts: [{ text: 'p' }],
      lane: GeminiLane.screenSynthesis,
      workload: 'extraction'
    })
    const [, init] = h.fetch.mock.calls[0] as [string, RequestInit]
    expect((init.headers as Record<string, string>)['X-App-Platform']).toBe('linux')
  })

  it('degrades to unknown when the preload bridge is absent', async () => {
    g.window = {}
    h.fetch.mockResolvedValueOnce(okJson())
    await generate({
      model: 'gemini-2.5-flash',
      parts: [{ text: 'p' }],
      lane: GeminiLane.screenSynthesis,
      workload: 'extraction'
    })
    const [, init] = h.fetch.mock.calls[0] as [string, RequestInit]
    expect((init.headers as Record<string, string>)['X-App-Platform']).toBe('unknown')
  })
})
