import { describe, expect, it, vi } from 'vitest'
import { buildByokChatRequest, sendByokChat } from './chat'

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body
  } as Response
}

describe('BYOK chat', () => {
  it('constructs direct OpenAI requests without sending traffic to Omi billing endpoints', () => {
    const request = buildByokChatRequest('openai', 'sk-openai-secret', [
      { role: 'user', content: 'hello' }
    ])

    expect(request.url).toBe('https://api.openai.com/v1/chat/completions')
    expect(request.url).not.toContain('omi')
    expect(request.init.headers).toMatchObject({
      authorization: 'Bearer sk-openai-secret'
    })
    expect(String(request.init.body)).not.toContain('sk-openai-secret')
  })

  it('constructs direct OpenRouter requests with OpenAI-compatible payloads', () => {
    const request = buildByokChatRequest('openrouter', 'sk-or-secret', [
      { role: 'user', content: 'hello' }
    ])

    expect(request.url).toBe('https://openrouter.ai/api/v1/chat/completions')
    expect(request.init.headers).toMatchObject({
      authorization: 'Bearer sk-or-secret',
      'HTTP-Referer': 'https://omi.me',
      'X-Title': 'Omi Windows'
    })
    expect(String(request.init.body)).toContain('openrouter/auto')
    expect(String(request.init.body)).not.toContain('sk-or-secret')
  })

  it('constructs direct Anthropic and Gemini requests with provider-owned credentials', () => {
    const anthropic = buildByokChatRequest('anthropic', 'sk-ant-secret', [
      { role: 'user', content: 'hello' }
    ])
    expect(anthropic.url).toBe('https://api.anthropic.com/v1/messages')
    expect(anthropic.init.headers).toMatchObject({
      'x-api-key': 'sk-ant-secret'
    })
    expect(String(anthropic.init.body)).not.toContain('sk-ant-secret')

    const gemini = buildByokChatRequest('gemini', 'AIzaSecretKey', [
      { role: 'user', content: 'hello' }
    ])
    expect(gemini.url).toBe(
      'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent'
    )
    expect(gemini.url).not.toContain('AIzaSecretKey')
    expect(gemini.init.headers).toMatchObject({
      'x-goog-api-key': 'AIzaSecretKey'
    })
    expect(String(gemini.init.body)).not.toContain('AIzaSecretKey')
  })

  it('uses the selected provider key to fetch and parse an OpenAI chat response', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse({
        choices: [{ message: { content: 'BYOK response' } }],
        usage: { prompt_tokens: 4, completion_tokens: 2, total_tokens: 6 }
      })
    )

    const result = await sendByokChat(
      'openai',
      'sk-openai-secret',
      [{ role: 'user', content: 'hello' }],
      undefined,
      { fetchImpl }
    )

    expect(fetchImpl).toHaveBeenCalledWith(
      'https://api.openai.com/v1/chat/completions',
      expect.objectContaining({
        headers: expect.objectContaining({ authorization: 'Bearer sk-openai-secret' })
      })
    )
    expect(result).toEqual({
      provider: 'openai',
      text: 'BYOK response',
      usage: { promptTokens: 4, completionTokens: 2, totalTokens: 6 }
    })
  })

  it('parses Anthropic and Gemini text response shapes', async () => {
    await expect(
      sendByokChat('anthropic', 'sk-ant-secret', [{ role: 'user', content: 'hello' }], undefined, {
        fetchImpl: vi.fn().mockResolvedValue(
          jsonResponse({
            content: [{ type: 'text', text: 'Claude response' }],
            usage: { input_tokens: 5, output_tokens: 3 }
          })
        )
      })
    ).resolves.toMatchObject({
      provider: 'anthropic',
      text: 'Claude response',
      usage: { promptTokens: 5, completionTokens: 3, totalTokens: 8 }
    })

    await expect(
      sendByokChat('gemini', 'AIzaSecretKey', [{ role: 'user', content: 'hello' }], undefined, {
        fetchImpl: vi.fn().mockResolvedValue(
          jsonResponse({
            candidates: [{ content: { parts: [{ text: 'Gemini response' }] } }],
            usageMetadata: {
              promptTokenCount: 6,
              candidatesTokenCount: 4,
              totalTokenCount: 10
            }
          })
        )
      })
    ).resolves.toMatchObject({
      provider: 'gemini',
      text: 'Gemini response',
      usage: { promptTokens: 6, completionTokens: 4, totalTokens: 10 }
    })
  })
})
