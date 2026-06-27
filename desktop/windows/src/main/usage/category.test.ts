import { describe, it, expect } from 'vitest'
import { categorize } from './category'

describe('categorize', () => {
  it('maps known browsers', () => {
    expect(categorize('chrome.exe')).toBe('browser')
    expect(categorize('msedge.exe')).toBe('browser')
    expect(categorize('firefox.exe')).toBe('browser')
  })
  it('maps editors and comms', () => {
    expect(categorize('Code.exe')).toBe('editor')
    expect(categorize('devenv.exe')).toBe('editor')
    expect(categorize('slack.exe')).toBe('comms')
    expect(categorize('Discord.exe')).toBe('comms')
  })
  it('maps media', () => {
    expect(categorize('spotify.exe')).toBe('media')
    expect(categorize('vlc.exe')).toBe('media')
  })
  it('is case-insensitive and defaults to other', () => {
    expect(categorize('CHROME.EXE')).toBe('browser')
    expect(categorize('some-random-tool.exe')).toBe('other')
    expect(categorize('')).toBe('other')
  })
})
