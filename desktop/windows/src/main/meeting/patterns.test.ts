import { describe, it, expect } from 'vitest'
import {
  bundledPatterns,
  sanitizePatterns,
  matchTier1,
  pickAgreedMatch,
  exeBasename
} from './patterns'

const p = bundledPatterns()

describe('meeting patterns', () => {
  it('bundled patterns.json is valid and non-empty', () => {
    expect(p.apps.length).toBeGreaterThan(0)
    expect(p.titles.length).toBeGreaterThan(0)
    expect(p.browsers).toContain('chrome.exe')
  })

  it('sanitize rejects garbage and drops bad regex entries', () => {
    expect(sanitizePatterns(null)).toBeNull()
    expect(sanitizePatterns({})).toBeNull()
    expect(sanitizePatterns({ apps: [], titles: [], browsers: [] })).toBeNull()
    const withBadRegex = sanitizePatterns({
      apps: [{ id: 'x', name: 'X', exes: ['X.EXE'] }],
      browsers: ['CHROME.EXE'],
      titles: [
        { id: 'bad', name: 'Bad', pattern: '(' },
        { id: 'ok', name: 'Ok', pattern: 'Meeting' }
      ]
    })
    expect(withBadRegex?.titles.map((t) => t.id)).toEqual(['ok'])
    expect(withBadRegex?.apps[0].exes).toEqual(['x.exe']) // lowercased
    expect(withBadRegex?.browsers).toEqual(['chrome.exe'])
  })

  it('exeBasename lowercases and strips directories', () => {
    expect(exeBasename('C:\\Users\\x\\AppData\\Zoom\\bin\\Zoom.exe')).toBe('zoom.exe')
    expect(exeBasename('zoom.exe')).toBe('zoom.exe')
    expect(exeBasename(null)).toBeNull()
  })

  it('matches a conferencing process from the snapshot', () => {
    const m = matchTier1(['explorer.exe', 'Zoom.exe'], { exePath: null, title: null }, p)
    expect(m).toEqual([{ id: 'zoom', name: 'Zoom', exe: 'zoom.exe', via: 'process' }])
  })

  it('matches browser meeting titles only for known browsers', () => {
    const meet = matchTier1(
      [],
      { exePath: 'C:\\Program Files\\Google\\Chrome\\chrome.exe', title: 'Meet - abc-defg-hij' },
      p
    )
    expect(meet[0]).toMatchObject({ id: 'meet-web', exe: 'chrome.exe', via: 'title' })

    // Same title in a non-browser (an editor with a weird filename) — no match.
    const editor = matchTier1(
      [],
      { exePath: 'C:\\tools\\notepad.exe', title: 'Meet - notes.txt' },
      p
    )
    expect(editor).toEqual([])
  })

  it('matches Teams / Zoom / Webex browser titles', () => {
    const fg = (title: string): { exePath: string; title: string } => ({
      exePath: 'C:\\x\\msedge.exe',
      title
    })
    expect(matchTier1([], fg('Standup | Microsoft Teams - Profile 1 - Microsoft Edge'), p)[0].id).toBe(
      'teams-web'
    )
    expect(matchTier1([], fg('Zoom Meeting - Google Chrome'), p)[0].id).toBe('zoom-web')
    expect(matchTier1([], fg('Cisco Webex Meetings'), p)[0].id).toBe('webex-web')
  })

  it('YouTube title in a browser is NOT a meeting (false-positive check)', () => {
    const m = matchTier1(
      ['chrome.exe'],
      { exePath: 'C:\\x\\chrome.exe', title: 'Rick Astley - Never Gonna Give You Up - YouTube' },
      p
    )
    expect(m).toEqual([])
  })

  it('agreement: Tier 1 process match + same exe in Tier 2', () => {
    const matches = matchTier1(['Zoom.exe'], { exePath: null, title: null }, p)
    expect(pickAgreedMatch(matches, ['zoom.exe'], p)).toMatchObject({
      id: 'zoom',
      tier2Key: 'zoom.exe'
    })
    // A different app on the mic does not agree.
    expect(pickAgreedMatch(matches, ['audacity.exe'], p)).toBeNull()
  })

  it('agreement: browser title match requires the BROWSER on the mic', () => {
    const matches = matchTier1(
      [],
      { exePath: 'C:\\x\\chrome.exe', title: 'Meet - abc-defg-hij' },
      p
    )
    expect(pickAgreedMatch(matches, ['chrome.exe'], p)).toMatchObject({
      id: 'meet-web',
      tier2Key: 'chrome.exe'
    })
    expect(pickAgreedMatch(matches, ['msedge.exe'], p)).toBeNull()
  })

  it('agreement: packaged Teams correlates snapshot exe with the packaged ConsentStore id', () => {
    const matches = matchTier1(['ms-teams.exe'], { exePath: null, title: null }, p)
    expect(pickAgreedMatch(matches, ['msteams_8wekyb3d8bbwe'], p)).toMatchObject({
      id: 'teams',
      tier2Key: 'msteams_8wekyb3d8bbwe'
    })
  })

  it('agreement: packaged app active in Tier 2 with no Tier 1 match still agrees', () => {
    expect(pickAgreedMatch([], ['msteams_8wekyb3d8bbwe'], p)).toMatchObject({
      id: 'teams',
      exe: null,
      tier2Key: 'msteams_8wekyb3d8bbwe'
    })
    expect(pickAgreedMatch([], ['someotherapp_key'], p)).toBeNull()
  })
})
