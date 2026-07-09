import { describe, it, expect, vi } from 'vitest'
import { buildPersonaPrompt, cleanReply, generateReply, type ReplyContext } from './replyEngine'

const ctx: ReplyContext = {
  userDisplayName: 'Karthik',
  senderName: 'Alice',
  chatTitle: 'Alice',
  network: 'WhatsApp',
  transcript: [
    { sender: 'Alice', text: 'hey!', fromMe: false },
    { sender: 'Alice', text: 'long time', fromMe: true }
  ],
  incomingText: 'where are you working these days?'
}

describe('buildPersonaPrompt', () => {
  it('frames the reply as the user, includes the thread and the new message', () => {
    const prompt = buildPersonaPrompt(ctx)
    expect(prompt).toContain('AS Karthik')
    expect(prompt).toContain('Alice: hey!')
    expect(prompt).toContain('Karthik: long time') // fromMe lines use the user's name
    expect(prompt).toContain("Alice's new message: where are you working these days?")
    expect(prompt).toContain('never invent facts')
  })

  it('omits the transcript block when there is no history', () => {
    const prompt = buildPersonaPrompt({ ...ctx, transcript: [] })
    expect(prompt).not.toContain('Recent conversation:')
  })
})

describe('cleanReply', () => {
  it('trims and strips wrapping quotes', () => {
    expect(cleanReply('  "At Omi, building AI wearables!"  ')).toBe(
      'At Omi, building AI wearables!'
    )
    expect(cleanReply('no quotes')).toBe('no quotes')
    expect(cleanReply('"')).toBe('"') // lone quote isn't a wrapped reply
  })
})

describe('generateReply', () => {
  it('streams the SSE body into a cleaned reply', async () => {
    const sse = 'data: think: Searching memories\ndata: At Omi,\ndata:  building!\ndone: eyJ9\n'
    const fetchImpl = vi.fn().mockResolvedValue(new Response(sse, { status: 200 }))
    const r = await generateReply({ apiBase: 'https://api.test', firebaseToken: 't', ctx, fetchImpl })
    expect(r).toEqual({ ok: true, text: 'At Omi, building!' })

    const [url, init] = fetchImpl.mock.calls[0]
    expect(url).toBe('https://api.test/v2/messages')
    expect(init.headers.Authorization).toBe('Bearer t')
    expect(JSON.parse(init.body).text).toContain('AS Karthik')
  })

  it('maps 401 to unauthorized (token refresh signal) and errors to network', async () => {
    const unauthorized = vi.fn().mockResolvedValue(new Response('', { status: 401 }))
    expect(
      await generateReply({ apiBase: 'a', firebaseToken: 't', ctx, fetchImpl: unauthorized })
    ).toEqual({ ok: false, error: 'unauthorized' })

    const failing = vi.fn().mockRejectedValue(new Error('offline'))
    const r = await generateReply({ apiBase: 'a', firebaseToken: 't', ctx, fetchImpl: failing })
    expect(r).toEqual({ ok: false, error: 'network', detail: 'offline' })
  })

  it('reports empty when the stream contained no reply content', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(new Response('data: think: Working\ndone: x\n', { status: 200 }))
    const r = await generateReply({ apiBase: 'a', firebaseToken: 't', ctx, fetchImpl })
    expect(r).toEqual({ ok: false, error: 'empty' })
  })
})
