import { describe, expect, it, vi } from 'vitest'
import { buildByokValidationRequest, validateByokKey } from './validation'

function response(status: number): Response {
  return {
    ok: status >= 200 && status < 300,
    status
  } as Response
}

describe('BYOK validation', () => {
  it('constructs provider-specific validation requests', () => {
    expect(buildByokValidationRequest('openai', 'sk-openai-secret').url).toBe(
      'https://api.openai.com/v1/models'
    )
    expect(buildByokValidationRequest('openai', 'sk-openai-secret').init.headers).toMatchObject({
      authorization: 'Bearer sk-openai-secret'
    })

    expect(buildByokValidationRequest('anthropic', 'sk-ant-secret').init.headers).toMatchObject({
      'anthropic-version': '2023-06-01',
      'x-api-key': 'sk-ant-secret'
    })

    const gemini = buildByokValidationRequest('gemini', 'AIza secret')
    expect(gemini.url).toBe('https://generativelanguage.googleapis.com/v1beta/models')
    expect(gemini.url).not.toContain('AIza secret')
    expect(gemini.init.headers).toMatchObject({
      'x-goog-api-key': 'AIza secret'
    })

    expect(buildByokValidationRequest('deepgram', 'dg-secret').init.headers).toMatchObject({
      authorization: 'Token dg-secret'
    })

    expect(buildByokValidationRequest('openrouter', 'sk-or-secret').url).toBe(
      'https://openrouter.ai/api/v1/key'
    )
    expect(buildByokValidationRequest('openrouter', 'sk-or-secret').init.headers).toMatchObject({
      authorization: 'Bearer sk-or-secret'
    })

    expect(buildByokValidationRequest('elevenlabs', 'sk_eleven-secret').url).toBe(
      'https://api.elevenlabs.io/v1/models'
    )
    expect(buildByokValidationRequest('elevenlabs', 'sk_eleven-secret').init.headers).toMatchObject(
      {
        'xi-api-key': 'sk_eleven-secret'
      }
    )
  })

  it('rejects obvious format mismatches before network use', async () => {
    const fetchImpl = vi.fn()

    await expect(
      validateByokKey('openai', 'not-an-openai-key', { fetchImpl })
    ).resolves.toMatchObject({
      ok: false,
      error: 'OpenAI keys should start with sk-'
    })

    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it('returns a generic provider rejection without reading response bodies', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response(401))

    await expect(
      validateByokKey('anthropic', 'sk-ant-secret-1234567890', { fetchImpl })
    ).resolves.toEqual({
      ok: false,
      status: 401,
      error: 'Provider rejected the key'
    })
  })

  it('accepts successful provider validation', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response(200))

    await expect(
      validateByokKey('deepgram', 'deepgram_secret_token_1234567890', { fetchImpl })
    ).resolves.toEqual({
      ok: true,
      status: 200
    })
    expect(fetchImpl).toHaveBeenCalledWith(
      'https://api.deepgram.com/v1/projects',
      expect.objectContaining({
        signal: expect.any(AbortSignal)
      })
    )
  })
})
