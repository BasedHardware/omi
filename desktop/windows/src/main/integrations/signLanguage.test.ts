import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios from 'axios'
import { translateToGlosses, defaultSignOpts } from './signLanguage'

vi.mock('axios')

const mockedAxios = vi.mocked(axios)

describe('translateToGlosses', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns empty result for empty input', async () => {
    const result = await translateToGlosses('', 'en', 'ase')
    expect(result.poseUrl).toBe('')
    expect(result.glosses).toEqual([])
    expect(result.swrFull).toBeUndefined()
  })

  it('returns TRANSLATION_UNAVAILABLE when the request fails', async () => {
    mockedAxios.get.mockRejectedValue(new Error('network error'))

    const result = await translateToGlosses('hello world', 'en', 'ase', {
      ...defaultSignOpts(),
      baseUrl: null,
      posesDir: undefined
    })

    expect(result.swrFull).toBe('TRANSLATION_UNAVAILABLE')
    expect(result.poseUrl).toBe('')
  })

  it('returns a pose URL on successful API response', async () => {
    mockedAxios.get.mockResolvedValue({ data: Buffer.from('{"urls":{}}') })

    const result = await translateToGlosses('hello world', 'en', 'ase', {
      ...defaultSignOpts(),
      baseUrl: null,
      posesDir: undefined
    })

    expect(result.poseUrl).toBeDefined()
  })
})