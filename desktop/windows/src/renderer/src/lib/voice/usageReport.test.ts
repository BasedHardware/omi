import { describe, it, expect, vi } from 'vitest'

vi.mock('../apiClient', () => ({
  desktopApi: { post: vi.fn() }
}))

import { mapOpenAiUsage, mapGeminiUsage, usageDelta, usageTotal } from './usageReport'

describe('mapOpenAiUsage', () => {
  it('splits audio vs text from the details arrays', () => {
    const body = mapOpenAiUsage(
      {
        inputTokens: 100,
        outputTokens: 60,
        inputTokensDetails: [{ audio_tokens: 70, text_tokens: 30, cached_tokens: 10 }],
        outputTokensDetails: [{ audio_tokens: 50, text_tokens: 10 }]
      },
      'gpt-realtime-2'
    )
    expect(body).toEqual({
      provider: 'openai',
      model: 'gpt-realtime-2',
      input_text_tokens: 30,
      input_audio_tokens: 70,
      input_cached_tokens: 10,
      output_text_tokens: 10,
      output_audio_tokens: 50
    })
  })

  it('tolerates missing details and clamps audio to the total', () => {
    const body = mapOpenAiUsage({ inputTokens: 5, outputTokens: 0 }, 'm')
    expect(body.input_text_tokens).toBe(5)
    expect(body.input_audio_tokens).toBe(0)
    const clamped = mapOpenAiUsage(
      { inputTokens: 5, inputTokensDetails: [{ audio_tokens: 999 }] },
      'm'
    )
    expect(clamped.input_audio_tokens).toBe(5)
    expect(clamped.input_text_tokens).toBe(0)
  })

  it('sums multiple detail entries', () => {
    const body = mapOpenAiUsage(
      {
        inputTokens: 20,
        inputTokensDetails: [{ audio_tokens: 5 }, { audio_tokens: 7, cached_tokens: 2 }]
      },
      'm'
    )
    expect(body.input_audio_tokens).toBe(12)
    expect(body.input_cached_tokens).toBe(2)
  })
})

describe('mapGeminiUsage', () => {
  it('splits by modality breakdown', () => {
    const body = mapGeminiUsage(
      {
        promptTokenCount: 80,
        responseTokenCount: 40,
        cachedContentTokenCount: 3,
        promptTokensDetails: [
          { modality: 'AUDIO', tokenCount: 60 },
          { modality: 'TEXT', tokenCount: 20 }
        ],
        responseTokensDetails: [{ modality: 'AUDIO', tokenCount: 40 }]
      },
      'models/gemini-3.1-flash-live-preview'
    )
    expect(body).toEqual({
      provider: 'gemini',
      model: 'models/gemini-3.1-flash-live-preview',
      input_text_tokens: 20,
      input_audio_tokens: 60,
      input_cached_tokens: 3,
      output_text_tokens: 0,
      output_audio_tokens: 40
    })
  })

  it('tolerates an empty metadata object', () => {
    const body = mapGeminiUsage({}, 'm')
    expect(usageTotal(body)).toBe(0)
  })
})

describe('usageDelta', () => {
  const base = {
    provider: 'openai' as const,
    model: 'm',
    input_text_tokens: 10,
    input_audio_tokens: 20,
    input_cached_tokens: 5,
    output_text_tokens: 8,
    output_audio_tokens: 30
  }

  it('returns the cumulative value when there is no previous report', () => {
    expect(usageDelta(base, null)).toEqual(base)
  })

  it('subtracts the previous cumulative report field-wise, flooring at 0', () => {
    const next = { ...base, input_audio_tokens: 50, output_audio_tokens: 25 }
    const d = usageDelta(next, base)
    expect(d.input_audio_tokens).toBe(30)
    expect(d.output_audio_tokens).toBe(0) // never negative
    expect(d.input_text_tokens).toBe(0)
  })
})
