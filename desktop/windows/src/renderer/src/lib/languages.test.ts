import { describe, it, expect } from 'vitest'
import {
  resolveLanguageCode,
  languageLabel,
  DEFAULT_LANGUAGE,
  FALLBACK_LANGUAGE
} from './languages'

describe('resolveLanguageCode', () => {
  it('passes through known ISO codes', () => {
    expect(resolveLanguageCode('en')).toBe('en')
    expect(resolveLanguageCode('es')).toBe('es')
    expect(resolveLanguageCode('multi')).toBe('multi')
  })

  it('normalizes case and whitespace on codes', () => {
    expect(resolveLanguageCode('  ES  ')).toBe('es')
    expect(resolveLanguageCode('EN')).toBe('en')
  })

  it('maps English language names (labels) to codes', () => {
    expect(resolveLanguageCode('Spanish')).toBe('es')
    expect(resolveLanguageCode('portuguese')).toBe('pt')
    expect(resolveLanguageCode('Japanese')).toBe('ja')
    expect(resolveLanguageCode('CHINESE')).toBe('zh')
  })

  it('maps common autonyms and alternate spellings', () => {
    expect(resolveLanguageCode('español')).toBe('es')
    expect(resolveLanguageCode('espanol')).toBe('es')
    expect(resolveLanguageCode('Deutsch')).toBe('de')
    expect(resolveLanguageCode('français')).toBe('fr')
    expect(resolveLanguageCode('mandarin')).toBe('zh')
  })

  it('maps non-Latin script names', () => {
    expect(resolveLanguageCode('日本語')).toBe('ja')
    expect(resolveLanguageCode('한국어')).toBe('ko')
    expect(resolveLanguageCode('русский')).toBe('ru')
  })

  it('falls back to the default for empty input', () => {
    expect(resolveLanguageCode('')).toBe(DEFAULT_LANGUAGE)
    expect(resolveLanguageCode('   ')).toBe(DEFAULT_LANGUAGE)
  })

  it('falls back to multilingual for unrecognized input', () => {
    expect(resolveLanguageCode('Klingon')).toBe(FALLBACK_LANGUAGE)
    expect(resolveLanguageCode('asdf123')).toBe(FALLBACK_LANGUAGE)
  })
})

describe('languageLabel', () => {
  it('returns the label for a known code', () => {
    expect(languageLabel('es')).toBe('Spanish')
    expect(languageLabel('multi')).toBe('Other / Multilingual')
  })

  it('returns the code itself for an unknown code', () => {
    expect(languageLabel('xx')).toBe('xx')
  })
})
