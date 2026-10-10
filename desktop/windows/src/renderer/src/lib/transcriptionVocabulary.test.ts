import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }))
vi.mock('./apiClient', () => ({ omiApi: api }))
const ptt = vi.hoisted(() => ({ setUserVocabulary: vi.fn() }))
vi.mock('./ptt/userVocabulary', () => ptt)

import {
  MAX_VOCABULARY_TERMS,
  fetchVocabulary,
  normalizeVocabulary,
  parseVocabularyInput,
  saveVocabulary
} from './transcriptionVocabulary'

beforeEach(() => {
  api.get.mockReset()
  api.patch.mockReset()
  ptt.setUserVocabulary.mockReset()
})

describe('normalizeVocabulary', () => {
  it('trims, collapses spaces, drops empties, and de-duplicates case-insensitively', () => {
    expect(normalizeVocabulary(['  Omi ', 'omi', '', 'Open  AI', 'Callie', 'OMI'])).toEqual([
      'Omi',
      'Open AI',
      'Callie'
    ])
  })

  it('caps the list at the backend limit but keeps long terms (the backend has no length cap)', () => {
    const many = Array.from({ length: 150 }, (_, i) => `term${i}`)
    expect(normalizeVocabulary(many)).toHaveLength(MAX_VOCABULARY_TERMS)
    const long = 'x'.repeat(120)
    expect(normalizeVocabulary([long, 'ok'])).toEqual([long, 'ok'])
  })

  it('de-duplicates without the OS locale (same keys as the PTT keyword path)', () => {
    const localeLower = vi.spyOn(String.prototype, 'toLocaleLowerCase')
    expect(normalizeVocabulary(['IBM', 'ibm', 'Istanbul'])).toEqual(['IBM', 'Istanbul'])
    expect(localeLower).not.toHaveBeenCalled()
    localeLower.mockRestore()
  })
})

describe('parseVocabularyInput', () => {
  it('splits a pasted comma list into terms', () => {
    expect(normalizeVocabulary(parseVocabularyInput('Omi, Callie,OpenAI,'))).toEqual([
      'Omi',
      'Callie',
      'OpenAI'
    ])
  })
})

describe('fetch/save', () => {
  it('reads the saved vocabulary and ignores malformed entries', async () => {
    api.get.mockResolvedValue({ data: { vocabulary: ['Omi', 3, 'Callie'] } })
    await expect(fetchVocabulary()).resolves.toEqual(['Omi', 'Callie'])
    expect(api.get).toHaveBeenCalledWith('/v1/users/transcription-preferences')
  })

  it('treats a missing vocabulary as empty', async () => {
    api.get.mockResolvedValue({ data: {} })
    await expect(fetchVocabulary()).resolves.toEqual([])
  })

  it('saves only the vocabulary field, normalized', async () => {
    api.patch.mockResolvedValue({})
    await saveVocabulary(['Omi', 'omi', ' Callie '])
    expect(api.patch).toHaveBeenCalledWith('/v1/users/transcription-preferences', {
      vocabulary: ['Omi', 'Callie']
    })
  })

  it('hands the saved list to the PTT keyword cache only after the backend accepted it', async () => {
    api.patch.mockResolvedValue({})
    await saveVocabulary(['Omi', 'Callie'])
    expect(ptt.setUserVocabulary).toHaveBeenCalledWith(['Omi', 'Callie'])

    api.patch.mockRejectedValue(new Error('500'))
    ptt.setUserVocabulary.mockReset()
    await expect(saveVocabulary(['Omi'])).rejects.toThrow('500')
    expect(ptt.setUserVocabulary).not.toHaveBeenCalled()
  })
})
