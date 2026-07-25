// The gate that stands between a captured frame and a cloud vision model.
import { describe, expect, it } from 'vitest'
import { mayAnalyzeFrame } from './privacy'

const frame = (
  app: string,
  windowTitle: string,
  processName = app.toLowerCase()
): { app: string; windowTitle: string; processName: string } => ({ app, windowTitle, processName })

describe('mayAnalyzeFrame', () => {
  it('allows an ordinary work frame', () => {
    expect(mayAnalyzeFrame(frame('Visual Studio Code', 'index.ts — omi', 'code'))).toBe(true)
  })

  it('blocks private / incognito browsing windows', () => {
    expect(mayAnalyzeFrame(frame('Google Chrome', 'Search — Incognito', 'chrome'))).toBe(false)
    expect(mayAnalyzeFrame(frame('Microsoft Edge', 'News — InPrivate', 'msedge'))).toBe(false)
    expect(mayAnalyzeFrame(frame('Firefox', 'Private Browsing', 'firefox'))).toBe(false)
  })

  it('blocks password managers by app name', () => {
    expect(mayAnalyzeFrame(frame('1Password', 'Vault', 'agilebits'))).toBe(false)
    expect(mayAnalyzeFrame(frame('Bitwarden', 'Vault', 'bitwarden'))).toBe(false)
  })

  it('blocks banking and login pages by window title', () => {
    expect(mayAnalyzeFrame(frame('Google Chrome', 'Chase — Account summary', 'chrome'))).toBe(false)
    expect(mayAnalyzeFrame(frame('Google Chrome', 'Sign in — Okta', 'chrome'))).toBe(false)
  })

  it('blocks on the process name too (an app that renames its window)', () => {
    expect(mayAnalyzeFrame(frame('App', 'Untitled', 'keepass'))).toBe(false)
  })
})
