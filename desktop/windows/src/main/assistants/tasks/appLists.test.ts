import { describe, expect, it } from 'vitest'
import { MESSAGING_APPS } from '../core/distributionGate'
import {
  ALLOWED_APPS,
  BROWSER_APPS,
  BROWSER_KEYWORDS,
  MESSAGING_APPS as REEXPORTED_MESSAGING_APPS,
  PROMPT_MESSAGING_APPS,
  isAppAllowed,
  isBrowserApp,
  isMessagingApp,
  isPromptMessagingApp,
  isWindowAllowed
} from './appLists'

describe('list shapes', () => {
  it('re-exports the shared MESSAGING_APPS constant (reused, not duplicated)', () => {
    expect(REEXPORTED_MESSAGING_APPS).toBe(MESSAGING_APPS)
  })

  it('has the ported list sizes (Mac Set:21–80, normalized)', () => {
    // 16 Mac allowed apps collapse to 15 after the two WhatsApp variants merge.
    expect(ALLOWED_APPS).toHaveLength(15)
    expect(BROWSER_APPS).toHaveLength(7)
    // 6 Mac reminder apps collapse to 5 after the WhatsApp variants merge.
    expect(PROMPT_MESSAGING_APPS).toHaveLength(5)
    expect(BROWSER_KEYWORDS.length).toBeGreaterThan(35)
  })

  it('every entry is lowercase (substring matching depends on it)', () => {
    for (const list of [ALLOWED_APPS, BROWSER_APPS, BROWSER_KEYWORDS, PROMPT_MESSAGING_APPS]) {
      for (const entry of list) expect(entry).toBe(entry.toLowerCase())
    }
  })
})

describe('isAppAllowed', () => {
  it('matches whitelisted apps by lowercased substring', () => {
    expect(isAppAllowed('Slack')).toBe(true)
    expect(isAppAllowed('Telegram')).toBe(true)
    expect(isAppAllowed('Notes')).toBe(true)
    expect(isAppAllowed('Superhuman')).toBe(true)
  })

  it('resolves the normalized macOS-isms', () => {
    // zoom.us → zoom
    expect(isAppAllowed('zoom.us')).toBe(true)
    // Google Chrome / Microsoft Edge / Brave Browser → chrome / edge / brave
    expect(isAppAllowed('Google Chrome')).toBe(true)
    expect(isAppAllowed('Microsoft Edge')).toBe(true)
    expect(isAppAllowed('Brave Browser')).toBe(true)
    // Windows process-style names still resolve through the substring
    expect(isAppAllowed('chrome.exe')).toBe(true)
    // the hidden LTR-mark WhatsApp variant collapses to whatsapp
    expect(isAppAllowed('‎WhatsApp')).toBe(true)
  })

  it('rejects non-whitelisted apps', () => {
    expect(isAppAllowed('Terminal')).toBe(false)
    expect(isAppAllowed('Visual Studio Code')).toBe(false)
    expect(isAppAllowed('')).toBe(false)
  })
})

describe('isBrowserApp / isWindowAllowed', () => {
  it('non-browser apps always pass the window gate', () => {
    expect(isBrowserApp('Slack')).toBe(false)
    expect(isWindowAllowed('Slack', 'anything at all')).toBe(true)
    // even an empty title passes for a non-browser
    expect(isWindowAllowed('Notes', '')).toBe(true)
  })

  it('a browser must show a title containing at least one keyword', () => {
    expect(isBrowserApp('Google Chrome')).toBe(true)
    expect(isWindowAllowed('Google Chrome', 'Inbox (14) - Gmail')).toBe(true)
    expect(isWindowAllowed('Google Chrome', 'Linear – My Issues')).toBe(true)
    expect(isWindowAllowed('Safari', 'GitHub · Where software is built')).toBe(true)
  })

  it('a browser on an unrelated page is filtered out', () => {
    expect(isWindowAllowed('Google Chrome', 'YouTube - lofi beats')).toBe(false)
    expect(isWindowAllowed('Safari', 'Wikipedia — the free encyclopedia')).toBe(false)
    expect(isWindowAllowed('Google Chrome', '')).toBe(false)
  })
})

describe('isMessagingApp (fast-path set) vs isPromptMessagingApp (reminder set)', () => {
  it('fast-path uses the shared 8-app set', () => {
    expect(isMessagingApp('Messenger')).toBe(true)
    expect(isMessagingApp('iMessage')).toBe(true)
    expect(isMessagingApp('Signal')).toBe(true)
    expect(isMessagingApp('Slack')).toBe(true)
    expect(isMessagingApp('Google Chrome')).toBe(false)
  })

  it('the prompt-reminder set is narrower (no iMessage/Signal/Messenger)', () => {
    expect(isPromptMessagingApp('Slack')).toBe(true)
    expect(isPromptMessagingApp('WhatsApp')).toBe(true)
    expect(isPromptMessagingApp('Telegram')).toBe(true)
    expect(isPromptMessagingApp('Discord')).toBe(true)
    expect(isPromptMessagingApp('Signal')).toBe(false)
    expect(isPromptMessagingApp('Messenger')).toBe(false)
  })
})
