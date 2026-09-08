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

  it('keeps regional Portuguese distinct from generic Portuguese (#7461)', () => {
    expect(resolveLanguageCode('pt-BR')).toBe('pt-BR')
    expect(resolveLanguageCode('Portuguese (Brazil)')).toBe('pt-BR')
    expect(resolveLanguageCode('Brazilian Portuguese')).toBe('pt-BR')
    expect(resolveLanguageCode('português do Brasil')).toBe('pt-BR')
    expect(resolveLanguageCode('European Portuguese')).toBe('pt-PT')
    expect(resolveLanguageCode('Portuguese')).toBe('pt')
  })

  it('returns the canonical casing of a region-qualified code', () => {
    expect(resolveLanguageCode('pt-br')).toBe('pt-BR')
    expect(resolveLanguageCode('  PT-PT ')).toBe('pt-PT')
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

  // The voice system instruction interpolates these labels, so a stored 'pt-BR'
  // used to reach the model as the raw code instead of a language name (#7461).
  it('labels region-qualified codes regardless of casing', () => {
    expect(languageLabel('pt-BR')).toBe('Portuguese (Brazil)')
    expect(languageLabel('pt-pt')).toBe('Portuguese (Portugal)')
  })
})
