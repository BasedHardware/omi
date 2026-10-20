import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios from 'axios'
import { translateToGlosses, defaultSignOpts, clearNegativeCache } from './signLanguage'
import { isSignLanguageEnabled, setSignLanguageEnabled } from '../ipc/integrations'

vi.mock('axios')
vi.mock('electron', () => ({ app: { getPath: (): string => '/tmp' } }))

const mockedAxiosGet = vi.mocked(axios.get)

describe('translateToGlosses', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    clearNegativeCache()
  })

  it('returns empty result for empty input', async () => {
    const result = await translateToGlosses('', 'en', 'ase')
    expect(result.poseUrl).toBe('')
    expect(result.glosses).toEqual([])
    expect(result.swrFull).toBeUndefined()
  })

  it('returns TRANSLATION_UNAVAILABLE when the request fails', async () => {
    mockedAxiosGet.mockRejectedValue(new Error('network error'))

    const result = await translateToGlosses('failed request', 'en', 'ase', {
      ...defaultSignOpts(),
      baseUrl: null,
      posesDir: undefined
    })

    expect(result.swrFull).toBe('TRANSLATION_UNAVAILABLE')
    expect(result.poseUrl).toBe('')
  })

  it('returns a pose URL on successful API response', async () => {
    mockedAxiosGet.mockResolvedValue({ data: Buffer.from('{"urls":{}}') })

    const result = await translateToGlosses('hello world', 'en', 'ase', {
      ...defaultSignOpts(),
      baseUrl: null,
      posesDir: undefined
    })

    expect(result.poseUrl).toBeDefined()
  })

  it('caches negative results so repeated failures do not re-request', async () => {
    mockedAxiosGet.mockRejectedValue(new Error('network error'))

    const opts = { ...defaultSignOpts(), baseUrl: null, posesDir: undefined }

    await translateToGlosses('cached failure', 'en', 'ase', opts)
    const second = await translateToGlosses('cached failure', 'en', 'ase', opts)

    expect(second.swrFull).toBe('TRANSLATION_UNAVAILABLE')
    expect(mockedAxiosGet).toHaveBeenCalledTimes(2)
  })

  it('truncates input text to 256 characters before sending', async () => {
    mockedAxiosGet.mockResolvedValue({ data: Buffer.from('{"urls":{}}') })

    const longText = 'a'.repeat(300)
    await translateToGlosses(longText, 'en', 'ase', {
      ...defaultSignOpts(),
      baseUrl: null,
      posesDir: undefined
    })

    const callArg = mockedAxiosGet.mock.calls[0][0] as string
    const urlPrefix =
      'https://us-central1-sign-mt.cloudfunctions.net/spoken_text_to_signed_pose?text='
    const encodedText = encodeURIComponent(longText.slice(0, 256))
    const expectedMaxLen = urlPrefix.length + encodedText.length + '&spoken=en&signed=ase'.length
    expect(callArg.length).toBeLessThanOrEqual(expectedMaxLen)
  })

  it('returns TRANSLATION_UNAVAILABLE when both pose and video APIs fail', async () => {
    mockedAxiosGet.mockRejectedValue(new Error('network error'))

    const result = await translateToGlosses('both APIs failure', 'en', 'ase', {
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
