import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios from 'axios'
import { translateToGlosses, defaultSignOpts } from './signLanguage'
import { isSignLanguageEnabled, setSignLanguageEnabled } from '../integrations'

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

  it('caches negative results so repeated failures do not re-request', async () => {
    mockedAxios.get.mockRejectedValue(new Error('network error'))

    const opts = { ...defaultSignOpts(), baseUrl: null, posesDir: undefined }

    await translateToGlosses('hello world', 'en', 'ase', opts)
    const second = await translateToGlosses('hello world', 'en', 'ase', opts)

    expect(second.swrFull).toBe('TRANSLATION_UNAVAILABLE')
    expect(mockedAxios.get).toHaveBeenCalledTimes(1)
  })

  it('truncates input text to 256 characters before sending', async () => {
    mockedAxios.get.mockResolvedValue({ data: Buffer.from('{"urls":{}}') })

    const longText = 'a'.repeat(300)
    await translateToGlosses(longText, 'en', 'ase', {
      ...defaultSignOpts(),
      baseUrl: null,
      posesDir: undefined
    })

    const callArg = mockedAxios.get.mock.calls[0][0] as string
    expect(callArg.length).toBeLessThanOrEqual(256 + 'https://us-central1-sign-mt.cloudfunctions.net/spoken_text_to_signed_pose?text='.length)
  })

  it('returns TRANSLATION_UNAVAILABLE when both pose and video APIs fail', async () => {
    mockedAxios.get.mockRejectedValue(new Error('network error'))

    const result = await translateToGlosses('hello world', 'en', 'ase', {
      ...defaultSignOpts(),
      baseUrl: null,
      posesDir: undefined
    })

    expect(result.swrFull).toBe('TRANSLATION_UNAVAILABLE')
    expect(result.poseUrl).toBe('')
  })
})

describe('sign-language opt-in gating', () => {
  beforeEach(() => {
    setSignLanguageEnabled(false)
  })

  it('is disabled by default', () => {
    expect(isSignLanguageEnabled()).toBe(false)
  })

  it('can be enabled by setSignLanguageEnabled', () => {
    setSignLanguageEnabled(true)
    expect(isSignLanguageEnabled()).toBe(true)
  })
})